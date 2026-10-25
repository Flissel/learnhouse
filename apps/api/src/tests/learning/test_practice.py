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
