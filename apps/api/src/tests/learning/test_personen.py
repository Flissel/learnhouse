"""Teil B: each LearnHouse account keeps one fixed Learning learner id (``actor_id``)."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import httpx
import pytest

import src.routers.learning.practice as practice
from src.db.learning.teil_b import LearningPerson
from src.db.user_organizations import UserOrganization
from src.db.users import PublicUser, User
from src.services.learning.personen import (
    KennungVergeben,
    _org_of,
    actor_von,
    learner_id,
    person_zu_actor,
)
from src.tests.learning.test_bootstrap import (
    BOOTSTRAP_HEADER,
    BOOTSTRAP_KEY,
    SERVICE_KEY,
    _bootstrap_client,
    _enable_local_mode,
)
from src.tests.learning.test_practice import _practice_client


async def _person(db, *, user_id: int, membership_id: int, name: str, org_id: int, role_id: int) -> PublicUser:
    now = str(datetime.now())
    user = User(
        id=user_id, username=name, first_name=name, last_name="Test", email=f"{name}@example.com",
        password="hashed_password", user_uuid=f"user_{name}", creation_date=now, update_date=now,
    )
    db.add(user)
    await db.commit()
    db.add(UserOrganization(id=membership_id, user_id=user_id, org_id=org_id, role_id=role_id,
                            creation_date=now, update_date=now))
    await db.commit()
    return PublicUser(id=user.id, username=user.username, first_name=user.first_name, last_name=user.last_name,
                      email=user.email, user_uuid=user.user_uuid)


@pytest.fixture
async def person_a(db, org, user_role) -> PublicUser:
    return await _person(db, user_id=11, membership_id=10, name="person-a", org_id=org.id, role_id=user_role.id)


@pytest.fixture
async def person_b(db, org, user_role) -> PublicUser:
    return await _person(db, user_id=12, membership_id=20, name="person-b", org_id=org.id, role_id=user_role.id)


@pytest.fixture
def bootstrap_kopf(monkeypatch) -> dict[str, str]:
    _enable_local_mode(monkeypatch)
    return {BOOTSTRAP_HEADER: BOOTSTRAP_KEY}


async def _mitgliedschaft_vorn_einfuegen(db, person: PublicUser, org_id: int) -> None:
    """A membership with a lower id: ``_org_of`` (first membership) now names another org."""
    now = str(datetime.now())
    db.add(UserOrganization(id=1, user_id=person.id, org_id=org_id, role_id=4, creation_date=now, update_date=now))
    await db.commit()


@pytest.mark.asyncio
async def test_actor_von_legt_bisherige_formel_fest_an(db, person_a, org) -> None:
    erwartet = learner_id(person_a, org.id)

    assert erwartet == f"lh-{org.id}-user_person-a"
    assert await actor_von(db, person_a) == erwartet
    assert (await db.get(LearningPerson, person_a.id)).actor_id == erwartet
    assert (await person_zu_actor(db, erwartet)).id == person_a.id
    assert await person_zu_actor(db, "lh-unbekannt") is None


@pytest.mark.asyncio
async def test_feste_zuordnung_bleibt(db, person_a, org, other_org) -> None:
    erst = await actor_von(db, person_a)
    await _mitgliedschaft_vorn_einfuegen(db, person_a, other_org.id)

    # The formula would now give another id; the stored one wins.
    assert await _org_of(db, person_a) == other_org.id
    assert learner_id(person_a, other_org.id) != erst
    assert await actor_von(db, person_a) == erst


@pytest.mark.asyncio
async def test_actor_von_nimmt_keine_fremde_kennung(db, person_a, person_b, org, bootstrap_kopf) -> None:
    # The formula id of person-a is already fixed for person-b: never share a learner.
    async with _bootstrap_client(db) as client:
        gesetzt = await client.post("/api/v1/learning/bootstrap/person", headers=bootstrap_kopf,
                                    json={"user_id": person_b.id, "actor_id": learner_id(person_a, org.id)})
    assert gesetzt.status_code == 200

    with pytest.raises(KennungVergeben):
        await actor_von(db, person_a)
    assert await db.get(LearningPerson, person_a.id) is None


@pytest.mark.asyncio
async def test_bootstrap_person_setzt_zuordnung(db, person_a, bootstrap_kopf) -> None:
    async with _bootstrap_client(db) as client:
        r = await client.post("/api/v1/learning/bootstrap/person", headers=bootstrap_kopf,
                              json={"user_id": person_a.id, "actor_id": "lh-1-alt"})
        nochmal = await client.post("/api/v1/learning/bootstrap/person", headers=bootstrap_kopf,
                                    json={"user_id": person_a.id, "actor_id": "lh-1-alt"})

    assert r.status_code == 200 and r.json() == {"user_id": person_a.id, "actor_id": "lh-1-alt"}
    assert nochmal.status_code == 200
    assert (await person_zu_actor(db, "lh-1-alt")).id == person_a.id
    assert await actor_von(db, person_a) == "lh-1-alt"


@pytest.mark.asyncio
async def test_bootstrap_person_ersetzt_angelegte_zuordnung(db, person_a, bootstrap_kopf) -> None:
    await actor_von(db, person_a)  # lazily created from the formula
    async with _bootstrap_client(db) as client:
        r = await client.post("/api/v1/learning/bootstrap/person", headers=bootstrap_kopf,
                              json={"user_id": person_a.id, "actor_id": "lh-1-alt"})

    assert r.status_code == 200
    assert await actor_von(db, person_a) == "lh-1-alt"


@pytest.mark.asyncio
async def test_bootstrap_person_doppelt_409(db, person_a, person_b, bootstrap_kopf) -> None:
    async with _bootstrap_client(db) as client:
        erst = await client.post("/api/v1/learning/bootstrap/person", headers=bootstrap_kopf,
                                 json={"user_id": person_a.id, "actor_id": "lh-1-alt"})
        doppelt = await client.post("/api/v1/learning/bootstrap/person", headers=bootstrap_kopf,
                                    json={"user_id": person_b.id, "actor_id": "lh-1-alt"})

    assert erst.status_code == 200
    assert doppelt.status_code == 409
    assert (await person_zu_actor(db, "lh-1-alt")).id == person_a.id
    assert await db.get(LearningPerson, person_b.id) is None


@pytest.mark.asyncio
async def test_bootstrap_person_prueft_eingaben(db, person_a, bootstrap_kopf) -> None:
    async with _bootstrap_client(db) as client:
        unsicher = await client.post("/api/v1/learning/bootstrap/person", headers=bootstrap_kopf,
                                     json={"user_id": person_a.id, "actor_id": "lh 1/alt"})
        zeilenumbruch = await client.post("/api/v1/learning/bootstrap/person", headers=bootstrap_kopf,
                                          json={"user_id": person_a.id, "actor_id": "lh-1-alt\n"})
        zu_lang = await client.post("/api/v1/learning/bootstrap/person", headers=bootstrap_kopf,
                                    json={"user_id": person_a.id, "actor_id": "a" * 129})
        unbekannt = await client.post("/api/v1/learning/bootstrap/person", headers=bootstrap_kopf,
                                      json={"user_id": 999, "actor_id": "lh-1-alt"})

    assert unsicher.status_code == zeilenumbruch.status_code == zu_lang.status_code == 422
    assert unbekannt.status_code == 404
    assert await db.get(LearningPerson, person_a.id) is None


@pytest.mark.asyncio
async def test_bootstrap_person_ohne_schluessel_403(db, person_a, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    async with _bootstrap_client(db) as client:
        ohne = await client.post("/api/v1/learning/bootstrap/person",
                                 json={"user_id": person_a.id, "actor_id": "lh-1-alt"})
        falsch = await client.post("/api/v1/learning/bootstrap/person", headers={BOOTSTRAP_HEADER: "x" * 40},
                                   json={"user_id": person_a.id, "actor_id": "lh-1-alt"})

    assert ohne.status_code == falsch.status_code == 403
    assert await db.get(LearningPerson, person_a.id) is None


@pytest.mark.asyncio
async def test_practice_nutzt_feste_zuordnung(db, person_a, bootstrap_kopf, monkeypatch) -> None:
    from src.services.learning.person_token import read_person_token

    calls: list[tuple[str, dict]] = []

    async def fake_call(tool, event, *, write=False, fresh=False):
        calls.append((tool, event))
        return {"state": "completed", "result": {}, "evidence": None}

    seen: list[dict[str, str]] = []

    def notes(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.headers))
        return httpx.Response(200, json={"notes": []})

    real = httpx.AsyncClient
    monkeypatch.setattr(practice, "_call", fake_call)
    monkeypatch.setattr(practice.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(notes), timeout=kw.get("timeout")))
    async with _bootstrap_client(db) as client:
        gesetzt = await client.post("/api/v1/learning/bootstrap/person", headers=bootstrap_kopf,
                                    json={"user_id": person_a.id, "actor_id": "lh-1-alt"})
    session_id = str(uuid4())
    async with _practice_client(db, person_a) as client:
        aufgabe = await client.get(f"/api/v1/learning/practice/sessions/{session_id}")
        antwort = await client.post(f"/api/v1/learning/practice/sessions/{session_id}/answer",
                                    json={"revision": 1, "answer": {"choice_id": "a"}})
        token = await client.get("/api/v1/learning/practice/player-token")
        mappe = await client.get("/api/v1/learning/practice/notes")

    assert gesetzt.status_code == aufgabe.status_code == antwort.status_code == 200
    assert token.status_code == mappe.status_code == 200
    assert [event["actor"]["actor_id"] for _, event in calls] == ["lh-1-alt", "lh-1-alt"]
    assert read_person_token(token.json()["token"], key=SERVICE_KEY) == "lh-1-alt"
    assert seen[0]["x-learning-actor"] == "lh-1-alt"
