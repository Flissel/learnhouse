"""Customers of the learning platform: one usergroup per customer in the one organisation.

LearnHouse OSS serves a single organisation (separate organisations per customer are an
Enterprise feature), so a customer is a usergroup: its courses are private and linked to
the group, which makes them visible to the group's members only, and its invite code puts
whoever signs up with it straight into the group.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.courses.courses import Course
from src.db.usergroup_resources import UserGroupResource
from src.db.usergroup_user import UserGroupUser
from src.db.usergroups import UserGroup, UserGroupCreate
from src.db.users import PublicUser
from src.services.orgs.invites import create_invite_code
from src.services.users.usergroups import add_resources_to_usergroup, create_usergroup

DESCRIPTION_PREFIX = "Kunde: "


class CustomerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=2, max_length=100)]
    course_ids: Annotated[list[str], Field(min_length=1, max_length=50)]


class CustomerRead(BaseModel):
    usergroup_uuid: str
    name: str
    courses: list[str]
    members: int
    invite_code: str | None = None
    signup_path: str | None = None


async def create_customer(
    request: Request,
    db_session: AsyncSession,
    owner: PublicUser,
    org_id: int,
    name: str,
    courses: list[Course],
) -> CustomerRead:
    group = await create_usergroup(
        request, db_session, owner,
        UserGroupCreate(name=name, description=DESCRIPTION_PREFIX + name, org_id=org_id),
    )
    for course in courses:
        # Linked and private: only the customer's members see it (admins always do).
        course.public = False
        db_session.add(course)
    await db_session.commit()
    await add_resources_to_usergroup(
        request, db_session, owner, group.id, ",".join(c.course_uuid for c in courses)
    )
    invite = await create_invite_code(request, org_id, owner, db_session, group.id)
    code = invite["invite_code"]
    return CustomerRead(
        usergroup_uuid=group.usergroup_uuid,
        name=group.name,
        courses=[c.course_uuid for c in courses],
        members=0,
        invite_code=code,
        signup_path=f"/signup?inviteCode={code}",
    )


async def list_customers(db_session: AsyncSession, org_id: int) -> list[CustomerRead]:
    groups = (
        await db_session.execute(
            select(UserGroup)
            .where(UserGroup.org_id == org_id, UserGroup.description.startswith(DESCRIPTION_PREFIX))
            .order_by(UserGroup.id)
        )
    ).scalars().all()
    customers = []
    for group in groups:
        courses = (
            await db_session.execute(
                select(UserGroupResource.resource_uuid).where(UserGroupResource.usergroup_id == group.id)
            )
        ).scalars().all()
        members = (
            await db_session.execute(
                select(func.count()).select_from(UserGroupUser).where(UserGroupUser.usergroup_id == group.id)
            )
        ).scalar_one()
        customers.append(CustomerRead(
            usergroup_uuid=group.usergroup_uuid, name=group.name,
            courses=[c for c in courses if c.startswith("course_")], members=int(members),
        ))
    return customers
