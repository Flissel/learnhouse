"""Group capacity: a group link admits no more people than the group canvas of its course holds.

The number comes from learning-mcp (``learning_group_capacity``) through ``practice._call``; it is
mocked there. Unknown capacity lets people in (fail-open) and logs a warning.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

import src.routers.learning.practice as practice
from src.db.learning.teil_b import LearningGruppe
from src.db.users import User
from src.security.auth import JWT_COOKIE_NAME
from src.services.learning.kurs_kennung import _course_id
from src.services.learning.verwaltung import LinkUngueltig, gruppe_voll_text, mitglieder_zahl
from src.tests.learning.test_verwaltung import (  # noqa: F401  (fixtures)
    kurs_a,
    kurs_b,
    kurs_intern,
    leute,
    org2,
    rollen,
)
from src.tests.learning.test_verwaltung_routen import (  # noqa: F401  (fixtures and helpers)
    PASSWORT,
    WEB,
    _client,
    _ohne_nebenwirkungen,
    _token_aus,
    _Wer,
    lernmodus,
)

pytestmark = pytest.mark.asyncio

VOLL_2 = "Diese Gruppe ist voll (höchstens 2 Personen). Bitte wenden Sie sich an Ihre Kursleitung."


class _Learning:
    """``practice._call`` for ``learning_group_capacity``: a fixed answer, every call recorded."""

    def __init__(self, antwort: object) -> None:
        self.antwort = antwort
        self.aufrufe: list[tuple[str, dict, bool]] = []

    async def __call__(self, tool: str, event: dict, *, write: bool = False, fresh: bool = False) -> dict:
        self.aufrufe.append((tool, event, write))
        if isinstance(self.antwort, Exception):
            raise self.antwort
        return self.antwort  # type: ignore[return-value]


def _plaetze(n: int) -> dict:
    return {"state": "completed", "result": {"kapazitaet": n, "aufgaben": 16, "course_revision": 3}, "evidence": {}}


async def _gruppe(client, wer: _Wer, leute, org, kurs) -> tuple[int, str]:
    wer.user = leute["leiter_a"]
    antwort = await client.post("/api/v1/learning/verwaltung/gruppen",
                                json={"org_id": org.id, "course_uuid": kurs.course_uuid, "name": "Montag"})
    assert antwort.status_code == 200, antwort.text
    return antwort.json()["gruppe_id"], _token_aus(antwort.json()["url"], WEB + "/einladung/")


async def _mitglieder(db, gruppe_id: int) -> int:
    return await mitglieder_zahl(db, await db.get(LearningGruppe, gruppe_id))


async def test_volle_gruppe_lehnt_neue_ab_mitglieder_nie(db, org, leute, kurs_a, lernmodus, monkeypatch) -> None:
    learning = _Learning(_plaetze(2))
    monkeypatch.setattr(practice, "_call", learning)
    wer = _Wer()
    async with _client(db, wer) as client:
        gruppe_id, token = await _gruppe(client, wer, leute, org, kurs_a)
        wer.user = leute["neu"]
        erste = await client.post(f"/api/v1/learning/einladung/{token}/annehmen")
        wer.user = leute["neu2"]
        zweite = await client.post(f"/api/v1/learning/einladung/{token}/annehmen")
        wer.user = leute["person_a"]
        dritte = await client.post(f"/api/v1/learning/einladung/{token}/annehmen")
        wer.user = leute["neu"]
        nochmal = await client.post(f"/api/v1/learning/einladung/{token}/annehmen")

    assert erste.status_code == zweite.status_code == 200
    assert dritte.status_code == 410
    assert dritte.json() == {"detail": VOLL_2, "grund": "voll"}
    assert token not in dritte.text
    assert nochmal.status_code == 200  # wer schon Mitglied ist, wird nie abgelehnt
    assert await _mitglieder(db, gruppe_id) == 2
    # Lesend, als System, mit der Learning-Kurs-ID der Gruppe.
    tool, event, write = learning.aufrufe[0]
    assert (tool, write) == ("learning_group_capacity", False)
    assert event["event_type"] == "learning.group.capacity"
    assert event["course_id"] == _course_id(kurs_a)
    assert event["actor"]["actor_type"] == "system" and event["payload"] == {}


async def test_konto_weg_prueft_vor_dem_anlegen(db, org, leute, kurs_a, lernmodus, monkeypatch) -> None:
    monkeypatch.setattr(practice, "_call", _Learning(_plaetze(1)))
    wer = _Wer()
    async with _client(db, wer) as client:
        gruppe_id, token = await _gruppe(client, wer, leute, org, kurs_a)
        wer.user = None
        konten_vorher = (await db.execute(select(func.count()).select_from(User))).scalar_one()
        with _ohne_nebenwirkungen():
            frei = await client.post(f"/api/v1/learning/einladung/{token}/konto",
                                     json={"email": "kap-1@example.org", "username": "kap-1", "password": PASSWORT})
        client.cookies.clear()
        with _ohne_nebenwirkungen():
            voll = await client.post(f"/api/v1/learning/einladung/{token}/konto",
                                     json={"email": "kap-2@example.org", "username": "kap-2", "password": PASSWORT})

    assert frei.status_code == 200, frei.text
    assert voll.status_code == 410
    assert voll.json() == {"detail": gruppe_voll_text(1), "grund": "voll"}
    assert "höchstens 1 Person)" in voll.json()["detail"]
    # Kein Konto ohne Gruppe: nur das erste Konto ist entstanden, kein Cookie fuer das zweite.
    assert (await db.execute(select(func.count()).select_from(User))).scalar_one() == konten_vorher + 1
    assert (await db.execute(select(User).where(User.username == "kap-2"))).scalars().first() is None
    assert voll.cookies.get(JWT_COOKIE_NAME) is None
    assert await _mitglieder(db, gruppe_id) == 1


@pytest.mark.parametrize("antwort", [
    HTTPException(status_code=503, detail="learning unavailable"),
    HTTPException(status_code=409, detail="invalid_session_request"),
    ValueError("kaputtes JSON"),
    {"state": "rejected", "result": {}},
    {"state": "completed", "result": {"kapazitaet": "zehn"}},
    {"state": "completed", "result": {"kapazitaet": 0}},
    {"state": "completed", "result": {"kapazitaet": True}},
    {"state": "completed", "result": None},
])
async def test_ohne_brauchbare_kapazitaet_durchlassen_und_warnen(
    db, org, leute, kurs_a, lernmodus, monkeypatch, caplog, antwort,
) -> None:
    monkeypatch.setattr(practice, "_call", _Learning(antwort))
    wer = _Wer()
    async with _client(db, wer) as client:
        gruppe_id, token = await _gruppe(client, wer, leute, org, kurs_a)
        with caplog.at_level(logging.WARNING, logger=practice.__name__):
            for name in ("neu", "neu2", "person_a"):
                wer.user = leute[name]
                angenommen = await client.post(f"/api/v1/learning/einladung/{token}/annehmen")
                assert angenommen.status_code == 200, angenommen.text

    assert await _mitglieder(db, gruppe_id) == 3
    warnungen = [r for r in caplog.records if r.name == practice.__name__ and r.levelno == logging.WARNING]
    assert warnungen and all(token not in r.getMessage() for r in warnungen)


async def test_learning_mcp_nicht_erreichbar_ungemockt_durchlassen(db, org, leute, kurs_a, lernmodus) -> None:
    """Der echte ``_call`` gegen einen Port ohne Dienst (conftest): fail-open."""
    wer = _Wer()
    async with _client(db, wer) as client:
        gruppe_id, token = await _gruppe(client, wer, leute, org, kurs_a)
        wer.user = leute["neu"]
        angenommen = await client.post(f"/api/v1/learning/einladung/{token}/annehmen")

    assert angenommen.status_code == 200, angenommen.text
    assert await _mitglieder(db, gruppe_id) == 1


async def test_nur_gruppenlinks_fragen_learning(db, org, leute, lernmodus, monkeypatch) -> None:
    learning = _Learning(_plaetze(1))
    monkeypatch.setattr(practice, "_call", learning)
    wer = _Wer()
    wer.user = leute["leiter_a"]
    async with _client(db, wer) as client:
        erzeugt = await client.post("/api/v1/learning/verwaltung/links", json={"art": "kursleiter", "org_id": org.id})
        token = _token_aus(erzeugt.json()["url"], WEB + "/einladung/")
        wer.user = leute["neu"]
        angenommen = await client.post(f"/api/v1/learning/einladung/{token}/annehmen")

    assert angenommen.status_code == 200
    assert learning.aufrufe == []


async def test_verwaltung_nennt_mitglieder_und_hoechstzahl(db, org, leute, kurs_a, lernmodus, monkeypatch) -> None:
    learning = _Learning(_plaetze(10))
    monkeypatch.setattr(practice, "_call", learning)
    wer = _Wer()
    async with _client(db, wer) as client:
        gruppe_id, token = await _gruppe(client, wer, leute, org, kurs_a)
        zweite_id, _ = await _gruppe(client, wer, leute, org, kurs_a)
        for name in ("neu", "neu2"):
            wer.user = leute[name]
            assert (await client.post(f"/api/v1/learning/einladung/{token}/annehmen")).status_code == 200
        wer.user = leute["leiter_a"]
        await client.post("/api/v1/learning/verwaltung/links", json={"art": "kursleiter", "org_id": org.id})
        learning.aufrufe.clear()
        liste = await client.get("/api/v1/learning/verwaltung/links", params={"org_id": org.id})
        fragen_je_liste = len(learning.aufrufe)
        learning.antwort = HTTPException(status_code=503, detail="learning unavailable")
        unbekannt = await client.get("/api/v1/learning/verwaltung/links", params={"org_id": org.id})

    assert liste.status_code == 200
    gruppen = {e["gruppe_id"]: (e["mitglieder"], e["kapazitaet"]) for e in liste.json() if e["art"] == "gruppe"}
    assert gruppen == {gruppe_id: (2, 10), zweite_id: (0, 10)}
    (kursleiter,) = [e for e in liste.json() if e["art"] == "kursleiter"]
    assert (kursleiter["mitglieder"], kursleiter["kapazitaet"]) == (None, None)
    assert fragen_je_liste == 1  # zwei Gruppen desselben Kurses: einmal je Kurs und Anfrage
    assert {e["gruppe_id"]: (e["mitglieder"], e["kapazitaet"]) for e in unbekannt.json() if e["art"] == "gruppe"} == {
        gruppe_id: (2, None), zweite_id: (0, None)}


def test_meldung_voll() -> None:
    assert LinkUngueltig("voll", hoechstens=10).text == (
        "Diese Gruppe ist voll (höchstens 10 Personen). Bitte wenden Sie sich an Ihre Kursleitung.")
    assert LinkUngueltig("voll", hoechstens=10).grund == "voll"
    with pytest.raises(ValueError):
        LinkUngueltig("voll")
