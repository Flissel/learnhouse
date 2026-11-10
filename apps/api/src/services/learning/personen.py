"""Which Learning learner (``actor_id``) a LearnHouse account is.

Each account has one fixed ``actor_id`` in ``learning_person``. The first time a person
practises, the row is created with the former formula ``lh-<org>-<user_uuid>`` (org =
first membership); from then on the stored id counts, even when the memberships change.
The bootstrap route can set it explicitly (e.g. to keep an existing learner's progress).
"""

from __future__ import annotations

import re

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.learning.teil_b import LearningPerson
from src.db.user_organizations import UserOrganization
from src.db.users import PublicUser, User
from src.services.learning.person_token import _ACTOR

_UNSAFE = re.compile(r"[^A-Za-z0-9._:-]")


class KennungVergeben(Exception):
    """The ``actor_id`` already belongs to another account."""


def ist_sichere_kennung(actor_id: str) -> bool:
    """Same rule as the person token, without a trailing newline slipping through ``$``."""
    return _ACTOR.fullmatch(actor_id) is not None


def learner_id(user: PublicUser | User, org_id: int | None) -> str:
    """The former formula; now only used for a person's first stored ``actor_id``."""
    raw = f"lh-{org_id or 0}-{user.user_uuid}"
    return _UNSAFE.sub("-", raw)[:128]


async def _org_of(db_session: AsyncSession, user: PublicUser | User) -> int:
    """The person's organisation, from the server; never taken from the browser."""
    org_id = (
        await db_session.execute(
            select(UserOrganization.org_id).where(UserOrganization.user_id == user.id).order_by(UserOrganization.id)
        )
    ).scalars().first()
    if org_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="no organisation")
    return int(org_id)


async def actor_von(db: AsyncSession, user: PublicUser | User) -> str:
    """The person's fixed ``actor_id``; created from the former formula on first use.

    Commits the new row. Raises ``KennungVergeben`` when the formula id is already fixed
    for another account (two accounts never share a learner)."""
    gespeichert = await db.get(LearningPerson, user.id)
    if gespeichert is not None:
        return gespeichert.actor_id
    kennung = learner_id(user, await _org_of(db, user))
    db.add(LearningPerson(user_id=user.id, actor_id=kennung))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        gespeichert = await db.get(LearningPerson, user.id)
        if gespeichert is not None:  # a parallel first request of the same person won
            return gespeichert.actor_id
        raise KennungVergeben(kennung) from None
    return kennung


async def person_zu_actor(db: AsyncSession, actor_id: str) -> User | None:
    """The account whose fixed ``actor_id`` this is, or ``None``."""
    return (
        await db.execute(
            select(User).join(LearningPerson, LearningPerson.user_id == User.id).where(
                LearningPerson.actor_id == actor_id
            )
        )
    ).scalars().first()


async def zuordnung_setzen(db: AsyncSession, user_id: int, actor_id: str) -> LearningPerson:
    """Fix ``actor_id`` for the account explicitly (bootstrap). Idempotent for the same pair.

    ``LookupError`` for an unknown account, ``ValueError`` for an unsafe id,
    ``KennungVergeben`` when another account already has the id."""
    if not ist_sichere_kennung(actor_id):
        raise ValueError("actor id is not a safe token")
    if await db.get(User, user_id) is None:
        raise LookupError("user not found")
    besitzer = (
        await db.execute(select(LearningPerson.user_id).where(LearningPerson.actor_id == actor_id))
    ).scalars().first()
    if besitzer is not None and besitzer != user_id:
        raise KennungVergeben(actor_id)
    person = await db.get(LearningPerson, user_id)
    if person is None:
        person = LearningPerson(user_id=user_id, actor_id=actor_id)
        db.add(person)
    else:
        person.actor_id = actor_id
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise KennungVergeben(actor_id) from None
    await db.refresh(person)
    return person
