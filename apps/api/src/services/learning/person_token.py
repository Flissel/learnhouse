"""The signed person token the embedded sequence player sends back to learning-api.

Same format and key derivation as Learning's ``services/lernsequenz/person.py``: a key
derived from the shared service key (``LEARNHOUSE_LEARNING_SERVICE_KEY``), payload
``<learner id>|<expiry>``, HMAC-SHA256 signature. The web app fetches one per lesson
page and appends it to the player's embed link; the player then carries it as a header.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import time

KEY_ENV = "LEARNHOUSE_LEARNING_SERVICE_KEY"
TTL_SECONDS = 8 * 3600
_ACTOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _key(key: str | None) -> bytes:
    shared = key if key is not None else os.environ.get(KEY_ENV, "")
    if len(shared) < 32:
        raise RuntimeError("learning service key is not configured")
    return hashlib.sha256(b"person:" + shared.encode()).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _signature(payload: str, key: str | None) -> str:
    return hmac.new(_key(key), payload.encode(), hashlib.sha256).hexdigest()[:48]


def person_token(actor_id: str, *, key: str | None = None, now: float | None = None) -> str:
    if not _ACTOR.match(actor_id):
        raise ValueError("actor id is not a safe token")
    expires = int((now if now is not None else time.time()) + TTL_SECONDS)
    payload = _b64(f"{actor_id}|{expires}".encode())
    return f"{payload}.{_signature(payload, key)}"


def read_person_token(token: str, *, key: str | None = None, now: float | None = None) -> str:
    """The learner id of a valid token; ``LookupError("expired")`` or ``LookupError("invalid")``."""
    payload, _, signature = token.partition(".")
    if not payload or not hmac.compare_digest(_signature(payload, key), signature):
        raise LookupError("invalid")
    try:
        actor_id, _, expires = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode().rpartition("|")
        expiry = int(expires)
    except (ValueError, UnicodeDecodeError) as error:
        raise LookupError("invalid") from error
    if not _ACTOR.match(actor_id):
        raise LookupError("invalid")
    if expiry < (now if now is not None else time.time()):
        raise LookupError("expired")
    return actor_id
