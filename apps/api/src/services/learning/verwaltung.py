"""Teil B administration: roles, protection rules, invitation links and groups.

Roles map onto what LearnHouse already has: Root is ``user.is_superadmin`` (read from the
database), Admin is ``role_id 1``, Kursleiter ``role_id 3`` and Teilnehmende ``role_id 4`` in
``userorganization``. Rights hold only inside the own provider; Root may act everywhere.

The LearnHouse services for group members, group resources and org removal
(``add_users_to_usergroup``, ``remove_users_from_usergroup``, ``add_resources_to_usergroup``,
``create_usergroup``, ``remove_user_from_org``) run their own request-bound RBAC, which
would refuse a Teilnehmende joining by link or a Kursleiter removing someone. This module
therefore writes the same tables through the same models, after its own rights check.

Only ``sha256(token)`` is stored; the plain token is returned once and never logged.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import IntEnum
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.courses.courses import Course
from src.db.learning.teil_b import LearningGruppe, LearningLink
from src.db.organizations import Organization
from src.db.user_organizations import UserOrganization
from src.db.usergroup_resources import UserGroupResource
from src.db.usergroup_user import UserGroupUser
from src.db.usergroups import UserGroup
from src.db.users import PublicUser, User
from src.services.learning.kurs_kennung import _course_id

LINK_ABGELAUFEN = "Dieser Einladungslink ist abgelaufen."
LINK_ZURUECKGEZOGEN = "Dieser Einladungslink wurde zurückgezogen."
LINK_UNBEKANNT = "Diesen Einladungslink gibt es nicht."
GRUPPE_GESCHLOSSEN = "Diese Gruppe ist geschlossen."
ROOT_BLEIBT = "Das Root-Konto kann nicht entfernt werden."
KEIN_ADMIN_ENTFERNEN = "Kursleiter können keine Admins entfernen."
LETZTER_ADMIN = "Der letzte Admin eines Anbieters kann nicht entfernt werden."
NICHT_ERLAUBT = "Nicht erlaubt."

LINK_GUELTIG = timedelta(days=7)

_LINK_TEXTE = {
    "abgelaufen": LINK_ABGELAUFEN,
    "zurueckgezogen": LINK_ZURUECKGEZOGEN,
    "unbekannt": LINK_UNBEKANNT,
    "gruppe_geschlossen": GRUPPE_GESCHLOSSEN,
}


class Rolle(IntEnum):
    """Value = LearnHouse ``role_id``; ``ROOT`` stands for ``is_superadmin``. Lower ranks higher."""

    ROOT = 0
    ADMIN = 1
    KURSLEITER = 3
    TEILNEHMEND = 4


# Maintainer (2) is elevated in LearnHouse and counts as Kursleiter here; any other role id
# gets the least rights.
_ROLLE_ZU_ROLE_ID = {1: Rolle.ADMIN, 2: Rolle.KURSLEITER, 3: Rolle.KURSLEITER, 4: Rolle.TEILNEHMEND}
_VERWALTEN = (Rolle.ROOT, Rolle.ADMIN, Rolle.KURSLEITER)
_LINK_ROLLE = {"admin": Rolle.ADMIN, "kursleiter": Rolle.KURSLEITER, "gruppe": Rolle.TEILNEHMEND}


class Verweigert(Exception):
    """The acting person may not do this; ``text`` is shown as is (route: 403)."""

    def __init__(self, text: str = NICHT_ERLAUBT) -> None:
        super().__init__(text)
        self.text = text


class LinkUngueltig(Exception):
    """The invitation link cannot be redeemed (route: 410)."""

    def __init__(self, grund: str) -> None:
        self.grund = grund
        self.text = _LINK_TEXTE[grund]
        super().__init__(self.text)


@dataclass(frozen=True)
class Einloesung:
    org_id: int
    rolle: Rolle
    gruppe_id: int | None
    course_id: str | None


@dataclass(frozen=True)
class KursEintrag:
    course_id: str
    course_uuid: str
    titel: str
    gruppen: list[str]


Person = PublicUser | User


def _utc(zeit: datetime | None) -> datetime:
    """``now`` by default; naive times (SQLite drops the zone) count as UTC."""
    if zeit is None:
        return datetime.now(timezone.utc)
    return zeit if zeit.tzinfo is not None else zeit.replace(tzinfo=timezone.utc)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _invalidate_session(user_id: int) -> None:
    from src.routers.users import _invalidate_session_cache

    _invalidate_session_cache(user_id)


async def _ist_root(db: AsyncSession, user_id: int) -> bool:
    return bool(
        (await db.execute(select(User.is_superadmin).where(User.id == user_id))).scalars().first()
    )


async def _mitgliedschaften(db: AsyncSession, user_id: int, org_id: int) -> list[UserOrganization]:
    return list(
        (
            await db.execute(
                select(UserOrganization)
                .where(UserOrganization.user_id == user_id, UserOrganization.org_id == org_id)
                .order_by(UserOrganization.id)
            )
        ).scalars().all()
    )


def _rang(role_id: int | None) -> Rolle:
    return _ROLLE_ZU_ROLE_ID.get(role_id or 0, Rolle.TEILNEHMEND)


async def _rolle_nach_id(db: AsyncSession, user_id: int, org_id: int) -> Rolle | None:
    if await _ist_root(db, user_id):
        return Rolle.ROOT
    mitgliedschaften = await _mitgliedschaften(db, user_id, org_id)
    if not mitgliedschaften:
        return None
    return min(_rang(m.role_id) for m in mitgliedschaften)


async def rolle_von(db: AsyncSession, user: Person, org_id: int) -> Rolle | None:
    """The person's role in this provider; ``None`` means: not a member (and not Root)."""
    return await _rolle_nach_id(db, user.id, org_id)


async def _darf_verwalten(db: AsyncSession, akteur_id: int, org_id: int) -> Rolle:
    rolle = await _rolle_nach_id(db, akteur_id, org_id)
    if rolle not in _VERWALTEN:
        raise Verweigert()
    return rolle


def _neuer_link(
    *, art: str, org_id: int, akteur_id: int, jetzt: datetime, gruppe_id: int | None = None
) -> tuple[LearningLink, str]:
    token = secrets.token_urlsafe(32)
    link = LearningLink(
        token_sha256=_hash(token),
        art=art,
        org_id=org_id,
        gruppe_id=gruppe_id,
        erstellt_von=akteur_id,
        erstellt_am=jetzt,
        laeuft_ab=None if art == "gruppe" else jetzt + LINK_GUELTIG,
    )
    return link, token


async def link_erzeugen(
    db: AsyncSession,
    akteur: Person,
    art: str,
    org_id: int,
    gruppe_id: int | None = None,
    jetzt: datetime | None = None,
) -> tuple[LearningLink, str]:
    """A new admin link (Root only) or Kursleiter link (Admin, Kursleiter of the provider).

    Group links come only from ``gruppe_anlegen``. Returns the record and the plain token."""
    akteur_id = akteur.id
    jetzt = _utc(jetzt)
    if art not in _LINK_ROLLE:
        raise ValueError("unknown link type")
    if art == "gruppe" or gruppe_id is not None:
        raise Verweigert()
    rolle = await _darf_verwalten(db, akteur_id, org_id)
    if art == "admin" and rolle is not Rolle.ROOT:
        raise Verweigert()
    if await db.get(Organization, org_id) is None:
        raise Verweigert()
    link, token = _neuer_link(art=art, org_id=org_id, akteur_id=akteur_id, jetzt=jetzt)
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return link, token


async def gueltiger_link(
    db: AsyncSession, token: str, jetzt: datetime | None = None
) -> tuple[LearningLink, LearningGruppe | None]:
    """The link for this token if it can still be redeemed, else ``LinkUngueltig``."""
    jetzt = _utc(jetzt)
    link = (
        await db.execute(select(LearningLink).where(LearningLink.token_sha256 == _hash(token)))
    ).scalars().first()
    if link is None:
        raise LinkUngueltig("unbekannt")
    if link.zurueckgezogen_am is not None:
        raise LinkUngueltig("zurueckgezogen")
    if link.laeuft_ab is not None and jetzt >= _utc(link.laeuft_ab):
        raise LinkUngueltig("abgelaufen")
    gruppe = None
    if link.art == "gruppe":
        gruppe = await db.get(LearningGruppe, link.gruppe_id) if link.gruppe_id is not None else None
        if gruppe is None:
            raise LinkUngueltig("unbekannt")
        if not gruppe.offen:
            raise LinkUngueltig("gruppe_geschlossen")
    return link, gruppe


async def link_einloesen(
    db: AsyncSession, token: str, user: Person, jetzt: datetime | None = None
) -> Einloesung:
    """Redeem a link: new members get the link's role, members are only ever upgraded.

    A group link also adds the person to the group's ``usergroup``."""
    user_id = user.id
    link, gruppe = await gueltiger_link(db, token, jetzt)
    org_id = link.org_id
    neue_rolle = _LINK_ROLLE[link.art]
    jetzt_text = str(datetime.now())

    mitgliedschaften = await _mitgliedschaften(db, user_id, org_id)
    if not mitgliedschaften:
        db.add(
            UserOrganization(
                user_id=user_id, org_id=org_id, role_id=int(neue_rolle),
                creation_date=jetzt_text, update_date=jetzt_text,
            )
        )
    elif neue_rolle < min(_rang(m.role_id) for m in mitgliedschaften):
        for mitgliedschaft in mitgliedschaften:
            mitgliedschaft.role_id = int(neue_rolle)
            mitgliedschaft.update_date = jetzt_text

    gruppe_id = course_id = None
    if gruppe is not None:
        gruppe_id = gruppe.id
        usergroup_id = gruppe.usergroup_id
        schon_drin = (
            await db.execute(
                select(UserGroupUser.id).where(
                    UserGroupUser.usergroup_id == usergroup_id, UserGroupUser.user_id == user_id
                )
            )
        ).scalars().first()
        if schon_drin is None:
            db.add(
                UserGroupUser(
                    usergroup_id=usergroup_id, user_id=user_id, org_id=org_id,
                    creation_date=jetzt_text, update_date=jetzt_text,
                )
            )
        kurs = await db.get(Course, gruppe.course_id)
        course_id = _course_id(kurs) if kurs is not None else None

    await db.commit()
    _invalidate_session(user_id)
    rolle = await _rolle_nach_id(db, user_id, org_id)
    if rolle is None:  # cannot happen: the person is a member now (Rolle.ROOT is 0, so no `or`)
        rolle = neue_rolle
    return Einloesung(org_id=org_id, rolle=rolle, gruppe_id=gruppe_id, course_id=course_id)


async def link_zurueckziehen(
    db: AsyncSession, akteur: Person, link_id: int, jetzt: datetime | None = None
) -> None:
    """Withdraw a link (admin links: Root only; others: Admin, Kursleiter of the provider)."""
    akteur_id = akteur.id
    jetzt = _utc(jetzt)
    link = await db.get(LearningLink, link_id)
    if link is None:
        raise Verweigert()
    rolle = await _darf_verwalten(db, akteur_id, link.org_id)
    if link.art == "admin" and rolle is not Rolle.ROOT:
        raise Verweigert()
    if link.zurueckgezogen_am is None:
        link.zurueckgezogen_am = jetzt
        await db.commit()


async def gruppe_anlegen(
    db: AsyncSession,
    akteur: Person,
    org_id: int,
    course_uuid: str,
    name: str,
    jetzt: datetime | None = None,
) -> tuple[LearningGruppe, str]:
    """A group for one course of this provider: ``usergroup``, course resource, group link."""
    akteur_id = akteur.id
    jetzt = _utc(jetzt)
    await _darf_verwalten(db, akteur_id, org_id)
    kurs = (
        await db.execute(
            select(Course).where(Course.course_uuid == course_uuid, Course.org_id == org_id)
        )
    ).scalars().first()
    if kurs is None:
        raise Verweigert()
    name = name.strip()
    if not name:
        raise ValueError("group name is empty")

    jetzt_text = str(datetime.now())
    usergroup = UserGroup(
        name=name, description="", org_id=org_id, usergroup_uuid=f"usergroup_{uuid4()}",
        creation_date=jetzt_text, update_date=jetzt_text,
    )
    db.add(usergroup)
    await db.flush()
    db.add(
        UserGroupResource(
            usergroup_id=usergroup.id, resource_uuid=kurs.course_uuid, org_id=org_id,
            creation_date=jetzt_text, update_date=jetzt_text,
        )
    )
    gruppe = LearningGruppe(
        usergroup_id=usergroup.id, course_id=kurs.id, offen=True, erstellt_von=akteur_id,
        erstellt_am=jetzt,
    )
    db.add(gruppe)
    await db.flush()
    link, token = _neuer_link(
        art="gruppe", org_id=org_id, akteur_id=akteur_id, jetzt=jetzt, gruppe_id=gruppe.id
    )
    db.add(link)
    await db.commit()
    await db.refresh(gruppe)
    return gruppe, token


async def _gruppe_mit_org(db: AsyncSession, gruppe_id: int) -> tuple[LearningGruppe, int]:
    zeile = (
        await db.execute(
            select(LearningGruppe, UserGroup.org_id)
            .join(UserGroup, UserGroup.id == LearningGruppe.usergroup_id)
            .where(LearningGruppe.id == gruppe_id)
        )
    ).first()
    if zeile is None:
        raise Verweigert()
    return zeile[0], int(zeile[1])


async def gruppe_schliessen(db: AsyncSession, akteur: Person, gruppe_id: int) -> None:
    """Close a group: its link no longer admits anyone; members keep access."""
    akteur_id = akteur.id
    gruppe, org_id = await _gruppe_mit_org(db, gruppe_id)
    await _darf_verwalten(db, akteur_id, org_id)
    if gruppe.offen:
        gruppe.offen = False
        await db.commit()


async def person_entfernen(db: AsyncSession, akteur: Person, org_id: int, user_id: int) -> None:
    """Remove a person from the provider and all its groups; ``learning_person`` stays.

    Protection rules: Root cannot be removed, a Kursleiter cannot remove an Admin, and the
    last Admin of a provider stays."""
    akteur_id = akteur.id
    akteur_rolle = await _darf_verwalten(db, akteur_id, org_id)
    if await _ist_root(db, user_id):
        raise Verweigert(ROOT_BLEIBT)
    ziel_rolle = await _rolle_nach_id(db, user_id, org_id)
    if ziel_rolle is None:
        raise Verweigert()
    if ziel_rolle is Rolle.ADMIN:
        if akteur_rolle is Rolle.KURSLEITER:
            raise Verweigert(KEIN_ADMIN_ENTFERNEN)
        admins = set(
            (
                await db.execute(
                    select(UserOrganization.user_id).where(
                        UserOrganization.org_id == org_id,
                        UserOrganization.role_id == int(Rolle.ADMIN),
                    )
                )
            ).scalars().all()
        )
        if admins <= {user_id}:
            raise Verweigert(LETZTER_ADMIN)

    gruppen_des_anbieters = select(UserGroup.id).where(UserGroup.org_id == org_id)
    await db.execute(
        delete(UserGroupUser).where(
            UserGroupUser.user_id == user_id,
            UserGroupUser.usergroup_id.in_(gruppen_des_anbieters),
        )
    )
    await db.execute(
        delete(UserOrganization).where(
            UserOrganization.user_id == user_id, UserOrganization.org_id == org_id
        )
    )
    await db.commit()
    _invalidate_session(user_id)


async def kurse_der_person(db: AsyncSession, user: Person) -> list[KursEintrag]:
    """Courses of all the person's providers: published, or assigned to one of her groups."""
    user_id = user.id
    org_ids = set(
        (
            await db.execute(select(UserOrganization.org_id).where(UserOrganization.user_id == user_id))
        ).scalars().all()
    )
    if not org_ids:
        return []

    gruppen: dict[int, list[str]] = {}
    for course_pk, gruppenname in (
        await db.execute(
            select(LearningGruppe.course_id, UserGroup.name)
            .join(UserGroup, UserGroup.id == LearningGruppe.usergroup_id)
            .join(UserGroupUser, UserGroupUser.usergroup_id == UserGroup.id)
            .where(UserGroupUser.user_id == user_id, UserGroup.org_id.in_(org_ids))
        )
    ).all():
        gruppen.setdefault(int(course_pk), []).append(gruppenname)

    kurse = (
        await db.execute(
            select(Course)
            .where(Course.org_id.in_(org_ids))
            .where(Course.published.is_(True) | Course.id.in_(list(gruppen)))
            .order_by(Course.name, Course.id)
        )
    ).scalars().all()

    eintraege: list[KursEintrag] = []
    for kurs in kurse:
        try:
            course_id = _course_id(kurs)
        except HTTPException:  # not a Learning course (no stable uuid): not offered
            continue
        eintraege.append(
            KursEintrag(
                course_id=course_id,
                course_uuid=kurs.course_uuid,
                titel=kurs.name,
                gruppen=sorted(gruppen.get(int(kurs.id), [])),
            )
        )
    return eintraege
