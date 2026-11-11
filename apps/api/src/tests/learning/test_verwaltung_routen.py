"""Teil B: HTTP routes for the course overview, invitations, groups, hand-over and providers."""

from __future__ import annotations

from contextlib import ExitStack, asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

import src.routers.learning as learning_router_module
# Imported at collection, like the other learning routers: a later reload of the database
# module (tests/core/test_events_database.py) must not leave the routes another get_db_session.
import src.routers.learning.service as service_routen
import src.routers.learning.verwaltung as verwaltung_routen
from src.core.events.database import get_db_session
from src.db.learning.teil_b import LearningLink
from src.db.organization_config import OrganizationConfig
from src.db.organizations import Organization, OrganizationCreate
from src.db.user_organizations import UserOrganization
from src.db.users import User
from src.security.auth import JWT_COOKIE_NAME, decode_jwt, get_authenticated_user
from src.services.learning.kurs_kennung import _course_id
from src.services.learning.personen import actor_von
from src.services.learning.uebergabe import read_uebergabe_token
from src.services.learning.verwaltung import (
    GRUPPE_GESCHLOSSEN,
    gruppe_anlegen,
    link_einloesen,
    LINK_UNBEKANNT,
    LINK_ZURUECKGEZOGEN,
    NICHT_ERLAUBT,
    ROOT_BLEIBT,
    Rolle,
    rolle_von,
)
from src.services.orgs.orgs import create_org
from src.tests.learning.test_bootstrap import (
    BOOTSTRAP_HEADER,
    BOOTSTRAP_KEY,
    SERVICE_HEADER,
    SERVICE_KEY,
    _enable_local_mode,
)
from src.tests.learning.test_verwaltung import (  # noqa: F401  (fixtures)
    kurs_a,
    kurs_b,
    kurs_intern,
    leute,
    org2,
    rollen,
)

pytestmark = pytest.mark.asyncio

HUELLE = "http://huelle.test"
WEB = "http://web.test"
PASSWORT = "Sicher-Passwort-2026!"


@pytest.fixture
def lernmodus(monkeypatch):
    _enable_local_mode(monkeypatch)
    monkeypatch.setenv("LEARNHOUSE_LEARNING_HUELLE_BASIS", HUELLE)
    monkeypatch.setenv("LEARNHOUSE_LEARNING_WEB_BASIS", WEB + "/")


class _Wer:
    """Who is signed in for the next request (``None``: nobody)."""

    def __init__(self) -> None:
        self.user = None


@asynccontextmanager
async def _client(db, wer: _Wer):
    api = APIRouter(prefix="/api/v1")
    assert learning_router_module.mount_local_learning_bootstrap(api) is True
    app = FastAPI()
    app.include_router(api)

    async def override_db_session():
        yield db

    def angemeldet():
        if wer.user is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        return wer.user

    for abhaengigkeit in {get_db_session, service_routen.get_db_session, verwaltung_routen.get_db_session}:
        app.dependency_overrides[abhaengigkeit] = override_db_session
    app.dependency_overrides[get_authenticated_user] = angemeldet
    transport = ASGITransport(app=app, client=("172.18.0.4", 43123))
    async with AsyncClient(transport=transport, base_url="http://learnhouse-api") as client:
        yield client


def _token_aus(url: str, basis: str) -> str:
    assert url.startswith(basis)
    return url[len(basis):]


def _ohne_nebenwirkungen() -> ExitStack:
    """Signup side effects (quota, analytics, webhooks, mails) are not part of these tests."""
    stack = ExitStack()
    for ziel, kwargs in [
        ("src.services.users.users.check_limits_with_usage", {"new_callable": AsyncMock}),
        ("src.services.users.users.increase_feature_usage", {"new_callable": AsyncMock}),
        ("src.services.users.users.track", {"new_callable": AsyncMock}),
        ("src.services.users.users.dispatch_webhooks", {"new_callable": AsyncMock}),
        ("src.services.users.users.send_account_creation_email", {}),
        ("src.services.orgs.orgs._try_send_org_created", {"new_callable": AsyncMock}),
        ("src.services.orgs.orgs._try_record_org_admin_in_loops", {}),
        ("src.routers.learning.verwaltung.check_invite_acceptance_rate_limit", {"return_value": (True, 0)}),
    ]:
        stack.enter_context(patch(ziel, **kwargs))
    return stack


async def _anzahl(db, model) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def test_routen_fehlen_ohne_lernmodus(db, monkeypatch) -> None:
    monkeypatch.delenv("LEARNHOUSE_LOCAL_LEARNING_MODE", raising=False)
    aus = APIRouter()
    assert learning_router_module.mount_local_learning_bootstrap(aus) is False
    assert aus.routes == []

    _enable_local_mode(monkeypatch)
    an = APIRouter()
    assert learning_router_module.mount_local_learning_bootstrap(an) is True
    app = FastAPI()
    app.include_router(an)
    pfade = set(app.openapi()["paths"])
    for pfad in (
        "/learning/verwaltung/kursuebersicht", "/learning/uebergabe", "/learning/verwaltung/links",
        "/learning/verwaltung/links/{link_id}", "/learning/verwaltung/gruppen",
        "/learning/verwaltung/gruppen/{gruppe_id}/schliessen", "/learning/verwaltung/personen",
        "/learning/verwaltung/personen/{user_id}", "/learning/einladung/{token}",
        "/learning/einladung/{token}/konto", "/learning/einladung/{token}/annehmen",
        "/learning/anbieter", "/learning/personen/{actor_id}/kurse", "/learning/gruppen/{gruppe_id}/personen/{actor_id}",
    ):
        assert pfad in pfade, pfad

    # Mounted once, then the mode is switched off: the routes answer 404.
    wer = _Wer()
    async with _client(db, wer) as client:
        monkeypatch.delenv("LEARNHOUSE_LOCAL_LEARNING_MODE")
        weg = await client.get("/api/v1/learning/einladung/irgendwas")
        auch_weg = await client.get("/api/v1/learning/verwaltung/kursuebersicht")
    assert weg.status_code == auch_weg.status_code == 404


async def test_kursuebersicht_zeigt_kurse_und_rollen(db, org, leute, kurs_a, kurs_intern, kurs_b, lernmodus) -> None:
    wer = _Wer()
    async with _client(db, wer) as client:
        anonym = await client.get("/api/v1/learning/verwaltung/kursuebersicht")
        wer.user = leute["person_a"]
        uebersicht = await client.get("/api/v1/learning/verwaltung/kursuebersicht")
        wer.user = leute["root"]
        root = await client.get("/api/v1/learning/verwaltung/kursuebersicht")

    assert anonym.status_code == 401
    assert uebersicht.status_code == 200
    assert uebersicht.json() == {
        "kurse": [{"course_id": _course_id(kurs_a), "course_uuid": kurs_a.course_uuid, "titel": "Kurs A",
                   "gruppen": [], "org_id": org.id}],
        "rollen": [{"org_id": org.id, "org_name": "Test Org", "rolle": "teilnehmend"}],
    }
    # Root sees every provider as root.
    assert {(r["org_id"], r["rolle"]) for r in root.json()["rollen"]} == {(1, "root"), (2, "root")}


async def test_kursuebersicht_nennt_anbieter_je_kurs(db, org, org2, leute, kurs_a, kurs_b, lernmodus) -> None:
    """With two providers every course says whose it is (the web offers groups per provider)."""
    person_a = leute["person_a"]
    now = str(datetime.now())
    db.add(UserOrganization(user_id=person_a.id, org_id=org2.id, role_id=4, creation_date=now, update_date=now))
    await db.commit()
    wer = _Wer()
    wer.user = person_a
    async with _client(db, wer) as client:
        uebersicht = await client.get("/api/v1/learning/verwaltung/kursuebersicht")

    assert uebersicht.status_code == 200
    assert {(k["titel"], k["org_id"]) for k in uebersicht.json()["kurse"]} == {
        ("Kurs A", org.id), ("Kurs B", org2.id),
    }
    assert org.id != org2.id


async def test_uebergabe_nur_eigene_kurse(db, org, leute, kurs_a, kurs_intern, kurs_b, lernmodus, monkeypatch) -> None:
    person_a = leute["person_a"]
    wer = _Wer()
    wer.user = person_a
    async with _client(db, wer) as client:
        fremd = await client.post("/api/v1/learning/uebergabe", json={"course_id": _course_id(kurs_b)})
        intern = await client.post("/api/v1/learning/uebergabe", json={"course_id": _course_id(kurs_intern)})
        unbekannt = await client.post("/api/v1/learning/uebergabe",
                                      json={"course_id": "00000000-0000-4000-8000-000000000999"})
        eigen = await client.post("/api/v1/learning/uebergabe", json={"course_id": _course_id(kurs_a)})
        monkeypatch.delenv("LEARNHOUSE_LEARNING_HUELLE_BASIS")
        ohne_basis = await client.post("/api/v1/learning/uebergabe", json={"course_id": _course_id(kurs_a)})

    assert fremd.status_code == intern.status_code == unbekannt.status_code == 403
    assert fremd.json() == {"detail": NICHT_ERLAUBT}
    assert eigen.status_code == 200
    token = _token_aus(eigen.json()["url"], HUELLE + "/lernen/uebergabe/")
    assert read_uebergabe_token(token, key=SERVICE_KEY) == (await actor_von(db, person_a), _course_id(kurs_a))
    assert ohne_basis.status_code == 503


async def test_einladung_konto_anlegen_meldet_an(db, org, leute, lernmodus) -> None:
    wer = _Wer()
    wer.user = leute["leiter_a"]
    async with _client(db, wer) as client:
        erzeugt = await client.post("/api/v1/learning/verwaltung/links", json={"art": "kursleiter", "org_id": org.id})
        wer.user = None
        token = _token_aus(erzeugt.json()["url"], WEB + "/einladung/")
        vorschau = await client.get(f"/api/v1/learning/einladung/{token}")
        with _ohne_nebenwirkungen():
            konto = await client.post(f"/api/v1/learning/einladung/{token}/konto",
                                      json={"email": "person-d@example.com", "username": "person-d",
                                            "password": PASSWORT})

    assert erzeugt.status_code == 200
    assert set(erzeugt.json()) == {"link_id", "url", "laeuft_ab"}
    assert vorschau.status_code == 200
    assert vorschau.json() == {"art": "kursleiter", "anbieter": "Test Org", "kurs": None}

    assert konto.status_code == 200, konto.text
    assert konto.json()["rolle"] == "kursleiter" and konto.json()["org_id"] == org.id
    assert token not in konto.text and "person-d@example.com" not in konto.text
    zugang = konto.cookies.get(JWT_COOKIE_NAME)
    assert zugang and decode_jwt(zugang)["sub"] == "person-d@example.com"
    neu = (await db.execute(select(User).where(User.username == "person-d"))).scalars().one()
    assert await rolle_von(db, neu, org.id) is Rolle.KURSLEITER


async def test_einladung_gruppe_annehmen_gibt_uebergabe(db, org, leute, kurs_a, lernmodus) -> None:
    wer = _Wer()
    wer.user = leute["leiter_a"]
    async with _client(db, wer) as client:
        gruppe = await client.post("/api/v1/learning/verwaltung/gruppen",
                                   json={"org_id": org.id, "course_uuid": kurs_a.course_uuid, "name": "Montag"})
        token = _token_aus(gruppe.json()["url"], WEB + "/einladung/")
        wer.user = None
        vorschau = await client.get(f"/api/v1/learning/einladung/{token}")
        anonym = await client.post(f"/api/v1/learning/einladung/{token}/annehmen")
        wer.user = leute["neu"]
        angenommen = await client.post(f"/api/v1/learning/einladung/{token}/annehmen")
        uebersicht = await client.get("/api/v1/learning/verwaltung/kursuebersicht")

    assert gruppe.status_code == 200 and set(gruppe.json()) == {"gruppe_id", "url"}
    assert vorschau.json() == {"art": "gruppe", "anbieter": "Test Org", "kurs": "Kurs A"}
    assert anonym.status_code == 401
    assert angenommen.status_code == 200
    body = angenommen.json()
    assert (body["rolle"], body["gruppe_id"], body["course_id"]) == (
        "teilnehmend", gruppe.json()["gruppe_id"], _course_id(kurs_a))
    uebergabe = _token_aus(body["uebergabe_url"].split("?")[0], HUELLE + "/lernen/uebergabe/")
    assert read_uebergabe_token(uebergabe, key=SERVICE_KEY) == (
        await actor_von(db, leute["neu"]), _course_id(kurs_a))
    assert uebersicht.json()["kurse"][0]["gruppen"] == [{"id": gruppe.json()["gruppe_id"], "name": "Montag"}]
    # Teil C: the web opens the group surface from the hand-over URL.
    assert body["uebergabe_url"].endswith(f"?gruppe={gruppe.json()['gruppe_id']}")


async def test_einladung_410_mit_text(db, org, leute, lernmodus) -> None:
    wer = _Wer()
    wer.user = leute["admin_a"]
    async with _client(db, wer) as client:
        erzeugt = await client.post("/api/v1/learning/verwaltung/links", json={"art": "kursleiter", "org_id": org.id})
        token = _token_aus(erzeugt.json()["url"], WEB + "/einladung/")
        zurueck = await client.delete(f"/api/v1/learning/verwaltung/links/{erzeugt.json()['link_id']}")
        wer.user = None
        vorschau = await client.get(f"/api/v1/learning/einladung/{token}")
        unbekannt = await client.get("/api/v1/learning/einladung/gibt-es-nicht")
        konten_vorher = await _anzahl(db, User)
        with _ohne_nebenwirkungen():
            konto = await client.post(f"/api/v1/learning/einladung/{token}/konto",
                                      json={"email": "person-e@example.com", "username": "person-e",
                                            "password": PASSWORT})
        wer.user = leute["neu"]
        annehmen = await client.post(f"/api/v1/learning/einladung/{token}/annehmen")

    assert zurueck.status_code == 204
    assert vorschau.status_code == konto.status_code == annehmen.status_code == 410
    erwartet = {"detail": LINK_ZURUECKGEZOGEN, "grund": "zurueckgezogen"}
    assert vorschau.json() == konto.json() == annehmen.json() == erwartet
    assert unbekannt.status_code == 410 and unbekannt.json() == {"detail": LINK_UNBEKANNT, "grund": "unbekannt"}
    assert await _anzahl(db, User) == konten_vorher
    assert await rolle_von(db, leute["neu"], org.id) is None
    assert konto.cookies.get(JWT_COOKIE_NAME) is None


async def test_gruppe_schliessen_und_links_ohne_token(db, org, org2, leute, kurs_a, lernmodus) -> None:
    wer = _Wer()
    wer.user = leute["leiter_a"]
    async with _client(db, wer) as client:
        gruppe = await client.post("/api/v1/learning/verwaltung/gruppen",
                                   json={"org_id": org.id, "course_uuid": kurs_a.course_uuid, "name": "Montag"})
        link = await client.post("/api/v1/learning/verwaltung/links", json={"art": "kursleiter", "org_id": org.id})
        admin_link = await client.post("/api/v1/learning/verwaltung/links", json={"art": "admin", "org_id": org.id})
        aktiv = await client.get("/api/v1/learning/verwaltung/links", params={"org_id": org.id})
        wer.user = leute["leiter_b"]
        fremd_liste = await client.get("/api/v1/learning/verwaltung/links", params={"org_id": org.id})
        fremd_zu = await client.post(f"/api/v1/learning/verwaltung/gruppen/{gruppe.json()['gruppe_id']}/schliessen")
        wer.user = leute["leiter_a"]
        zu = await client.post(f"/api/v1/learning/verwaltung/gruppen/{gruppe.json()['gruppe_id']}/schliessen")
        danach = await client.get("/api/v1/learning/verwaltung/links", params={"org_id": org.id})
        token = _token_aus(gruppe.json()["url"], WEB + "/einladung/")
        geschlossen = await client.get(f"/api/v1/learning/einladung/{token}")
        leer = await client.post("/api/v1/learning/verwaltung/gruppen",
                                 json={"org_id": org.id, "course_uuid": kurs_a.course_uuid, "name": "  "})

    assert gruppe.status_code == link.status_code == 200
    assert admin_link.status_code == 403
    assert aktiv.status_code == 200
    eintraege = aktiv.json()
    assert sorted(e["art"] for e in eintraege) == ["gruppe", "kursleiter"]
    for eintrag in eintraege:
        assert set(eintrag) == {"link_id", "art", "gruppe_id", "gruppe", "erstellt_am", "laeuft_ab"}
    assert token not in aktiv.text and _token_aus(link.json()["url"], WEB + "/einladung/") not in aktiv.text
    assert fremd_liste.status_code == fremd_zu.status_code == 403
    assert zu.status_code == 204
    assert [e["art"] for e in danach.json()] == ["kursleiter"]
    assert geschlossen.status_code == 410
    assert geschlossen.json() == {"detail": GRUPPE_GESCHLOSSEN, "grund": "gruppe_geschlossen"}
    assert leer.status_code == 422


async def test_personenliste_ohne_email(db, org, leute, lernmodus) -> None:
    wer = _Wer()
    wer.user = leute["admin_a"]
    async with _client(db, wer) as client:
        liste = await client.get("/api/v1/learning/verwaltung/personen", params={"org_id": org.id})
        wer.user = leute["person_a"]
        teilnehmend = await client.get("/api/v1/learning/verwaltung/personen", params={"org_id": org.id})
        wer.user = leute["leiter_a"]
        root_weg = await client.delete(f"/api/v1/learning/verwaltung/personen/{leute['root'].id}",
                                       params={"org_id": org.id})

    assert liste.status_code == 200
    assert "@" not in liste.text and "email" not in liste.text
    personen = {p["user_id"]: p for p in liste.json()}
    assert set(personen) == {22, 23, 24, 25}
    assert personen[25] == {"user_id": 25, "anzeigename": "person-a Test", "rolle": "teilnehmend", "gruppen": []}
    assert personen[22]["rolle"] == "admin" and personen[24]["rolle"] == "kursleiter"
    assert teilnehmend.status_code == 403 and teilnehmend.json() == {"detail": NICHT_ERLAUBT}
    assert root_weg.status_code == 403 and root_weg.json() == {"detail": ROOT_BLEIBT}


async def test_dienstroute_kurse_404_nach_entfernen(db, org, leute, kurs_a, kurs_b, lernmodus) -> None:
    person_a = leute["person_a"]
    actor = await actor_von(db, person_a)
    wer = _Wer()
    async with _client(db, wer) as client:
        ohne_schluessel = await client.get(f"/api/v1/learning/personen/{actor}/kurse")
        kurse = await client.get(f"/api/v1/learning/personen/{actor}/kurse", headers={SERVICE_HEADER: SERVICE_KEY})
        unbekannt = await client.get("/api/v1/learning/personen/lh-unbekannt/kurse",
                                     headers={SERVICE_HEADER: SERVICE_KEY})
        wer.user = leute["admin_a"]
        entfernt = await client.delete(f"/api/v1/learning/verwaltung/personen/{person_a.id}",
                                       params={"org_id": org.id})
        danach = await client.get(f"/api/v1/learning/personen/{actor}/kurse", headers={SERVICE_HEADER: SERVICE_KEY})

    assert ohne_schluessel.status_code == 403
    assert kurse.status_code == 200
    assert kurse.json() == {"kurse": [{"course_id": _course_id(kurs_a), "titel": "Kurs A"}]}
    assert unbekannt.status_code == 404
    assert entfernt.status_code == 204
    assert danach.status_code == 404


async def test_anbieter_nur_root_mit_bootstrap(db, org, org2, leute, lernmodus, mock_request) -> None:
    wer = _Wer()
    neu = {"name": "Anbieter C", "slug": "anbieter-c"}
    with _ohne_nebenwirkungen():
        async with _client(db, wer) as client:
            wer.user = leute["root"]
            ohne_schluessel = await client.post("/api/v1/learning/anbieter", json=neu)
            falscher_schluessel = await client.post("/api/v1/learning/anbieter", json=neu,
                                                    headers={BOOTSTRAP_HEADER: "x" * 40})
            wer.user = leute["admin_a"]
            kein_root = await client.post("/api/v1/learning/anbieter", json=neu,
                                          headers={BOOTSTRAP_HEADER: BOOTSTRAP_KEY})
            wer.user = None
            anonym = await client.post("/api/v1/learning/anbieter", json=neu,
                                       headers={BOOTSTRAP_HEADER: BOOTSTRAP_KEY})
            anzahl_vorher = await _anzahl(db, Organization)
            wer.user = leute["root"]
            angelegt = await client.post("/api/v1/learning/anbieter", json=neu,
                                         headers={BOOTSTRAP_HEADER: BOOTSTRAP_KEY})
            wer.user = None
            token = _token_aus(angelegt.json()["admin_link_url"], WEB + "/einladung/")
            vorschau = await client.get(f"/api/v1/learning/einladung/{token}")

        # Outside the learning route the edition lock stays: OSS refuses a further provider.
        with pytest.raises(HTTPException) as gesperrt:
            await create_org(mock_request, OrganizationCreate(name="Anbieter D", slug="anbieter-d", email=""),
                             leute["root"], db)

    assert ohne_schluessel.status_code == falscher_schluessel.status_code == kein_root.status_code == 403
    assert anonym.status_code == 401
    assert anzahl_vorher == 2
    assert angelegt.status_code == 200, angelegt.text
    assert set(angelegt.json()) == {"org_id", "admin_link_url"}
    anbieter = await db.get(Organization, angelegt.json()["org_id"])
    assert (anbieter.name, anbieter.slug) == ("Anbieter C", "anbieter-c")
    assert vorschau.json() == {"art": "admin", "anbieter": "Anbieter C", "kurs": None}
    assert (await db.execute(select(LearningLink.art).where(LearningLink.org_id == anbieter.id))).scalars().all() == [
        "admin"]
    assert gesperrt.value.status_code == 403


async def _nur_diese_anmeldewege(db, org_id: int, wege: list[str]) -> None:
    db.add(OrganizationConfig(
        org_id=org_id,
        config={"config_version": "2.0", "admin_toggles": {"security": {"allowed_auth_methods": wege}}},
        creation_date=str(datetime.now()), update_date=str(datetime.now()),
    ))
    await db.commit()


async def _konto_ueber_link(db, org, leute) -> tuple[str, int]:
    wer = _Wer()
    wer.user = leute["admin_a"]
    async with _client(db, wer) as client:
        erzeugt = await client.post("/api/v1/learning/verwaltung/links", json={"art": "kursleiter", "org_id": org.id})
    return _token_aus(erzeugt.json()["url"], WEB + "/einladung/"), erzeugt.json()["link_id"]


async def test_einladung_konto_ohne_passwort_anmeldung_abgelehnt(db, org, leute, lernmodus) -> None:
    token, link_id = await _konto_ueber_link(db, org, leute)
    await _nur_diese_anmeldewege(db, org.id, ["google"])
    konten_vorher, mitglieder_vorher = await _anzahl(db, User), await _anzahl(db, UserOrganization)

    wer = _Wer()
    async with _client(db, wer) as client:
        with _ohne_nebenwirkungen():
            konto = await client.post(f"/api/v1/learning/einladung/{token}/konto",
                                      json={"email": "person-f@example.com", "username": "person-f",
                                            "password": PASSWORT})
        vorschau = await client.get(f"/api/v1/learning/einladung/{token}")

    assert konto.status_code == 403
    assert konto.json()["detail"]["code"] == "AUTH_METHOD_NOT_ALLOWED"
    assert konto.cookies.get(JWT_COOKIE_NAME) is None
    assert await _anzahl(db, User) == konten_vorher
    assert await _anzahl(db, UserOrganization) == mitglieder_vorher
    link = await db.get(LearningLink, link_id)
    await db.refresh(link)
    assert link.zurueckgezogen_am is None and vorschau.status_code == 200


async def test_einladung_konto_gedrosselt(db, org, leute, lernmodus) -> None:
    token, _ = await _konto_ueber_link(db, org, leute)
    konten_vorher = await _anzahl(db, User)

    wer = _Wer()
    async with _client(db, wer) as client:
        with _ohne_nebenwirkungen(), patch(
            "src.routers.learning.verwaltung.check_invite_acceptance_rate_limit", return_value=(False, 600)
        ) as drossel:
            konto = await client.post(f"/api/v1/learning/einladung/{token}/konto",
                                      json={"email": "person-g@example.com", "username": "person-g",
                                            "password": PASSWORT})

    assert konto.status_code == 429 and konto.headers["Retry-After"] == "600"
    assert drossel.call_args.args[1] == org.id
    assert await _anzahl(db, User) == konten_vorher
    assert token not in konto.text


async def test_anbieter_im_lernmodus_ohne_free_plan_grenze(db, org, leute, lernmodus, mock_request) -> None:
    wer = _Wer()
    wer.user = leute["root"]
    with _ohne_nebenwirkungen():
        async with _client(db, wer) as client:
            angelegt = [
                await client.post("/api/v1/learning/anbieter", json={"name": f"Anbieter {i}", "slug": f"anbieter-{i}"},
                                  headers={BOOTSTRAP_HEADER: BOOTSTRAP_KEY})
                for i in range(1, 6)
            ]
        # Every other caller keeps the free-plan cap (Root is admin of 5 free providers now).
        with pytest.raises(HTTPException) as begrenzt:
            await create_org(mock_request, OrganizationCreate(name="Anbieter X", slug="anbieter-x", email=""),
                             leute["root"], db, allow_multi_org=True)

    assert [r.status_code for r in angelegt] == [200] * 5, [r.text for r in angelegt]
    assert begrenzt.value.status_code == 403 and "Free plan" in str(begrenzt.value.detail)


async def test_einloesen_gruppenlink_url_mit_gruppe(db, org, leute, kurs_a, lernmodus) -> None:
    wer = _Wer()
    wer.user = leute["leiter_a"]
    async with _client(db, wer) as client:
        gruppe = await client.post("/api/v1/learning/verwaltung/gruppen",
                                   json={"org_id": org.id, "course_uuid": kurs_a.course_uuid, "name": "Montag"})
        token = _token_aus(gruppe.json()["url"], WEB + "/einladung/")
        wer.user = leute["neu"]
        angenommen = await client.post(f"/api/v1/learning/einladung/{token}/annehmen")

    gid = gruppe.json()["gruppe_id"]
    url = angenommen.json()["uebergabe_url"]
    assert url.startswith(HUELLE + "/lernen/uebergabe/") and url.endswith(f"?gruppe={gid}")


async def test_kursuebersicht_gruppen_mit_id(db, org, leute, kurs_intern, lernmodus) -> None:
    gruppe, token = await gruppe_anlegen(db, leute["leiter_a"], org.id, kurs_intern.course_uuid, "Montag")
    await link_einloesen(db, token, leute["person_a"])
    wer = _Wer()
    wer.user = leute["person_a"]
    async with _client(db, wer) as client:
        uebersicht = await client.get("/api/v1/learning/verwaltung/kursuebersicht")

    intern = [k for k in uebersicht.json()["kurse"] if k["titel"] == "Kurs Intern"]
    assert intern[0]["gruppen"] == [{"id": gruppe.id, "name": "Montag"}]


async def test_uebergabe_mit_gruppe_url_traegt_gruppe(db, org, leute, kurs_intern, lernmodus) -> None:
    gruppe, token = await gruppe_anlegen(db, leute["leiter_a"], org.id, kurs_intern.course_uuid, "Montag")
    await link_einloesen(db, token, leute["person_a"])
    wer = _Wer()
    wer.user = leute["person_a"]
    async with _client(db, wer) as client:
        antwort = await client.post("/api/v1/learning/uebergabe",
                                    json={"course_id": _course_id(kurs_intern), "gruppe_id": gruppe.id})

    assert antwort.status_code == 200
    url = antwort.json()["url"]
    assert url.endswith(f"?gruppe={gruppe.id}")
    roh = _token_aus(url.split("?")[0], HUELLE + "/lernen/uebergabe/")
    assert read_uebergabe_token(roh, key=SERVICE_KEY) == (
        await actor_von(db, leute["person_a"]), _course_id(kurs_intern))


async def test_uebergabe_fremde_gruppe_403(db, org, leute, kurs_a, kurs_intern, lernmodus) -> None:
    gruppe, _ = await gruppe_anlegen(db, leute["leiter_a"], org.id, kurs_intern.course_uuid, "Montag")
    andere, token = await gruppe_anlegen(db, leute["leiter_a"], org.id, kurs_intern.course_uuid, "Dienstag")
    await link_einloesen(db, token, leute["person_a"])
    wer = _Wer()
    wer.user = leute["person_a"]
    async with _client(db, wer) as client:
        kein_mitglied = await client.post("/api/v1/learning/uebergabe",
                                          json={"course_id": _course_id(kurs_intern), "gruppe_id": gruppe.id})
        falscher_kurs = await client.post("/api/v1/learning/uebergabe",
                                          json={"course_id": _course_id(kurs_a), "gruppe_id": andere.id})
        unbekannt = await client.post("/api/v1/learning/uebergabe",
                                      json={"course_id": _course_id(kurs_intern), "gruppe_id": 99999})

    assert kein_mitglied.status_code == falscher_kurs.status_code == unbekannt.status_code == 403
    assert kein_mitglied.json() == {"detail": NICHT_ERLAUBT}
