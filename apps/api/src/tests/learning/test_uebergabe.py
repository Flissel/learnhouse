"""Teil B: the hand-over token to the Lern-Hülle (label ``uebergabe:``, 120 s)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.services.learning.person_token import person_token, read_person_token
from src.services.learning.uebergabe import TTL_SECONDS, read_uebergabe_token, uebergabe_token

VEKTOR = Path(__file__).with_name("uebergabe_vektor.json")
KEY = "test-only-uebergabe-key-0123456789abcdef0123456789abcdef01234567"[:64]
KURS = "00000000-0000-4000-8000-000000000001"


def test_uebergabe_vektor() -> None:
    roh = VEKTOR.read_bytes()
    assert b"\r" not in roh and not roh.startswith(b"\xef\xbb\xbf")
    vektor = json.loads(roh)
    assert set(vektor) == {"key", "now", "actor_id", "course_id", "token"}
    assert len(vektor["key"]) == 64 and vektor["key"].startswith("test-only-")
    assert vektor["now"] == 1800000000 and vektor["actor_id"] == "lh-1-person-a"

    token = uebergabe_token(vektor["actor_id"], vektor["course_id"], key=vektor["key"], now=vektor["now"])

    assert token == vektor["token"]
    assert read_uebergabe_token(token, key=vektor["key"], now=vektor["now"]) == (
        vektor["actor_id"], vektor["course_id"]
    )


def test_uebergabe_format_und_ablauf() -> None:
    token = uebergabe_token("lh-1-person-a", KURS, key=KEY, now=1000)
    payload, _, signatur = token.partition(".")
    assert "=" not in payload and len(signatur) == 48
    assert TTL_SECONDS == 120

    assert read_uebergabe_token(token, key=KEY, now=1000 + 120) == ("lh-1-person-a", KURS)
    with pytest.raises(LookupError, match="expired"):
        read_uebergabe_token(token, key=KEY, now=1000 + 121)
    with pytest.raises(LookupError, match="invalid"):
        read_uebergabe_token(token[:-1] + ("0" if token[-1] != "0" else "1"), key=KEY, now=1000)
    with pytest.raises(LookupError, match="invalid"):
        read_uebergabe_token(token, key=KEY[::-1], now=1000)

    ohne_kurs = uebergabe_token("lh-1-person-a", None, key=KEY, now=1000)
    assert read_uebergabe_token(ohne_kurs, key=KEY, now=1000) == ("lh-1-person-a", None)


def test_uebergabe_prueft_eingaben() -> None:
    for actor in ("", "lh|x", "-lh", "lh 1", "lh-1\n"):
        with pytest.raises(ValueError):
            uebergabe_token(actor, KURS, key=KEY, now=1000)
    for kurs in ("kein-kurs", "0000000a-0000-4000-8000-00000000000b".upper(), "course_" + KURS, KURS + "|x"):
        with pytest.raises(ValueError):
            uebergabe_token("lh-1-person-a", kurs, key=KEY, now=1000)
    with pytest.raises(RuntimeError):
        uebergabe_token("lh-1-person-a", KURS, key="zu-kurz", now=1000)


def test_uebergabe_label_getrennt() -> None:
    uebergabe = uebergabe_token("lh-1-person-a", KURS, key=KEY, now=1000)
    person = person_token("lh-1-person-a", key=KEY, now=1000)

    with pytest.raises(LookupError, match="invalid"):
        read_person_token(uebergabe, key=KEY, now=1000)
    with pytest.raises(LookupError, match="invalid"):
        read_uebergabe_token(person, key=KEY, now=1000)
    # Both are valid under their own label.
    assert read_person_token(person, key=KEY, now=1000) == "lh-1-person-a"
    assert read_uebergabe_token(uebergabe, key=KEY, now=1000)[0] == "lh-1-person-a"
