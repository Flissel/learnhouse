from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

import src.routers.learning.practice as practice
from src.core.events.database import get_db_session
from src.db.user_organizations import UserOrganization
from src.db.users import AnonymousUser, PublicUser, User
from src.security.auth import get_current_user
from src.tests.learning.test_bootstrap import (
    SERVICE_HEADER,
    SERVICE_KEY,
    _enable_local_mode,
    _mounted_learning_client,
)


@asynccontextmanager
async def _practice_client(db, user):
    app = FastAPI()
    app.include_router(practice.router, prefix="/api/v1/learning")

    async def override_db_session():
        yield db

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_current_user] = lambda: user
    transport = ASGITransport(app=app, client=("172.18.0.4", 43123))
    async with AsyncClient(transport=transport, base_url="http://learnhouse-api") as client:
        yield client


@pytest.mark.asyncio
async def test_practice_is_per_person_and_forwards_to_the_engine(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    calls = []

    async def fake_call(tool, event, *, write=False, fresh=False):
        calls.append((tool, event, write or fresh))
        return {"state": "completed", "result": {"session": {"session_id": str(uuid4())}}, "evidence": None}

    monkeypatch.setattr(practice, "_call", fake_call)
    async with _mounted_learning_client(db) as service:
        created = await service.post(
            "/api/v1/learning/courses",
            headers={SERVICE_HEADER: SERVICE_KEY},
            json={"title": "Practice target", "description": "", "about": ""},
        )
    course = created.json()["course"]
    owner = (await db.execute(select(User))).scalars().first()
    org_id = (await db.execute(select(UserOrganization.org_id).where(UserOrganization.user_id == owner.id))).scalars().first()
    person = PublicUser.model_validate(owner, from_attributes=True)

    async with _practice_client(db, person) as client:
        started = await client.post("/api/v1/learning/practice/sessions",
                                    json={"course_id": course["course_id"], "mode": "training"})
        session_id = str(uuid4())
        answered = await client.post(f"/api/v1/learning/practice/sessions/{session_id}/answer",
                                     json={"revision": 3, "answer": {"choice_id": "y"}})
        spoofed = await client.get(f"/api/v1/learning/practice/sessions/{session_id}?org_id=999")
    async with _practice_client(db, AnonymousUser()) as anonymous:
        refused = await anonymous.post("/api/v1/learning/practice/sessions",
                                       json={"course_id": course["course_id"]})

    assert started.status_code == answered.status_code == spoofed.status_code == 200
    assert refused.status_code == 401
    tool, event, write = calls[0]
    expected_actor = f"lh-{org_id}-{owner.user_uuid}"
    assert tool == "learning_session_start" and write is True
    assert event["actor"] == {"actor_id": expected_actor, "actor_type": "local_user"}
    assert event["course_id"] == course["course_id"] and event["payload"]["mode"] == "training"
    assert isinstance(event["payload"]["course_revision"], int)
    assert calls[1][0] == "learning_task_answer" and calls[1][1]["expected_revision"] == 3
    # A query parameter cannot change the learner: the organisation comes from the server.
    assert calls[2][1]["actor"]["actor_id"] == expected_actor


@pytest.mark.asyncio
async def test_canvas_open_gives_the_drawing_page_of_this_person(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    calls = []

    async def fake_call(tool, event, *, write=False, fresh=False):
        calls.append((tool, event))
        return {"state": "completed", "result": {"page_url": "http://100.67.177.45:8090/zeichnen/t.s"}, "evidence": None}

    monkeypatch.setattr(practice, "_call", fake_call)
    async with _mounted_learning_client(db) as service:
        await service.post("/api/v1/learning/courses", headers={SERVICE_HEADER: SERVICE_KEY},
                           json={"title": "Canvas target", "description": "", "about": ""})
    owner = (await db.execute(select(User))).scalars().first()
    person = PublicUser.model_validate(owner, from_attributes=True)
    session_id, activity_id = str(uuid4()), str(uuid4())
    async with _practice_client(db, person) as client:
        first = await client.post(f"/api/v1/learning/practice/sessions/{session_id}/canvas",
                                  json={"activity_id": activity_id})
        again = await client.post(f"/api/v1/learning/practice/sessions/{session_id}/canvas",
                                  json={"activity_id": activity_id})
    assert first.status_code == 200 and first.json() == {"page_url": "http://100.67.177.45:8090/zeichnen/t.s"}
    tool, event = calls[0]
    assert tool == "learning_canvas_open" and event["payload"]["activity_id"] == activity_id
    assert event["actor"]["actor_id"].endswith(str(owner.user_uuid))
    # Reopening the same task keeps the same canvas reference.
    assert calls[1][1]["payload"]["session_ref"] == event["payload"]["session_ref"]
    assert again.status_code == 200


@pytest.mark.asyncio
async def test_player_token_is_signed_for_the_person(db, monkeypatch) -> None:
    from src.services.learning.person_token import read_person_token

    _enable_local_mode(monkeypatch)
    monkeypatch.setenv("LEARNHOUSE_LEARNING_PLAYER_ORIGIN", "http://100.67.177.45:8090/")
    async with _mounted_learning_client(db) as service:
        await service.post("/api/v1/learning/courses", headers={SERVICE_HEADER: SERVICE_KEY},
                           json={"title": "Token target", "description": "", "about": ""})
    owner = (await db.execute(select(User))).scalars().first()
    org_id = (await db.execute(select(UserOrganization.org_id).where(UserOrganization.user_id == owner.id))).scalars().first()
    person = PublicUser.model_validate(owner, from_attributes=True)
    async with _practice_client(db, person) as client:
        issued = await client.get("/api/v1/learning/practice/player-token")
    async with _practice_client(db, AnonymousUser()) as anonymous:
        refused = await anonymous.get("/api/v1/learning/practice/player-token")

    assert issued.status_code == 200 and refused.status_code == 401
    # Verifiable with the shared service key only; the payload names exactly this person.
    assert read_person_token(issued.json()["token"], key=SERVICE_KEY) == f"lh-{org_id}-{owner.user_uuid}"
    # The web attaches the token only to players on this origin (never to a look-alike embed).
    assert issued.json()["origin"] == "http://100.67.177.45:8090"
    monkeypatch.delenv("LEARNHOUSE_LEARNING_PLAYER_ORIGIN")
    async with _practice_client(db, person) as client:
        unconfigured = await client.get("/api/v1/learning/practice/player-token")
    assert unconfigured.status_code == 200 and unconfigured.json()["origin"] is None


@pytest.mark.asyncio
async def test_notes_are_proxied_for_the_signed_in_person_only(db, monkeypatch) -> None:
    import httpx

    _enable_local_mode(monkeypatch)
    monkeypatch.setenv("LEARNING_RETRIEVAL_SERVICE_URL", "http://learning-api:8090")
    seen: list[tuple[str, str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url), dict(request.headers)))
        if request.method == "GET":
            return httpx.Response(200, json={"notes": [{"id": "11111111-1111-4111-8111-111111111111", "selection": "x"}]})
        return httpx.Response(200, json={"id": "11111111-1111-4111-8111-111111111111", "own_text": "Merken"})

    real = httpx.AsyncClient
    monkeypatch.setattr(practice.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), timeout=kw.get("timeout")))
    async with _mounted_learning_client(db) as service:
        await service.post("/api/v1/learning/courses", headers={SERVICE_HEADER: SERVICE_KEY},
                           json={"title": "Notes target", "description": "", "about": ""})
    owner = (await db.execute(select(User))).scalars().first()
    org_id = (await db.execute(select(UserOrganization.org_id).where(UserOrganization.user_id == owner.id))).scalars().first()
    person = PublicUser.model_validate(owner, from_attributes=True)
    async with _practice_client(db, person) as client:
        listed = await client.get("/api/v1/learning/practice/notes?actor=lh-9-evil")
        changed = await client.patch("/api/v1/learning/practice/notes/11111111-1111-4111-8111-111111111111", json={"own_text": "Merken"})
        odd = await client.patch("/api/v1/learning/practice/notes/not-an-id", json={"own_text": "x"})
    async with _practice_client(db, AnonymousUser()) as anonymous:
        refused = await anonymous.get("/api/v1/learning/practice/notes")

    assert listed.status_code == 200 and listed.json()["notes"][0]["selection"] == "x"
    assert changed.status_code == 200 and changed.json()["own_text"] == "Merken"
    assert odd.status_code == 400 and refused.status_code == 401
    method, url, headers = seen[0]
    assert (method, url) == ("GET", "http://learning-api:8090/api/v1/notizen")
    # The person comes from the server session; the service key never reaches the browser.
    assert headers["x-learnhouse-learning-service-key"] == SERVICE_KEY
    assert headers["x-learning-actor"] == f"lh-{org_id}-{owner.user_uuid}"
    assert seen[1][0] == "PATCH" and seen[1][1].endswith("/api/v1/notizen/11111111-1111-4111-8111-111111111111")


def test_media_paths_become_absolute_on_the_player_origin(monkeypatch) -> None:
    # 27.10.: drawn terminal windows live on learning-api, not on LearnHouse; the practice
    # page would load "/lernsequenz-medien/..." from its own host and show nothing.
    from src.routers.learning import practice

    monkeypatch.setenv("LEARNHOUSE_LEARNING_PLAYER_ORIGIN", "http://100.67.177.45:8090/")
    result = {"task": {"type": "fill_in", "presentation": {
        "image": "/lernsequenz-medien/term-0123456789abcdef.png", "rect": {"x": 1},
        "left": [{"id": "a", "label": "Fenster 1", "image": "/lernsequenz-medien/term-aaaaaaaaaaaaaaaa.png"},
                 {"id": "b", "label": "Text"}],
        "right": [{"id": "s", "label": "CMD", "image": "https://evil.example/x.png"}],
    }}}

    shown = practice._absolute_media(result)["task"]["presentation"]

    assert shown["image"] == "http://100.67.177.45:8090/lernsequenz-medien/term-0123456789abcdef.png"
    assert shown["left"][0]["image"] == "http://100.67.177.45:8090/lernsequenz-medien/term-aaaaaaaaaaaaaaaa.png"
    assert "image" not in shown["left"][1] and "image" not in shown["right"][0]


def test_without_a_player_origin_media_paths_are_dropped(monkeypatch) -> None:
    from src.routers.learning import practice

    monkeypatch.delenv("LEARNHOUSE_LEARNING_PLAYER_ORIGIN", raising=False)
    result = {"task": {"presentation": {"image": "/lernsequenz-medien/term-0123456789abcdef.png", "template": "x"}}}

    assert "image" not in practice._absolute_media(result)["task"]["presentation"]
