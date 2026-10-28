from __future__ import annotations

from uuid import uuid4, uuid5

import pytest
from sqlmodel import select

from src.db.courses.activities import Activity
from src.db.courses.activity_versions import ActivityVersion
from src.db.courses.chapter_activities import ChapterActivity
from src.db.courses.chapters import Chapter
from src.db.courses.course_chapters import CourseChapter
from src.db.courses.courses import Course
from src.db.courses.learning_state import LearningCourseState
from src.tests.learning.test_bootstrap import (
    SERVICE_HEADER,
    SERVICE_KEY,
    _enable_local_mode,
    _mounted_learning_client,
)
import src.services.learning.werkstatt_stand as stand_module
from src.tests.learning.test_factory_draft import _draft, _draft_hash

H = {SERVICE_HEADER: SERVICE_KEY}


def _stand(expected_revision: int, freigabe_id: str, kapitel: list[dict]) -> dict:
    return {"expected_revision": expected_revision, "freigabe_id": freigabe_id, "kapitel": kapitel}


def _lektion(key: str, titel: str, markdown: str) -> dict:
    return {"key": key, "art": "lesson", "titel": titel, "markdown": markdown, "claims": ["Kernaussage"]}


def _aufgabe(key: str, titel: str, prompt: str) -> dict:
    return {"key": key, "art": "task", "titel": titel, "prompt": prompt}


def _foundations(*eintraege: dict) -> list[dict]:
    return [{"titel": "Foundations", "eintraege": list(eintraege)}]


async def _published_course(client) -> tuple[str, int]:
    created = await client.post(
        "/api/v1/learning/courses", headers=H,
        json={"title": "Stand-Ziel", "description": "", "about": ""},
    )
    course_id = created.json()["course"]["course_id"]
    draft = _draft(str(uuid4()), course_id)
    await client.put(
        f"/api/v1/learning/courses/{course_id}/factory-draft", headers=H,
        json={"expected_revision": 1, "draft_hash": _draft_hash(draft), "draft": draft},
    )
    await client.post(
        f"/api/v1/learning/courses/{course_id}/review", headers=H,
        json={"review": "approved", "expected_revision": 2},
    )
    published = await client.post(
        f"/api/v1/learning/courses/{course_id}/publish", headers=H, json={"expected_revision": 3}
    )
    assert published.status_code == 200
    return course_id, 4


def _url(course_id: str) -> str:
    return f"/api/v1/learning/courses/{course_id}/werkstatt-stand"


async def _activities(db) -> list[Activity]:
    rows = (await db.execute(select(Activity))).scalars().all()
    for row in rows:
        await db.refresh(row)
    return list(rows)


@pytest.mark.asyncio
async def test_veroeffentlichter_kurs_nimmt_stand_an(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        response = await client.put(
            _url(course_id), headers=H,
            json=_stand(rev, "f1", _foundations(_lektion("lesson-authority", "Autoritaet", "Neuer Text."))),
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["revision"] == rev + 1
    assert body["aktualisiert"] == 1 and body["neu"] == 0


@pytest.mark.asyncio
async def test_vorhandene_aktivitaet_wird_an_ort_und_stelle_aktualisiert(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        before = next(a for a in await _activities(db) if a.extra_metadata["draft_activity_id"] == "lesson-authority")
        old_id, old_content = before.id, before.content
        response = await client.put(
            _url(course_id), headers=H,
            json=_stand(rev, "f1", _foundations(_lektion("lesson-authority", "Autoritaet", "Voellig neuer Text."))),
        )
    assert response.status_code == 200, response.text
    after = next(a for a in await _activities(db) if a.extra_metadata["draft_activity_id"] == "lesson-authority")
    assert after.id == old_id
    assert "Voellig neuer Text." in str(after.content)
    assert after.extra_metadata["werkstatt_key"] == "lesson-authority"
    assert after.published is True
    versions = (
        await db.execute(select(ActivityVersion).where(ActivityVersion.activity_id == old_id))
    ).scalars().all()
    assert len(versions) == 1 and versions[0].content == old_content


@pytest.mark.asyncio
async def test_neuer_schluessel_legt_veroeffentlichte_aktivitaet_an(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        response = await client.put(
            _url(course_id), headers=H,
            json=_stand(rev, "f1", [{"titel": "Neues Kapitel", "eintraege": [_lektion("neu-1", "Neu", "Text.")]}]),
        )
    assert response.status_code == 200, response.text
    assert response.json()["neu"] == 1
    created = next(a for a in await _activities(db) if (a.extra_metadata or {}).get("werkstatt_key") == "neu-1")
    assert created.published is True
    assert created.activity_sub_type == "SUBTYPE_DYNAMIC_PAGE"
    chapters = (await db.execute(select(Chapter))).scalars().all()
    assert {c.name for c in chapters} == {"Foundations", "Neues Kapitel"}


@pytest.mark.asyncio
async def test_entfernte_schluessel_werden_unveroeffentlicht(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        response = await client.put(
            _url(course_id), headers=H,
            json=_stand(rev, "f1", _foundations(_lektion("lesson-authority", "Autoritaet", "Text."))),
        )
    assert response.status_code == 200, response.text
    assert response.json()["unveroeffentlicht"] == 1
    rows = {a.extra_metadata["draft_activity_id"]: a for a in await _activities(db)}
    assert rows["task-authority"].published is False  # not deleted
    assert rows["lesson-authority"].published is True


@pytest.mark.asyncio
async def test_revision_konflikt_ist_409(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        response = await client.put(
            _url(course_id), headers=H,
            json=_stand(rev - 1, "f1", _foundations(_lektion("lesson-authority", "A", "Text."))),
        )
    assert response.status_code == 409
    assert response.json()["detail"] == "revision_conflict"


@pytest.mark.asyncio
async def test_gleiche_freigabe_id_ist_idempotent(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        first = await client.put(
            _url(course_id), headers=H,
            json=_stand(rev, "f1", _foundations(_lektion("lesson-authority", "A", "Eins."))),
        )
        again = await client.put(
            _url(course_id), headers=H,
            json=_stand(rev, "f1", _foundations(_lektion("lesson-authority", "A", "Eins."))),
        )
    assert first.status_code == again.status_code == 200
    assert first.json() == again.json()
    lesson = next(a for a in await _activities(db) if a.extra_metadata["draft_activity_id"] == "lesson-authority")
    assert "Eins." in str(lesson.content)
    state = (await db.execute(select(LearningCourseState))).scalars().first()
    await db.refresh(state)
    assert state.revision == rev + 1
    assert len((await db.execute(select(ActivityVersion))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_lektion_vor_aufgabe_in_reihenfolge(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        response = await client.put(
            _url(course_id), headers=H,
            json=_stand(rev, "f1", _foundations(
                _lektion("lesson-authority", "L1", "Text 1."),
                _aufgabe("task-authority", "A1", "Frage 1?"),
                _lektion("l2", "L2", "Text 2."),
                _aufgabe("t2", "A2", "Frage 2?"),
            )),
        )
    assert response.status_code == 200, response.text
    by_id = {a.id: a for a in await _activities(db)}
    links = (await db.execute(select(ChapterActivity).order_by(ChapterActivity.order))).scalars().all()
    keys = [
        (by_id[link.activity_id].extra_metadata.get("werkstatt_key")) for link in links
    ]
    assert keys == ["lesson-authority", "task-authority", "l2", "t2"]


async def _put(client, course_id, rev, fid, *eintraege, titel="Foundations"):
    return await client.put(
        _url(course_id), headers=H,
        json=_stand(rev, fid, [{"titel": titel, "eintraege": list(eintraege)}]),
    )


async def _course_row(db) -> Course:
    return (await db.execute(select(Course))).scalars().first()


@pytest.mark.asyncio
async def test_gleiche_freigabe_id_mit_anderem_inhalt_ist_409(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        first = await _put(client, course_id, rev, "f1", _lektion("lesson-authority", "A", "Eins."))
        other = await _put(client, course_id, rev, "f1", _lektion("lesson-authority", "A", "Zwei."))
    assert first.status_code == 200
    assert other.status_code == 409 and other.json()["detail"] == "freigabe_id_reused"
    lesson = next(a for a in await _activities(db) if a.extra_metadata["draft_activity_id"] == "lesson-authority")
    assert "Zwei." not in str(lesson.content)


@pytest.mark.asyncio
async def test_unveraenderter_inhalt_legt_keine_version_an(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        first = await _put(client, course_id, rev, "f1", _lektion("lesson-authority", "A", "Text."))
        second = await _put(client, course_id, rev + 1, "f2", _lektion("lesson-authority", "A", "Text."))
    assert first.status_code == second.status_code == 200
    assert second.json()["aktualisiert"] == 0
    lesson = next(a for a in await _activities(db) if a.extra_metadata["draft_activity_id"] == "lesson-authority")
    assert lesson.current_version == 2
    assert len((await db.execute(select(ActivityVersion))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_versionen_werden_auf_maximum_begrenzt(db, monkeypatch) -> None:
    from src.services.courses.activities.versioning import MAX_ACTIVITY_VERSIONS

    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        lesson = next(a for a in await _activities(db) if a.extra_metadata["draft_activity_id"] == "lesson-authority")
        lesson_id, org_id = lesson.id, lesson.org_id
        lesson.current_version = MAX_ACTIVITY_VERSIONS + 5
        for number in range(1, MAX_ACTIVITY_VERSIONS + 1):
            db.add(ActivityVersion(activity_id=lesson_id, org_id=org_id, version_number=number, content={}))
        await db.commit()
        response = await _put(client, course_id, rev, "f1", _lektion("lesson-authority", "A", "Neu."))
    assert response.status_code == 200, response.text
    numbers = [
        v.version_number
        for v in (await db.execute(select(ActivityVersion).where(ActivityVersion.activity_id == lesson_id))).scalars().all()
    ]
    assert len(numbers) == MAX_ACTIVITY_VERSIONS
    assert MAX_ACTIVITY_VERSIONS + 5 in numbers and 1 not in numbers


@pytest.mark.asyncio
async def test_einbettung_bleibt_nach_textaenderung(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    player = "http://127.0.0.1:8090/lernsequenz/praes-x-kurs?k=" + "a" * 40
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        embedded = await client.put(
            f"/api/v1/learning/courses/{course_id}/lernsequenz-einbettungen", headers=H,
            json={"lesson_id": "lesson-authority", "embeds": [{"heading": "Praesentation", "url": player}]},
        )
        response = await _put(client, course_id, rev, "f1", _lektion("lesson-authority", "A", "Ganz neu."))
    assert embedded.status_code == response.status_code == 200
    lesson = next(a for a in await _activities(db) if a.extra_metadata["draft_activity_id"] == "lesson-authority")
    assert "Ganz neu." in str(lesson.content)
    embeds = [b for b in lesson.content["content"] if b["type"] == "blockEmbed"]
    assert len(embeds) == 1 and embeds[0]["attrs"]["embedUrl"] == player


async def _plain_activity(db, name: str, uuid: str, meta: dict | None) -> int:
    course = await _course_row(db)
    row = Activity(
        name=name, activity_type="TYPE_DYNAMIC", activity_sub_type="SUBTYPE_DYNAMIC_PAGE",
        content={"type": "doc", "content": []}, published=True, org_id=course.org_id,
        course_id=course.id, activity_uuid=uuid, creation_date="", update_date="",
        extra_metadata=meta,
    )
    db.add(row)
    await db.commit()
    return row.id


@pytest.mark.asyncio
async def test_treffer_ueber_werkstatt_key(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        row_id = await _plain_activity(db, "Alt", "activity_wk", {"werkstatt_key": "wk-1"})
        response = await _put(client, course_id, rev, "f1", _lektion("wk-1", "Neu", "Inhalt."))
    assert response.status_code == 200, response.text
    assert response.json()["neu"] == 0 and response.json()["aktualisiert"] == 1
    again = next(a for a in await _activities(db) if a.id == row_id)
    assert "Inhalt." in str(again.content) and again.name == "Neu"


@pytest.mark.asyncio
async def test_handgemachte_aktivitaet_bleibt_veroeffentlicht(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        row_id = await _plain_activity(db, "Von Hand", "activity_hand", None)
        response = await _put(client, course_id, rev, "f1", _lektion("lesson-authority", "A", "Text."))
    assert response.status_code == 200, response.text
    hand = next(a for a in await _activities(db) if a.id == row_id)
    assert hand.published is True and hand.name == "Von Hand"
    assert hand.content == {"type": "doc", "content": []}


@pytest.mark.asyncio
async def test_neue_aktivitaet_hat_werkstatt_uuid(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        response = await _put(client, course_id, rev, "f1", _lektion("neu-1", "Neu", "Text."))
    assert response.status_code == 200
    course = await _course_row(db)
    created = next(a for a in await _activities(db) if (a.extra_metadata or {}).get("werkstatt_key") == "neu-1")
    expected = uuid5(stand_module._WERKSTATT_NAMESPACE, f"werkstatt:{course.course_uuid}:neu-1")
    assert created.activity_uuid == f"activity_{expected}"


@pytest.mark.asyncio
async def test_fehler_mitten_drin_rollt_alles_zurueck(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    real = stand_module._content_for
    calls = {"n": 0}

    def flaky(entry):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("erzwungener Fehler")
        return real(entry)

    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        monkeypatch.setattr(stand_module, "_content_for", flaky)
        with pytest.raises(RuntimeError):
            await _put(
                client, course_id, rev, "f1",
                _lektion("lesson-authority", "Geaendert", "Zwischenstand."),
                _aufgabe("task-authority", "A", "Frage?"),
            )
    rows = {a.extra_metadata["draft_activity_id"]: a for a in await _activities(db)}
    assert "Zwischenstand." not in str(rows["lesson-authority"].content)
    assert rows["lesson-authority"].name != "Geaendert"
    assert (await db.execute(select(ActivityVersion))).scalars().all() == []
    state = (await db.execute(select(LearningCourseState))).scalars().first()
    await db.refresh(state)
    assert state.revision == rev and "werkstatt_freigaben" not in (state.source_metadata or {})


@pytest.mark.asyncio
async def test_kapitel_wird_ueber_titel_wiederverwendet(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        response = await _put(client, course_id, rev, "f1", _lektion("lesson-authority", "A", "Text."))
    assert response.status_code == 200
    assert len((await db.execute(select(Chapter))).scalars().all()) == 1
    assert len((await db.execute(select(CourseChapter))).scalars().all()) == 1
