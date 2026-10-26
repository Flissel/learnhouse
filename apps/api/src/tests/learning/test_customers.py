from __future__ import annotations

import pytest
from sqlmodel import select

import src.services.learning.kunden as kunden
import src.services.users.usergroups as usergroups
from src.db.courses.courses import Course
from src.db.usergroup_resources import UserGroupResource
from src.db.usergroups import UserGroup
from src.tests.learning.test_bootstrap import (
    SERVICE_HEADER,
    SERVICE_KEY,
    _enable_local_mode,
    _mounted_learning_client,
)


@pytest.mark.asyncio
async def test_a_customer_is_a_usergroup_with_private_courses_and_an_invite(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    invites = []

    async def fake_invite(request, org_id, current_user, db_session, usergroup_id=None):
        invites.append((org_id, usergroup_id))
        return {"invite_code": "Ab12Cd34"}

    async def no_usage(*args, **kwargs):
        return None

    monkeypatch.setattr(kunden, "create_invite_code", fake_invite)
    # Usage counting needs Redis and webhook tables; in operation it runs as usual.
    monkeypatch.setattr(usergroups, "increase_feature_usage", no_usage)
    headers = {SERVICE_HEADER: SERVICE_KEY}
    async with _mounted_learning_client(db) as service:
        created = await service.post("/api/v1/learning/courses", headers=headers,
                                     json={"title": "Kundenkurs", "description": "", "about": ""})
        course_id = created.json()["course"]["course_id"]
        refused = await service.post("/api/v1/learning/customers",
                                     json={"name": "Musterkunde GmbH", "course_ids": [course_id]})
        customer = await service.post("/api/v1/learning/customers", headers=headers,
                                      json={"name": "Musterkunde GmbH", "course_ids": [course_id]})
        listed = await service.get("/api/v1/learning/customers", headers=headers)

    assert refused.status_code == 403
    assert customer.status_code == 200, customer.text
    body = customer.json()
    assert body["invite_code"] == "Ab12Cd34" and body["signup_path"] == "/signup?inviteCode=Ab12Cd34"
    group = (await db.execute(select(UserGroup).where(UserGroup.usergroup_uuid == body["usergroup_uuid"]))).scalars().one()
    assert invites == [(group.org_id, group.id)]
    course = (await db.execute(select(Course).where(Course.course_uuid == body["courses"][0]))).scalars().one()
    assert course.public is False
    link = (await db.execute(select(UserGroupResource).where(UserGroupResource.usergroup_id == group.id))).scalars().one()
    assert link.resource_uuid == course.course_uuid
    assert listed.json() == [{**body, "invite_code": None, "signup_path": None}]
