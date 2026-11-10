"""Teil B: roles, protection rules, invitation links and groups (service layer)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from src.db.courses.courses import Course
from src.db.learning.teil_b import LearningGruppe, LearningLink, LearningPerson
from src.db.roles import Role, RoleTypeEnum
from src.db.user_organizations import UserOrganization
from src.db.usergroup_resources import UserGroupResource
from src.db.usergroup_user import UserGroupUser
from src.db.usergroups import UserGroup
from src.db.users import PublicUser, User
from src.services.learning.kurs_kennung import _course_id
from src.services.learning.personen import actor_von
from src.services.learning.verwaltung import (
    GRUPPE_GESCHLOSSEN,
    KEIN_ADMIN_ENTFERNEN,
    LETZTER_ADMIN,
    LINK_ABGELAUFEN,
    LINK_UNBEKANNT,
    LINK_ZURUECKGEZOGEN,
    NICHT_ERLAUBT,
    ROOT_BLEIBT,
    LinkUngueltig,
    Rolle,
    Verweigert,
    gruppe_anlegen,
    gruppe_schliessen,
    kurse_der_person,
    link_einloesen,
    link_erzeugen,
    link_zurueckziehen,
    person_entfernen,
    rolle_von,
)

pytestmark = pytest.mark.asyncio

T0 = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


async def _rolle_anlegen(db, org, role_id: int, name: str) -> None:
    now = str(datetime.now())
    db.add(Role(id=role_id, name=name, org_id=org.id, role_type=RoleTypeEnum.TYPE_ORGANIZATION,
                role_uuid=f"role_{name.lower()}", rights={}, creation_date=now, update_date=now))
    await db.commit()


@pytest.fixture
async def rollen(db, org):
    await _rolle_anlegen(db, org, 1, "Admin")
    await _rolle_anlegen(db, org, 3, "Instructor")
    await _rolle_anlegen(db, org, 4, "User")


async def _konto(db, user_id: int, name: str, *, org_id: int | None = None, role_id: int | None = None,
                 superadmin: bool = False) -> PublicUser:
    now = str(datetime.now())
    db.add(User(id=user_id, username=name, first_name=name, last_name="Test", email=f"{name}@example.com",
                password="hashed_password", user_uuid=f"user_{name}", is_superadmin=superadmin,
                creation_date=now, update_date=now))
    await db.commit()
    if org_id is not None:
        db.add(UserOrganization(user_id=user_id, org_id=org_id, role_id=role_id,
                                creation_date=now, update_date=now))
        await db.commit()
    return PublicUser(id=user_id, username=name, first_name=name, last_name="Test",
                      email=f"{name}@example.com", user_uuid=f"user_{name}", is_superadmin=superadmin)


@pytest.fixture
async def org2(other_org):
    return other_org


@pytest.fixture
async def leute(db, org, org2, rollen) -> dict[str, PublicUser]:
    return {
        "root": await _konto(db, 21, "root-konto", superadmin=True),
        "admin_a": await _konto(db, 22, "admin-a", org_id=org.id, role_id=1),
        "admin_a2": await _konto(db, 23, "admin-a2", org_id=org.id, role_id=1),
        "leiter_a": await _konto(db, 24, "leiter-a", org_id=org.id, role_id=3),
        "person_a": await _konto(db, 25, "person-a", org_id=org.id, role_id=4),
        "leiter_b": await _konto(db, 26, "leiter-b", org_id=org2.id, role_id=3),
        "neu": await _konto(db, 30, "person-b"),
        "neu2": await _konto(db, 31, "person-c"),
    }


async def _kurs(db, course_id: int, org_id: int, name: str, nummer: int, *, published: bool) -> Course:
    now = str(datetime.now())
    kurs = Course(id=course_id, name=name, public=False, published=published, open_to_contributors=False,
                  org_id=org_id, course_uuid=f"course_00000000-0000-4000-8000-{nummer:012d}",
                  creation_date=now, update_date=now)
    db.add(kurs)
    await db.commit()
    await db.refresh(kurs)
    return kurs


@pytest.fixture
async def kurs_a(db, org) -> Course:
    return await _kurs(db, 101, org.id, "Kurs A", 1, published=True)


@pytest.fixture
async def kurs_intern(db, org) -> Course:
    return await _kurs(db, 102, org.id, "Kurs Intern", 2, published=False)


@pytest.fixture
async def kurs_entwurf(db, org) -> Course:
    return await _kurs(db, 103, org.id, "Kurs Entwurf", 3, published=False)


@pytest.fixture
async def kurs_b(db, org2) -> Course:
    return await _kurs(db, 201, org2.id, "Kurs B", 4, published=True)


async def _anzahl(db, model) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def _in_gruppe(db, user_id: int, gruppe: LearningGruppe) -> bool:
    return (await db.execute(select(UserGroupUser).where(
        UserGroupUser.user_id == user_id, UserGroupUser.usergroup_id == gruppe.usergroup_id
    ))).scalars().first() is not None


async def test_rolle_von(db, org, org2, leute) -> None:
    assert await rolle_von(db, leute["root"], org.id) is Rolle.ROOT
    assert await rolle_von(db, leute["root"], org2.id) is Rolle.ROOT
    assert await rolle_von(db, leute["admin_a"], org.id) is Rolle.ADMIN
    assert await rolle_von(db, leute["leiter_a"], org.id) is Rolle.KURSLEITER
    assert await rolle_von(db, leute["person_a"], org.id) is Rolle.TEILNEHMEND
    assert await rolle_von(db, leute["person_a"], org2.id) is None
    assert await rolle_von(db, leute["neu"], org.id) is None


async def test_schutzregeln(db, org, leute) -> None:
    root, admin_a, admin_a2, leiter_a = leute["root"], leute["admin_a"], leute["admin_a2"], leute["leiter_a"]

    with pytest.raises(Verweigert, match=ROOT_BLEIBT) as e:
        await person_entfernen(db, admin_a, org.id, root.id)
    assert e.value.text == "Das Root-Konto kann nicht entfernt werden."
    with pytest.raises(Verweigert) as e:
        await person_entfernen(db, leiter_a, org.id, admin_a.id)
    assert e.value.text == "Kursleiter können keine Admins entfernen."
    assert await rolle_von(db, admin_a, org.id) is Rolle.ADMIN

    await person_entfernen(db, admin_a, org.id, admin_a2.id)
    assert await rolle_von(db, admin_a2, org.id) is None

    with pytest.raises(Verweigert) as e:
        await person_entfernen(db, root, org.id, admin_a.id)
    assert e.value.text == "Der letzte Admin eines Anbieters kann nicht entfernt werden."
    with pytest.raises(Verweigert, match=LETZTER_ADMIN):
        await person_entfernen(db, admin_a, org.id, admin_a.id)
    assert await rolle_von(db, admin_a, org.id) is Rolle.ADMIN

    # A Kursleiter may remove Kursleiter and Teilnehmende of the own provider.
    await person_entfernen(db, leiter_a, org.id, leute["person_a"].id)
    assert await rolle_von(db, leute["person_a"], org.id) is None
    assert KEIN_ADMIN_ENTFERNEN == "Kursleiter können keine Admins entfernen."


async def test_teilnehmende_duerfen_nichts_verwalten(db, org, leute, kurs_a) -> None:
    person_a = leute["person_a"]
    for aufruf in (lambda: person_entfernen(db, person_a, org.id, leute["leiter_a"].id),
                   lambda: gruppe_anlegen(db, person_a, org.id, kurs_a.course_uuid, "G"),
                   lambda: link_erzeugen(db, person_a, "kursleiter", org.id),
                   lambda: person_entfernen(db, leute["neu"], org.id, person_a.id)):
        with pytest.raises(Verweigert) as e:
            await aufruf()
        assert e.value.text == NICHT_ERLAUBT == "Nicht erlaubt."
    assert await _anzahl(db, LearningLink) == await _anzahl(db, LearningGruppe) == 0
    assert await rolle_von(db, leute["leiter_a"], org.id) is Rolle.KURSLEITER


async def test_rechte_nur_im_eigenen_anbieter(db, org, org2, leute, kurs_a, kurs_b) -> None:
    leiter_a, leiter_b, person_a = leute["leiter_a"], leute["leiter_b"], leute["person_a"]
    gruppe, _ = await gruppe_anlegen(db, leiter_a, org.id, kurs_a.course_uuid, "Montag")
    link, _ = await link_erzeugen(db, leiter_a, "kursleiter", org.id, jetzt=T0)
    gruppen_vorher, links_vorher = await _anzahl(db, UserGroup), await _anzahl(db, LearningLink)

    for aufruf in (lambda: person_entfernen(db, leiter_b, org.id, person_a.id),
                   lambda: gruppe_anlegen(db, leiter_b, org.id, kurs_a.course_uuid, "G"),
                   lambda: gruppe_anlegen(db, leiter_a, org.id, kurs_b.course_uuid, "G"),
                   lambda: gruppe_anlegen(db, leiter_b, org2.id, kurs_a.course_uuid, "G"),
                   lambda: link_erzeugen(db, leiter_b, "kursleiter", org.id),
                   lambda: link_zurueckziehen(db, leiter_b, link.id),
                   lambda: gruppe_schliessen(db, leiter_b, gruppe.id)):
        with pytest.raises(Verweigert):
            await aufruf()

    assert await rolle_von(db, person_a, org.id) is Rolle.TEILNEHMEND
    assert await _anzahl(db, UserGroup) == gruppen_vorher
    assert await _anzahl(db, LearningLink) == links_vorher
    await db.refresh(link)
    await db.refresh(gruppe)
    assert link.zurueckgezogen_am is None and gruppe.offen is True


async def test_root_darf_in_jedem_anbieter(db, org2, leute, kurs_b) -> None:
    root = leute["root"]
    gruppe, _ = await gruppe_anlegen(db, root, org2.id, kurs_b.course_uuid, "Dienstag")
    link, _ = await link_erzeugen(db, root, "kursleiter", org2.id)
    await link_zurueckziehen(db, root, link.id)
    await gruppe_schliessen(db, root, gruppe.id)
    await person_entfernen(db, root, org2.id, leute["leiter_b"].id)

    assert await rolle_von(db, leute["leiter_b"], org2.id) is None
    await db.refresh(gruppe)
    assert gruppe.offen is False


async def test_link_einloesen_faelle(db, org, leute, kurs_a) -> None:
    admin_a, person_a, neu, neu2 = leute["admin_a"], leute["person_a"], leute["neu"], leute["neu2"]
    link, t = await link_erzeugen(db, admin_a, "kursleiter", org.id, jetzt=T0)

    eingeloest = await link_einloesen(db, t, neu, jetzt=T0 + timedelta(days=6, hours=23))
    assert eingeloest.rolle is Rolle.KURSLEITER
    assert (eingeloest.org_id, eingeloest.gruppe_id, eingeloest.course_id) == (org.id, None, None)
    assert await rolle_von(db, neu, org.id) is Rolle.KURSLEITER

    with pytest.raises(LinkUngueltig) as e:
        await link_einloesen(db, t, neu2, jetzt=T0 + timedelta(days=7, seconds=1))
    assert e.value.text == "Dieser Einladungslink ist abgelaufen." == LINK_ABGELAUFEN
    assert e.value.grund == "abgelaufen"
    assert await rolle_von(db, neu2, org.id) is None
    # Also an existing member: the expired link changes nothing.
    with pytest.raises(LinkUngueltig, match=LINK_ABGELAUFEN):
        await link_einloesen(db, t, person_a, jetzt=T0 + timedelta(days=8))
    assert await rolle_von(db, person_a, org.id) is Rolle.TEILNEHMEND

    # An admin is never downgraded by a Kursleiter link.
    assert (await link_einloesen(db, t, admin_a, jetzt=T0)).rolle is Rolle.ADMIN
    assert await rolle_von(db, admin_a, org.id) is Rolle.ADMIN

    # Withdrawn: own message, no membership, no change for members.
    await link_zurueckziehen(db, admin_a, link.id, jetzt=T0 + timedelta(hours=1))
    with pytest.raises(LinkUngueltig) as e:
        await link_einloesen(db, t, neu2, jetzt=T0 + timedelta(hours=2))
    assert (e.value.grund, e.value.text) == ("zurueckgezogen", "Dieser Einladungslink wurde zurückgezogen.")
    assert e.value.text == LINK_ZURUECKGEZOGEN
    with pytest.raises(LinkUngueltig, match=LINK_ZURUECKGEZOGEN):
        await link_einloesen(db, t, person_a, jetzt=T0 + timedelta(hours=2))
    assert await rolle_von(db, neu2, org.id) is None
    assert await rolle_von(db, person_a, org.id) is Rolle.TEILNEHMEND

    # Unknown token.
    with pytest.raises(LinkUngueltig) as e:
        await link_einloesen(db, "gibt-es-nicht", neu2, jetzt=T0)
    assert (e.value.grund, e.value.text) == ("unbekannt", "Diesen Einladungslink gibt es nicht.")
    assert e.value.text == LINK_UNBEKANNT
    assert await rolle_von(db, neu2, org.id) is None

    # Closed group.
    gruppe, gt = await gruppe_anlegen(db, admin_a, org.id, kurs_a.course_uuid, "Montag", jetzt=T0)
    await gruppe_schliessen(db, admin_a, gruppe.id)
    with pytest.raises(LinkUngueltig) as e:
        await link_einloesen(db, gt, neu2, jetzt=T0)
    assert (e.value.grund, e.value.text) == ("gruppe_geschlossen", "Diese Gruppe ist geschlossen.")
    assert e.value.text == GRUPPE_GESCHLOSSEN
    assert await rolle_von(db, neu2, org.id) is None
    assert not await _in_gruppe(db, neu2.id, gruppe)


async def test_root_bleibt_root_beim_einloesen(db, org, leute) -> None:
    _, t = await link_erzeugen(db, leute["admin_a"], "kursleiter", org.id, jetzt=T0)
    assert (await link_einloesen(db, t, leute["root"], jetzt=T0)).rolle is Rolle.ROOT


async def test_link_stuft_nur_herauf(db, org, leute) -> None:
    person_a, leiter_a = leute["person_a"], leute["leiter_a"]
    _, t = await link_erzeugen(db, leiter_a, "kursleiter", org.id, jetzt=T0)

    assert (await link_einloesen(db, t, person_a, jetzt=T0)).rolle is Rolle.KURSLEITER
    assert await rolle_von(db, person_a, org.id) is Rolle.KURSLEITER
    mitgliedschaften = (await db.execute(select(UserOrganization).where(
        UserOrganization.user_id == person_a.id, UserOrganization.org_id == org.id))).scalars().all()
    assert [m.role_id for m in mitgliedschaften] == [3]


async def test_gruppen_link_macht_mitglied_und_nennt_kurs(db, org, leute, kurs_a) -> None:
    leiter_a, person_neu = leute["leiter_a"], leute["neu"]
    g, t = await gruppe_anlegen(db, leiter_a, org.id, kurs_a.course_uuid, "Montag", jetzt=T0)

    e = await link_einloesen(db, t, person_neu, jetzt=T0 + timedelta(days=30))
    assert e.gruppe_id == g.id and e.course_id == _course_id(kurs_a)
    assert e.course_id == kurs_a.course_uuid.removeprefix("course_")
    assert e.rolle is Rolle.TEILNEHMEND and e.org_id == org.id
    assert await _in_gruppe(db, person_neu.id, g)

    # Redeeming twice keeps one group membership; a Kursleiter keeps the role.
    await link_einloesen(db, t, person_neu, jetzt=T0)
    assert (await link_einloesen(db, t, leiter_a, jetzt=T0)).rolle is Rolle.KURSLEITER
    zeilen = (await db.execute(select(UserGroupUser).where(
        UserGroupUser.usergroup_id == g.usergroup_id))).scalars().all()
    assert sorted(z.user_id for z in zeilen) == [leiter_a.id, person_neu.id]

    usergroup = await db.get(UserGroup, g.usergroup_id)
    assert usergroup.name == "Montag" and usergroup.org_id == org.id
    ressourcen = (await db.execute(select(UserGroupResource.resource_uuid).where(
        UserGroupResource.usergroup_id == g.usergroup_id))).scalars().all()
    assert ressourcen == [kurs_a.course_uuid]
    assert g.course_id == kurs_a.id and g.offen is True and g.erstellt_von == leiter_a.id
    link = (await db.execute(select(LearningLink).where(LearningLink.gruppe_id == g.id))).scalars().one()
    assert (link.art, link.org_id, link.laeuft_ab) == ("gruppe", org.id, None)


async def test_nur_root_erzeugt_admin_links(db, org, leute) -> None:
    for akteur in (leute["admin_a"], leute["leiter_a"], leute["person_a"]):
        with pytest.raises(Verweigert):
            await link_erzeugen(db, akteur, "admin", org.id)
    with pytest.raises(Verweigert):
        await link_erzeugen(db, leute["admin_a"], "gruppe", org.id)
    assert await _anzahl(db, LearningLink) == 0

    link, t = await link_erzeugen(db, leute["root"], "admin", org.id, jetzt=T0)
    assert link.art == "admin" and link.erstellt_von == leute["root"].id
    assert link.laeuft_ab.replace(tzinfo=timezone.utc) == T0 + timedelta(days=7)
    with pytest.raises(Verweigert):
        await link_zurueckziehen(db, leute["admin_a"], link.id)
    assert (await link_einloesen(db, t, leute["neu"], jetzt=T0)).rolle is Rolle.ADMIN
    assert await rolle_von(db, leute["neu"], org.id) is Rolle.ADMIN


async def test_token_wird_nur_als_hash_gespeichert(db, org, leute) -> None:
    link, t = await link_erzeugen(db, leute["admin_a"], "kursleiter", org.id)
    assert link.token_sha256 == hashlib.sha256(t.encode()).hexdigest() and t not in repr(link.__dict__)
    assert len(t) >= 43
    gespeichert = (await db.execute(select(LearningLink))).scalars().one()
    assert t not in repr(gespeichert.__dict__)


async def test_kurse_der_person(db, org, org2, leute, kurs_a, kurs_intern, kurs_entwurf, kurs_b) -> None:
    person_a, leiter_a = leute["person_a"], leute["leiter_a"]
    g, t = await gruppe_anlegen(db, leiter_a, org.id, kurs_intern.course_uuid, "Montag")
    await link_einloesen(db, t, person_a)

    kurse = await kurse_der_person(db, person_a)
    assert [(k.course_id, k.course_uuid, k.titel, k.gruppen) for k in kurse] == [
        (_course_id(kurs_a), kurs_a.course_uuid, "Kurs A", []),
        (_course_id(kurs_intern), kurs_intern.course_uuid, "Kurs Intern", ["Montag"]),
    ]
    # Another provider's courses are never listed; without a group, unpublished stays hidden.
    assert [k.org_id for k in kurse] == [org.id, org.id]
    assert [(k.titel, k.org_id) for k in await kurse_der_person(db, leute["leiter_b"])] == [("Kurs B", org2.id)]
    assert [k.titel for k in await kurse_der_person(db, leiter_a)] == ["Kurs A"]
    assert await kurse_der_person(db, leute["neu"]) == []


async def test_entfernte_person_behaelt_zuordnung(db, org, leute, kurs_intern) -> None:
    person_a, leiter_a = leute["person_a"], leute["leiter_a"]
    kennung = await actor_von(db, person_a)
    g, t = await gruppe_anlegen(db, leiter_a, org.id, kurs_intern.course_uuid, "Montag")
    await link_einloesen(db, t, person_a)
    assert await _in_gruppe(db, person_a.id, g)

    await person_entfernen(db, leiter_a, org.id, person_a.id)

    assert await rolle_von(db, person_a, org.id) is None
    assert not await _in_gruppe(db, person_a.id, g)
    assert await kurse_der_person(db, person_a) == []
    assert (await db.get(LearningPerson, person_a.id)).actor_id == kennung
    assert await db.get(User, person_a.id) is not None


async def _zeilen(db) -> dict[str, int]:
    return {model.__name__: await _anzahl(db, model)
            for model in (UserOrganization, UserGroupUser, UserGroup, LearningGruppe, LearningLink)}


async def test_entfernte_person_kommt_mit_altem_link_nicht_zurueck(db, org, leute, kurs_intern) -> None:
    person_a, leiter_a, neu = leute["person_a"], leute["leiter_a"], leute["neu"]
    g, gruppen_token = await gruppe_anlegen(db, leiter_a, org.id, kurs_intern.course_uuid, "Montag", jetzt=T0)
    _, leiter_token = await link_erzeugen(db, leiter_a, "kursleiter", org.id, jetzt=T0)
    await link_einloesen(db, gruppen_token, person_a, jetzt=T0)

    await person_entfernen(db, leiter_a, org.id, person_a.id, jetzt=T0 + timedelta(hours=1))
    vorher = await _zeilen(db)

    for token in (gruppen_token, leiter_token):
        with pytest.raises(LinkUngueltig) as e:
            await link_einloesen(db, token, person_a, jetzt=T0 + timedelta(hours=2))
        assert (e.value.grund, e.value.text) == ("zurueckgezogen", LINK_ZURUECKGEZOGEN)
    assert await _zeilen(db) == vorher
    assert await rolle_von(db, person_a, org.id) is None
    assert not await _in_gruppe(db, person_a.id, g)

    # Everyone else keeps using the old group link.
    e = await link_einloesen(db, gruppen_token, neu, jetzt=T0 + timedelta(hours=2))
    assert e.rolle is Rolle.TEILNEHMEND and await _in_gruppe(db, neu.id, g)


async def test_neu_erstellter_link_holt_entfernte_person_zurueck(db, org, leute, kurs_intern) -> None:
    person_a, leiter_a = leute["person_a"], leute["leiter_a"]
    await person_entfernen(db, leiter_a, org.id, person_a.id, jetzt=T0)
    # A second removal only moves the note forward (one note per person and provider).
    _, t = await link_erzeugen(db, leiter_a, "kursleiter", org.id, jetzt=T0 + timedelta(hours=1))
    await link_einloesen(db, t, person_a, jetzt=T0 + timedelta(hours=1))
    await person_entfernen(db, leiter_a, org.id, person_a.id, jetzt=T0 + timedelta(hours=2))
    with pytest.raises(LinkUngueltig, match=LINK_ZURUECKGEZOGEN):
        await link_einloesen(db, t, person_a, jetzt=T0 + timedelta(hours=3))

    g, neuer_token = await gruppe_anlegen(db, leiter_a, org.id, kurs_intern.course_uuid, "Dienstag",
                                          jetzt=T0 + timedelta(hours=3))
    e = await link_einloesen(db, neuer_token, person_a, jetzt=T0 + timedelta(hours=4))
    assert e.rolle is Rolle.TEILNEHMEND and e.gruppe_id == g.id
    assert await rolle_von(db, person_a, org.id) is Rolle.TEILNEHMEND
    assert await _in_gruppe(db, person_a.id, g)


async def test_gruppe_nur_fuer_kurs_mit_learning_kennung(db, org, leute) -> None:
    now = str(datetime.now())
    kaputt = Course(id=104, name="Ohne Kennung", public=False, published=True, open_to_contributors=False,
                    org_id=org.id, course_uuid="course_keine-uuid", creation_date=now, update_date=now)
    db.add(kaputt)
    await db.commit()
    vorher = await _zeilen(db)

    with pytest.raises(Verweigert) as e:
        await gruppe_anlegen(db, leute["leiter_a"], org.id, "course_keine-uuid", "Montag")
    assert e.value.text == NICHT_ERLAUBT
    assert await _zeilen(db) == vorher
    assert await _anzahl(db, UserGroupResource) == 0
