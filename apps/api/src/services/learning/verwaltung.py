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

Group capacity: a group canvas holds only so many folders (Mappen). Joining a group by link is
refused once the group has as many members as the canvas of its course holds; the number comes
from learning-mcp through a ``Kapazitaet`` source the routes pass in. Unknown capacity lets the
person in (fail-open): the Lern-Hülle still refuses a folder that does not fit.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import IntEnum
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.courses.courses import Course
from src.db.learning.teil_b import LearningEntfernung, LearningGruppe, LearningLink
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


def gruppe_voll_text(hoechstens: int) -> str:
    personen = "Person" if hoechstens == 1 else "Personen"
    return f"Diese Gruppe ist voll (höchstens {hoechstens} {personen}). Bitte wenden Sie sich an Ihre Kursleitung."


# Learning ``course_id`` -> places of a new group canvas of that course; ``None``: unknown.
Kapazitaet = Callable[[str], Awaitable[int | None]]

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
    """The invitation link cannot be redeemed (route: 410). ``voll`` carries the group's limit."""

    def __init__(self, grund: str, *, hoechstens: int | None = None) -> None:
        self.grund = grund
        if grund == "voll":
            if hoechstens is None:
                raise ValueError("a full group names its limit")
            self.text = gruppe_voll_text(hoechstens)
        else:
            self.text = _LINK_TEXTE[grund]
        super().__init__(self.text)


@dataclass(frozen=True)
class Einloesung:
    org_id: int
    rolle: Rolle
    gruppe_id: int | None
    course_id: str | None


@dataclass(frozen=True)
class GruppeKurz:
    id: int
    name: str


@dataclass(frozen=True)
class KursEintrag:
    course_id: str
    course_uuid: str
    titel: str
    gruppen: list[GruppeKurz]
    org_id: int


@dataclass(frozen=True)
class GruppePerson:
    mitglied: bool
    offen: bool
    course_id: str
    gruppe_name: str
    anzeigename: str | None


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


async def _in_gruppe(db: AsyncSession, gruppe: LearningGruppe, user_id: int) -> bool:
    return (
        await db.execute(
            select(UserGroupUser.id).where(
                UserGroupUser.usergroup_id == gruppe.usergroup_id, UserGroupUser.user_id == user_id
            ).limit(1)
        )
    ).scalars().first() is not None


async def mitglieder_zahl(db: AsyncSession, gruppe: LearningGruppe) -> int:
    """Members of the group as ``gruppe_person`` counts them: in its usergroup and in its provider."""
    return int(
        (
            await db.execute(
                select(func.count(func.distinct(UserGroupUser.user_id)))
                .join(UserGroup, UserGroup.id == UserGroupUser.usergroup_id)
                .join(
                    UserOrganization,
                    (UserOrganization.user_id == UserGroupUser.user_id)
                    & (UserOrganization.org_id == UserGroup.org_id),
                )
                .where(UserGroupUser.usergroup_id == gruppe.usergroup_id)
            )
        ).scalar_one()
    )


async def gruppen_kapazitaet(
    db: AsyncSession, gruppe: LearningGruppe, kapazitaet: Kapazitaet | None
) -> int | None:
    """Places of the group's canvas from ``kapazitaet``; ``None`` when unknown (no source, no Learning course)."""
    if kapazitaet is None:
        return None
    kurs = await db.get(Course, gruppe.course_id)
    if kurs is None:
        return None
    try:
        course_id = _course_id(kurs)
    except HTTPException:  # not a Learning course
        return None
    return await kapazitaet(course_id)


async def platz_pruefen(
    db: AsyncSession, gruppe: LearningGruppe | None, user_id: int | None, kapazitaet: Kapazitaet | None
) -> None:
    """``LinkUngueltig("voll")`` when a NEW member would join a group that already has as many members
    as its canvas holds. Members (``user_id`` in the group) are never refused; unknown capacity lets in."""
    if gruppe is None or kapazitaet is None:
        return
    if user_id is not None and await _in_gruppe(db, gruppe, user_id):
        return
    hoechstens = await gruppen_kapazitaet(db, gruppe, kapazitaet)
    if hoechstens is not None and await mitglieder_zahl(db, gruppe) >= hoechstens:
        raise LinkUngueltig("voll", hoechstens=hoechstens)


async def link_einloesen(
    db: AsyncSession,
    token: str,
    user: Person,
    jetzt: datetime | None = None,
    kapazitaet: Kapazitaet | None = None,
) -> Einloesung:
    """Redeem a link: new members get the link's role, members are only ever upgraded.

    A group link also adds the person to the group's ``usergroup``, unless the group is full
    (``kapazitaet``, checked before anything is written)."""
    user_id = user.id
    link, gruppe = await gueltiger_link(db, token, jetzt)
    org_id = link.org_id
    # A link created before the person's removal from this provider does not readmit her.
    vermerk = await db.get(LearningEntfernung, (user_id, org_id))
    if vermerk is not None and _utc(vermerk.entfernt_am) >= _utc(link.erstellt_am):
        raise LinkUngueltig("zurueckgezogen")
    await platz_pruefen(db, gruppe, user_id, kapazitaet)
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
    try:
        _course_id(kurs)  # only courses with a stable Learning id; checked before any write
    except HTTPException:
        raise Verweigert() from None
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


async def person_entfernen(
    db: AsyncSession, akteur: Person, org_id: int, user_id: int, jetzt: datetime | None = None
) -> None:
    """Remove a person from the provider and all its groups; ``learning_person`` stays.

    Protection rules: Root cannot be removed, a Kursleiter cannot remove an Admin, and the
    last Admin of a provider stays. A removal note (``learning_entfernung``) keeps links
    created before the removal from readmitting her; a link created afterwards does."""
    akteur_id = akteur.id
    jetzt = _utc(jetzt)
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
    vermerk = await db.get(LearningEntfernung, (user_id, org_id))
    if vermerk is None:
        db.add(LearningEntfernung(user_id=user_id, org_id=org_id, entfernt_am=jetzt))
    else:
        vermerk.entfernt_am = jetzt
    await db.commit()
    _invalidate_session(user_id)


@dataclass(frozen=True)
class AnbieterRolle:
    org_id: int
    org_name: str
    rolle: Rolle


@dataclass(frozen=True)
class LinkEintrag:
    """An active link as the administration sees it; the token is never stored or shown."""

    link_id: int
    art: str
    gruppe_id: int | None
    gruppe: str | None
    erstellt_am: datetime
    laeuft_ab: datetime | None
    mitglieder: int | None = None  # group links: members now
    kapazitaet: int | None = None  # group links: places of the canvas, None when unknown


@dataclass(frozen=True)
class PersonEintrag:
    """A member of a provider, without e-mail address."""

    user_id: int
    anzeigename: str
    rolle: Rolle
    gruppen: list[str]


async def ist_root(db: AsyncSession, user: Person) -> bool:
    """``is_superadmin`` as stored in the database (never taken from a token or the browser)."""
    return await _ist_root(db, user.id)


async def rollen_der_person(db: AsyncSession, user: Person) -> list[AnbieterRolle]:
    """The person's role per provider; Root gets every provider as Root."""
    user_id = user.id
    if await _ist_root(db, user_id):
        anbieter = (await db.execute(select(Organization).order_by(Organization.id))).scalars().all()
        return [AnbieterRolle(org_id=int(o.id), org_name=o.name, rolle=Rolle.ROOT) for o in anbieter]
    rang: dict[int, Rolle] = {}
    namen: dict[int, str] = {}
    for org_id, org_name, role_id in (
        await db.execute(
            select(UserOrganization.org_id, Organization.name, UserOrganization.role_id)
            .join(Organization, Organization.id == UserOrganization.org_id)
            .where(UserOrganization.user_id == user_id)
        )
    ).all():
        org_id = int(org_id)
        rang[org_id] = min(rang.get(org_id, Rolle.TEILNEHMEND), _rang(role_id))
        namen[org_id] = org_name
    return [AnbieterRolle(org_id=o, org_name=namen[o], rolle=rang[o]) for o in sorted(rang)]


async def aktive_links(
    db: AsyncSession,
    akteur: Person,
    org_id: int,
    jetzt: datetime | None = None,
    kapazitaet: Kapazitaet | None = None,
) -> list[LinkEintrag]:
    """Links of the provider that still admit someone (admin links: shown to Root only).

    Group links carry the number of members and, from ``kapazitaet``, how many the canvas holds."""
    akteur_id = akteur.id
    jetzt = _utc(jetzt)
    rolle = await _darf_verwalten(db, akteur_id, org_id)
    zeilen = (
        await db.execute(
            select(LearningLink, UserGroup.name, LearningGruppe.offen)
            .outerjoin(LearningGruppe, LearningGruppe.id == LearningLink.gruppe_id)
            .outerjoin(UserGroup, UserGroup.id == LearningGruppe.usergroup_id)
            .where(LearningLink.org_id == org_id, LearningLink.zurueckgezogen_am.is_(None))
            .order_by(LearningLink.id)
        )
    ).all()
    eintraege: list[LinkEintrag] = []
    plaetze: dict[int, int | None] = {}  # per course: one question to learning-mcp per listing
    for link, gruppenname, offen in zeilen:
        if link.laeuft_ab is not None and jetzt >= _utc(link.laeuft_ab):
            continue
        if link.art == "gruppe" and not offen:
            continue
        if link.art == "admin" and rolle is not Rolle.ROOT:
            continue
        mitglieder = hoechstens = None
        gruppe = await db.get(LearningGruppe, link.gruppe_id) if link.gruppe_id is not None else None
        if gruppe is not None:
            mitglieder = await mitglieder_zahl(db, gruppe)
            if gruppe.course_id not in plaetze:
                plaetze[gruppe.course_id] = await gruppen_kapazitaet(db, gruppe, kapazitaet)
            hoechstens = plaetze[gruppe.course_id]
        eintraege.append(
            LinkEintrag(
                link_id=int(link.id), art=link.art, gruppe_id=link.gruppe_id, gruppe=gruppenname,
                erstellt_am=_utc(link.erstellt_am),
                laeuft_ab=_utc(link.laeuft_ab) if link.laeuft_ab is not None else None,
                mitglieder=mitglieder, kapazitaet=hoechstens,
            )
        )
    return eintraege


def _anzeigename(user: User) -> str:
    return f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username


async def personen_des_anbieters(db: AsyncSession, akteur: Person, org_id: int) -> list[PersonEintrag]:
    """Members of the provider with role and Teil-B groups; for Root, Admin, Kursleiter."""
    akteur_id = akteur.id
    await _darf_verwalten(db, akteur_id, org_id)
    rang: dict[int, Rolle] = {}
    konten: dict[int, User] = {}
    for konto, role_id in (
        await db.execute(
            select(User, UserOrganization.role_id)
            .join(UserOrganization, UserOrganization.user_id == User.id)
            .where(UserOrganization.org_id == org_id)
        )
    ).all():
        konten[int(konto.id)] = konto
        rang[int(konto.id)] = min(rang.get(int(konto.id), Rolle.TEILNEHMEND), _rang(role_id))
    root_ids = {i for i, konto in konten.items() if konto.is_superadmin}

    gruppen: dict[int, list[str]] = {}
    for user_id, gruppenname in (
        await db.execute(
            select(UserGroupUser.user_id, UserGroup.name)
            .join(UserGroup, UserGroup.id == UserGroupUser.usergroup_id)
            .join(LearningGruppe, LearningGruppe.usergroup_id == UserGroup.id)
            .where(UserGroup.org_id == org_id)
        )
    ).all():
        gruppen.setdefault(int(user_id), []).append(gruppenname)

    return [
        PersonEintrag(
            user_id=i,
            anzeigename=_anzeigename(konten[i]),
            rolle=Rolle.ROOT if i in root_ids else rang[i],
            gruppen=sorted(gruppen.get(i, [])),
        )
        for i in sorted(konten, key=lambda k: (_anzeigename(konten[k]).casefold(), k))
    ]


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

    gruppen: dict[int, list[GruppeKurz]] = {}
    for course_pk, gruppe_id, gruppenname in (
        await db.execute(
            select(LearningGruppe.course_id, LearningGruppe.id, UserGroup.name)
            .join(UserGroup, UserGroup.id == LearningGruppe.usergroup_id)
            .join(UserGroupUser, UserGroupUser.usergroup_id == UserGroup.id)
            .where(UserGroupUser.user_id == user_id, UserGroup.org_id.in_(org_ids))
        )
    ).all():
        gruppen.setdefault(int(course_pk), []).append(GruppeKurz(id=int(gruppe_id), name=gruppenname))

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
                gruppen=sorted(gruppen.get(int(kurs.id), []), key=lambda g: (g.name, g.id)),
                org_id=int(kurs.org_id),
            )
        )
    return eintraege


async def gruppe_person(db: AsyncSession, gruppe_id: int, user: Person) -> GruppePerson | None:
    """Is ``user`` a member of the group? ``None`` for an unknown group.

    Member means a ``usergroup_user`` row plus a ``userorganization`` row in the group's provider,
    whether or not the group is still open."""
    zeile = (
        await db.execute(
            select(LearningGruppe, UserGroup.name, UserGroup.org_id)
            .join(UserGroup, UserGroup.id == LearningGruppe.usergroup_id)
            .where(LearningGruppe.id == gruppe_id)
        )
    ).first()
    if zeile is None:
        return None
    gruppe, gruppenname, org_id = zeile
    kurs = await db.get(Course, gruppe.course_id)
    if kurs is None:
        return None
    try:
        course_id = _course_id(kurs)
    except HTTPException:  # not a Learning course
        return None
    eintrag = (
        await db.execute(
            select(UserGroupUser.id)
            .where(UserGroupUser.usergroup_id == gruppe.usergroup_id, UserGroupUser.user_id == user.id)
            .limit(1)
        )
    ).scalars().first()
    # LearnHouse's own removal drops only the userorganization row: belonging to the provider counts too.
    im_anbieter = (
        await db.execute(
            select(UserOrganization.id)
            .where(UserOrganization.user_id == user.id, UserOrganization.org_id == org_id)
            .limit(1)
        )
    ).scalars().first()
    konto = await db.get(User, user.id)
    return GruppePerson(
        mitglied=eintrag is not None and im_anbieter is not None, offen=bool(gruppe.offen), course_id=course_id,
        gruppe_name=gruppenname, anzeigename=_anzeigename(konto) if konto is not None else None,
    )
