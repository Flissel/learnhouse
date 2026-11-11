"""Teil C: the Hülle asks the service whether a person belongs to a group (service key)."""

from __future__ import annotations

import pytest

from src.services.learning.kurs_kennung import _course_id
from src.services.learning.personen import actor_von
from src.services.learning.verwaltung import gruppe_anlegen, gruppe_schliessen, link_einloesen
from src.tests.learning.test_bootstrap import SERVICE_HEADER, SERVICE_KEY
from src.tests.learning.test_verwaltung import (  # noqa: F401  (fixtures)
    kurs_a,
    kurs_b,
    kurs_intern,
    leute,
    org2,
    rollen,
)
from src.tests.learning.test_verwaltung_routen import _Wer, _client, lernmodus  # noqa: F401

pytestmark = pytest.mark.asyncio

KEY = {SERVICE_HEADER: SERVICE_KEY}


async def test_gruppe_person_mitglied(db, org, leute, kurs_intern, lernmodus) -> None:
    gruppe, token = await gruppe_anlegen(db, leute["leiter_a"], org.id, kurs_intern.course_uuid, "Montag")
    await link_einloesen(db, token, leute["person_a"])
    actor = await actor_von(db, leute["person_a"])
    async with _client(db, _Wer()) as client:
        antwort = await client.get(f"/api/v1/learning/gruppen/{gruppe.id}/personen/{actor}", headers=KEY)
        await gruppe_schliessen(db, leute["leiter_a"], gruppe.id)
        zu = await client.get(f"/api/v1/learning/gruppen/{gruppe.id}/personen/{actor}", headers=KEY)

    assert antwort.status_code == 200
    assert antwort.json() == {
        "mitglied": True, "offen": True, "course_id": _course_id(kurs_intern),
        "gruppe_name": "Montag", "anzeigename": "person-a Test",
    }
    # Closing only stops the link; members stay members.
    assert zu.json()["mitglied"] is True and zu.json()["offen"] is False


async def test_gruppe_person_kein_mitglied(db, org, leute, kurs_intern, lernmodus) -> None:
    gruppe, _ = await gruppe_anlegen(db, leute["leiter_a"], org.id, kurs_intern.course_uuid, "Montag")
    actor = await actor_von(db, leute["person_a"])
    async with _client(db, _Wer()) as client:
        antwort = await client.get(f"/api/v1/learning/gruppen/{gruppe.id}/personen/{actor}", headers=KEY)

    assert antwort.status_code == 200
    assert antwort.json()["mitglied"] is False
    assert antwort.json()["gruppe_name"] == "Montag"
    assert antwort.json()["course_id"] == _course_id(kurs_intern)


async def test_gruppe_person_unbekannt_404(db, org, leute, kurs_intern, lernmodus) -> None:
    gruppe, _ = await gruppe_anlegen(db, leute["leiter_a"], org.id, kurs_intern.course_uuid, "Montag")
    actor = await actor_von(db, leute["person_a"])
    async with _client(db, _Wer()) as client:
        actor_weg = await client.get(f"/api/v1/learning/gruppen/{gruppe.id}/personen/lh-unbekannt", headers=KEY)
        unsicher = await client.get(f"/api/v1/learning/gruppen/{gruppe.id}/personen/a%20b", headers=KEY)
        gruppe_weg = await client.get(f"/api/v1/learning/gruppen/99999/personen/{actor}", headers=KEY)

    assert actor_weg.status_code == unsicher.status_code == gruppe_weg.status_code == 404


async def test_gruppe_person_ohne_schluessel_403(db, org, leute, kurs_intern, lernmodus) -> None:
    gruppe, _ = await gruppe_anlegen(db, leute["leiter_a"], org.id, kurs_intern.course_uuid, "Montag")
    actor = await actor_von(db, leute["person_a"])
    async with _client(db, _Wer()) as client:
        ohne = await client.get(f"/api/v1/learning/gruppen/{gruppe.id}/personen/{actor}")
        falsch = await client.get(f"/api/v1/learning/gruppen/{gruppe.id}/personen/{actor}",
                                  headers={SERVICE_HEADER: "x" * 40})

    assert ohne.status_code == falsch.status_code == 403
