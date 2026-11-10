"""The short-lived hand-over token that opens a course on the person's Lern-Hülle.

LearnHouse signs ``<actor_id>|<course_id or empty>|<expiry>`` with the shared service key
(``LEARNHOUSE_LEARNING_SERVICE_KEY``) under its own derivation label ``uebergabe:``; the
Hülle checks it and sets its own person cookie. Same format as ``person_token.py``
(base64url payload without padding, ``.``, HMAC-SHA256 hex cut to 48), but a token of
one label is never accepted under the other. Valid for 120 seconds; not single-use (an
allow-once list comes before any internet exposure).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from uuid import UUID

from src.services.learning.person_token import _ACTOR, KEY_ENV

TTL_SECONDS = 120
_LABEL = b"uebergabe:"


def _key(key: str | None) -> bytes:
    shared = key if key is not None else os.environ.get(KEY_ENV, "")
    if len(shared) < 32:
        raise RuntimeError("learning service key is not configured")
    return hashlib.sha256(_LABEL + shared.encode()).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _signature(payload: str, key: str | None) -> str:
    return hmac.new(_key(key), payload.encode(), hashlib.sha256).hexdigest()[:48]


def _ist_course_id(course_id: str) -> bool:
    try:
        return str(UUID(course_id)) == course_id
    except ValueError:
        return False


def uebergabe_token(
    actor_id: str, course_id: str | None, *, key: str | None = None, now: float | None = None
) -> str:
    if _ACTOR.fullmatch(actor_id) is None:
        raise ValueError("actor id is not a safe token")
    if course_id is not None and not _ist_course_id(course_id):
        raise ValueError("course id is not a canonical uuid")
    expires = int((now if now is not None else time.time()) + TTL_SECONDS)
    payload = _b64(f"{actor_id}|{course_id or ''}|{expires}".encode())
    return f"{payload}.{_signature(payload, key)}"


def read_uebergabe_token(
    token: str, *, key: str | None = None, now: float | None = None
) -> tuple[str, str | None]:
    """``(actor_id, course_id or None)`` of a valid token; ``LookupError("expired")`` or
    ``LookupError("invalid")``."""
    payload, _, signature = token.partition(".")
    if not payload or not hmac.compare_digest(_signature(payload, key), signature):
        raise LookupError("invalid")
    try:
        raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode()
        actor_id, course_id, expires = raw.split("|")
        expiry = int(expires)
    except ValueError as error:  # also UnicodeDecodeError and a wrong number of parts
        raise LookupError("invalid") from error
    if _ACTOR.fullmatch(actor_id) is None or (course_id and not _ist_course_id(course_id)):
        raise LookupError("invalid")
    if expiry < (now if now is not None else time.time()):
        raise LookupError("expired")
    return actor_id, course_id or None
