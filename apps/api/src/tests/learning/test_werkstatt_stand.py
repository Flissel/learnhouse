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
    # A Werkstatt-written activity (it carries werkstatt_key) missing from the next state goes offline.
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        first = await client.put(
            _url(course_id), headers=H,
            json=_stand(rev, "f1", _foundations(
                _lektion("lesson-authority", "Autoritaet", "Text."), _aufgabe("neu-1", "A", "Frage?"),
            )),
        )
        response = await client.put(
            _url(course_id), headers=H,
            json=_stand(rev + 1, "f2", _foundations(_lektion("lesson-authority", "Autoritaet", "Text."))),
        )
    assert first.status_code == 200 and response.status_code == 200, response.text
    assert response.json()["unveroeffentlicht"] == 1
    rows = {_key(a): a for a in await _activities(db)}
    assert rows["neu-1"].published is False  # not deleted
    assert rows["lesson-authority"].published is True


def _key(activity: Activity) -> str | None:
    meta = activity.extra_metadata or {}
    return meta.get("werkstatt_key") or meta.get("draft_activity_id")


@pytest.mark.asyncio
async def test_nicht_uebernommene_fabrik_aktivitaet_bleibt(db, monkeypatch) -> None:
    # task-authority was never taken over into the Werkstatt: without `entfernen` it stays.
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        response = await client.put(
            _url(course_id), headers=H,
            json=_stand(rev, "f1", _foundations(_lektion("lesson-authority", "Autoritaet", "Text."))),
        )
    assert response.status_code == 200, response.text
    assert response.json()["unveroeffentlicht"] == 0
    rows = {a.extra_metadata["draft_activity_id"]: a for a in await _activities(db)}
    assert rows["task-authority"].published is True
    assert "werkstatt_key" not in rows["task-authority"].extra_metadata


@pytest.mark.asyncio
async def test_nur_ausdruecklich_entfernte_fabrik_aktivitaeten_werden_unveroeffentlicht(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        hand = await _plain_activity(db, "Von Hand", "activity_hand2", {"draft_activity_id": "anderes"})
        body = _stand(rev, "f1", _foundations(_lektion("lesson-authority", "Autoritaet", "Text.")))
        body["entfernen"] = ["task-authority", "lesson-authority", "gibt-es-nicht"]
        response = await client.put(_url(course_id), headers=H, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["unveroeffentlicht"] == 1
    rows = {a.extra_metadata["draft_activity_id"]: a for a in await _activities(db) if a.extra_metadata}
    assert rows["task-authority"].published is False
    assert rows["lesson-authority"].published is True  # in the state, so it stays despite `entfernen`
    assert next(a for a in await _activities(db) if a.id == hand).published is True


@pytest.mark.asyncio
async def test_entfernen_zaehlt_zum_koerper_der_freigabe(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        body = _stand(rev, "f1", _foundations(_lektion("lesson-authority", "A", "Text.")))
        first = await client.put(_url(course_id), headers=H, json=body)
        other = await client.put(_url(course_id), headers=H, json={**body, "entfernen": ["task-authority"]})
        same = await client.put(_url(course_id), headers=H, json={**body, "entfernen": []})
    assert first.status_code == 200
    assert other.status_code == 409 and other.json()["detail"] == "freigabe_id_reused"
    assert same.status_code == 200 and same.json() == first.json()  # empty list = not sent


@pytest.mark.asyncio
async def test_kapitelreihenfolge_folgt_dem_stand(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        course = await _course_row(db)
        anhang = Chapter(
            name="Anhang", description="", thumbnail_image="", org_id=course.org_id,
            course_id=course.id, chapter_uuid="chapter_anhang", creation_date="", update_date="",
        )
        db.add(anhang)
        await db.commit()
        db.add(CourseChapter(
            order=7, course_id=course.id, chapter_id=anhang.id, org_id=course.org_id,
            creation_date="", update_date="",
        ))
        await db.commit()
        response = await client.put(
            _url(course_id), headers=H,
            json=_stand(rev, "f1", [
                {"titel": "Neues Kapitel", "eintraege": [_lektion("neu-1", "Neu", "Text.")]},
                {"titel": "Foundations", "eintraege": [_lektion("lesson-authority", "A", "Text.")]},
            ]),
        )
    assert response.status_code == 200, response.text
    names = {c.id: c.name for c in (await db.execute(select(Chapter))).scalars().all()}
    links = (await db.execute(select(CourseChapter))).scalars().all()
    for link in links:
        await db.refresh(link)
    reihenfolge = [names[link.chapter_id] for link in sorted(links, key=lambda link: link.order)]
    assert reihenfolge == ["Neues Kapitel", "Foundations", "Anhang"]
    assert [link.order for link in sorted(links, key=lambda link: link.order)] == [1, 2, 3]


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

    def flaky(entry, *args):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("erzwungener Fehler")
        return real(entry, *args)

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


@pytest.mark.asyncio
async def test_rollback_auch_am_versionslimit(db, monkeypatch) -> None:
    from src.services.courses.activities.versioning import MAX_ACTIVITY_VERSIONS

    _enable_local_mode(monkeypatch)
    real = stand_module._content_for
    calls = {"n": 0}

    def flaky(entry, *args):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("erzwungener Fehler")
        return real(entry, *args)

    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        lesson = next(a for a in await _activities(db) if a.extra_metadata["draft_activity_id"] == "lesson-authority")
        lesson_id, org_id, old_content = lesson.id, lesson.org_id, lesson.content
        lesson.current_version = MAX_ACTIVITY_VERSIONS + 5
        for number in range(1, MAX_ACTIVITY_VERSIONS + 1):
            db.add(ActivityVersion(activity_id=lesson_id, org_id=org_id, version_number=number, content={}))
        await db.commit()
        monkeypatch.setattr(stand_module, "_content_for", flaky)
        with pytest.raises(RuntimeError):
            await _put(
                client, course_id, rev, "f1",
                _lektion("lesson-authority", "A", "Zwischenstand."),
                _aufgabe("task-authority", "A", "Frage?"),
            )
    numbers = sorted(
        v.version_number
        for v in (await db.execute(select(ActivityVersion).where(ActivityVersion.activity_id == lesson_id))).scalars().all()
    )
    assert numbers == list(range(1, MAX_ACTIVITY_VERSIONS + 1))
    lesson = next(a for a in await _activities(db) if a.id == lesson_id)
    assert lesson.content == old_content and lesson.current_version == MAX_ACTIVITY_VERSIONS + 5
    state = (await db.execute(select(LearningCourseState))).scalars().first()
    await db.refresh(state)
    assert state.revision == rev and "werkstatt_freigaben" not in (state.source_metadata or {})


def _types(node) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        if "type" in node:
            found.append(node["type"])
        for value in node.values():
            found += _types(value)
    elif isinstance(node, list):
        for value in node:
            found += _types(value)
    return found


@pytest.mark.asyncio
async def test_formeln_nur_mit_math(db, monkeypatch) -> None:
    # Ruling 6: Learning sends `math: true` for math courses only; Terminal text stays as before.
    _enable_local_mode(monkeypatch)
    terminal = "Mit $env:Path;$env:USERPROFILE arbeiten."
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        ohne = await client.put(
            _url(course_id), headers=H,
            json=_stand(rev, "f1", _foundations(
                _lektion("lesson-authority", "Autoritaet", terminal), _aufgabe("t-1", "T", "Was zeigt $env:Path;$x$?"),
            )),
        )
        assert ohne.status_code == 200, ohne.text
        lektion = next(a for a in await _activities(db) if (a.extra_metadata or {}).get("werkstatt_key") == "lesson-authority")
        assert "inlineMathEquation" not in _types(lektion.content)
        assert lektion.content["content"][0]["content"] == [{"type": "text", "text": terminal}]
        # A body with `math: false` is the very same release as one without the field.
        wieder = await client.put(
            _url(course_id), headers=H,
            json={**_stand(rev, "f1", _foundations(
                _lektion("lesson-authority", "Autoritaet", terminal), _aufgabe("t-1", "T", "Was zeigt $env:Path;$x$?"),
            )), "math": False},
        )
        assert wieder.status_code == 200, wieder.text
        mit = await client.put(
            _url(course_id), headers=H,
            json={**_stand(rev + 1, "f2", _foundations(
                _lektion("lesson-authority", "Autoritaet", "Es gilt\n$$f'(x)=3x^2$$\nund $x^2$."),
                _aufgabe("t-1", "T", "Was ist $f(1)$?"),
            )), "math": True},
        )
    assert mit.status_code == 200, mit.text
    by_key = {(a.extra_metadata or {}).get("werkstatt_key"): a for a in await _activities(db)}
    assert "blockMathEquation" in _types(by_key["lesson-authority"].content)
    assert "inlineMathEquation" in _types(by_key["t-1"].content)


async def _unpublished_course(client, db) -> tuple[str, int]:
    course_id, rev = await _published_course(client)
    course = await _course_row(db)
    course.published = False
    db.add(course)
    await db.flush()
    return course_id, rev


@pytest.mark.asyncio
async def test_freigabe_veroeffentlicht_unveroeffentlichten_kurs_und_aktivitaeten(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _unpublished_course(client, db)
        response = await client.put(
            _url(course_id), headers=H,
            json=_stand(rev, "f1", _foundations(
                _lektion("lesson-authority", "Autoritaet", "Neuer Text."),
                _aufgabe("neu-1", "Neu", "Frage?"),
            )),
        )
    assert response.status_code == 200, response.text
    assert (await _course_row(db)).published is True
    rows = {_key(a): a for a in await _activities(db)}
    assert rows["neu-1"].published is True
    assert rows["lesson-authority"].published is True


@pytest.mark.asyncio
async def test_freigabe_laesst_veroeffentlichten_kurs_veroeffentlicht(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        response = await _put(client, course_id, rev, "f1", _lektion("neu-1", "Neu", "Text."))
    assert response.status_code == 200, response.text
    assert (await _course_row(db)).published is True


@pytest.mark.asyncio
async def test_freigabe_entfernte_aktivitaet_bleibt_unveroeffentlicht(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _unpublished_course(client, db)
        first = await _put(client, course_id, rev, "f1",
                           _lektion("lesson-authority", "Autoritaet", "Text."), _aufgabe("neu-1", "A", "Frage?"))
        second = await _put(client, course_id, rev + 1, "f2", _lektion("lesson-authority", "Autoritaet", "Text."))
    assert first.status_code == 200 and second.status_code == 200, second.text
    rows = {_key(a): a for a in await _activities(db)}
    assert rows["neu-1"].published is False
    assert rows["lesson-authority"].published is True
    assert (await _course_row(db)).published is True


@pytest.mark.asyncio
async def test_umbenanntes_kapitel_wird_wiederverwendet(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        first = await client.put(
            _url(course_id), headers=H,
            json=_stand(rev, "f1", [
                {"titel": "A $x$", "eintraege": [_lektion("a-1", "A1", "Text.")]},
                {"titel": "B", "eintraege": [_lektion("b-1", "B1", "Text.")]},
            ]),
        )
        assert first.status_code == 200, first.text
        old = (await db.execute(select(Chapter).where(Chapter.name == "A $x$"))).scalars().one()
        old_id, old_uuid = old.id, old.chapter_uuid
        second = await client.put(
            _url(course_id), headers=H,
            json=_stand(rev + 1, "f2", [
                {"titel": "A x", "eintraege": [_lektion("a-1", "A1", "Text.")]},
                {"titel": "B", "eintraege": [_lektion("b-1", "B1", "Text.")]},
            ]),
        )
        assert second.status_code == 200, second.text
    db.expire_all()
    chapters = (await db.execute(select(Chapter).where(Chapter.extra_metadata.is_not(None)))).scalars().all()
    werkstatt = [c for c in chapters if (c.extra_metadata or {}).get("werkstatt_generated")]
    assert sorted(c.name for c in werkstatt) == ["A x", "B"]
    renamed = next(c for c in werkstatt if c.name == "A x")
    assert renamed.id == old_id and renamed.chapter_uuid == old_uuid
    links = (await db.execute(select(ChapterActivity))).scalars().all()
    for chapter in werkstatt:
        assert any(link.chapter_id == chapter.id for link in links)
    a1 = next(a for a in await _activities(db) if (a.extra_metadata or {}).get("werkstatt_key") == "a-1")
    assert next(l for l in links if l.activity_id == a1.id).chapter_id == old_id


@pytest.mark.asyncio
async def test_nicht_werkstatt_kapitel_wird_nicht_umbenannt(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        response = await client.put(
            _url(course_id), headers=H,
            json=_stand(rev, "f1", [{"titel": "Ganz Neu", "eintraege": [_lektion("neu-1", "Neu", "Text.")]}]),
        )
        assert response.status_code == 200, response.text
    chapters = (await db.execute(select(Chapter))).scalars().all()
    assert "Foundations" in {c.name for c in chapters}
    assert "Ganz Neu" in {c.name for c in chapters}


@pytest.mark.asyncio
async def test_werkstatt_stand_legt_bewertungsseite_an(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    bewertung = {"key": "kursbewertung", "art": "bewertung", "titel": "Wie fanden Sie diesen Kurs?"}
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        response = await client.put(
            _url(course_id), headers=H,
            json=_stand(rev, "f-bew", [
                {"titel": "Foundations", "eintraege": [_lektion("l1", "Eins", "Text.")]},
                {"titel": "Kurs abschließen", "eintraege": [bewertung]},
            ]),
        )
    assert response.status_code == 200
    page = next(a for a in await _activities(db) if (a.extra_metadata or {}).get("werkstatt_key") == "kursbewertung")
    assert page.details["learning_kind"] == "bewertung"
    assert page.extra_metadata["learning_kind"] == "bewertung"
    assert page.name == "Wie fanden Sie diesen Kurs?"
    assert page.published is True


@pytest.mark.asyncio
async def test_bewertungskapitel_uebernimmt_kein_altes_kapitel(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    bewertung = {"key": "kursbewertung", "art": "bewertung", "titel": "Wie fanden Sie diesen Kurs?"}
    async with _mounted_learning_client(db) as client:
        course_id, rev = await _published_course(client)
        first = await client.put(
            _url(course_id), headers=H,
            json=_stand(rev, "f-alt", [
                {"titel": "Foundations", "eintraege": [_lektion("lesson-authority", "A", "Text.")]},
                {"titel": "C", "eintraege": [_lektion("c-1", "Alt", "Alt.")]},
            ]),
        )
        assert first.status_code == 200, first.text
        second = await client.put(
            _url(course_id), headers=H,
            json=_stand(rev + 1, "f-neu", [
                {"titel": "Foundations", "eintraege": [_lektion("lesson-authority", "A", "Text.")]},
                {"titel": "Kurs abschließen", "eintraege": [bewertung]},
            ]),
        )
    assert second.status_code == 200, second.text
    chapters = {c.name: c for c in (await db.execute(select(Chapter))).scalars().all()}
    assert "C" in chapters, "old chapter must not be renamed into the rating chapter"
    rating = chapters["Kurs abschließen"]
    assert rating.id != chapters["C"].id
    activities = {a.id: a for a in await _activities(db)}

    async def keys_in(chapter: Chapter) -> list[str]:
        links = (
            await db.execute(select(ChapterActivity).where(ChapterActivity.chapter_id == chapter.id))
        ).scalars().all()
        return [activities[link.activity_id].extra_metadata.get("werkstatt_key") for link in links]

    assert await keys_in(rating) == ["kursbewertung"]
    assert await keys_in(chapters["C"]) == ["c-1"]
    old = next(a for a in activities.values() if a.extra_metadata.get("werkstatt_key") == "c-1")
    assert old.published is False
