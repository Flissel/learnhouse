"""Practice in the Learning Player for the signed-in LearnHouse person.

The browser never talks to the Learning engine directly: these routes take the person
from the LearnHouse session, check read access to the course and forward the action to
learning-mcp with the person as learner (``lh-<org>-<user_uuid>``). Mastery is therefore
per person and per organisation (one instance, one organisation per customer).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.events.database import get_db_session
from src.db.user_organizations import UserOrganization
from src.db.users import PublicUser
from src.routers.learning.service import (
    LOCAL_LEARNING_SERVICE_KEY_ENV,
    _authorize_course,
    _course_by_public_id,
    _state_for_course,
)
from src.security.auth import get_current_user
from src.security.rbac import AccessAction

router = APIRouter()
MCP_URL_ENV = "LEARNING_MCP_URL"
_TIMEOUT_S = 660.0
_UNSAFE = re.compile(r"[^A-Za-z0-9._:-]")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SessionStart(_Strict):
    course_id: str = Field(min_length=1, max_length=80)
    mode: Literal["training", "exam"] = "training"


class AnswerWrite(_Strict):
    revision: int = Field(ge=1)
    answer: dict[str, Any]


class HintRequest(_Strict):
    task_id: str = Field(min_length=1, max_length=80)


class TutorQuestion(_Strict):
    question: Annotated[str, Field(min_length=1, max_length=2_000)]


class CanvasOpen(_Strict):
    activity_id: UUID


class NoteText(_Strict):
    own_text: str = Field(max_length=10_000)


class CourseRatingWrite(_Strict):
    # No title on purpose: the course title comes from the database, never from the browser.
    course_id: str = Field(min_length=1, max_length=80)
    smiley: Literal["gut", "mittel", "schlecht"]
    stichworte: list[str] = Field(default_factory=list, max_length=20)


def learner_id(user: PublicUser, org_id: int | None) -> str:
    """The person as Learning learner; same person, same id across sessions."""
    raw = f"lh-{org_id or 0}-{user.user_uuid}"
    return _UNSAFE.sub("-", raw)[:128]


def _person(user: PublicUser) -> PublicUser:
    if not isinstance(user, PublicUser) or not getattr(user, "user_uuid", None):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="sign in to practise")
    return user


async def _call(tool: str, event: dict[str, Any], *, write: bool = False, fresh: bool = False) -> dict[str, Any]:
    url = os.environ.get(MCP_URL_ENV, "http://learning-mcp:8091/mcp")
    event = {"invocation_id": str(uuid4()), "correlation_id": str(uuid4()), **event}
    if write and fresh:
        # A new session on every start; a deterministic key would replay the first one forever.
        event["idempotency_key"] = f"lh-{uuid4().hex}"
    elif write:
        keyed = {k: v for k, v in event.items() if k not in ("invocation_id", "correlation_id")}
        event["idempotency_key"] = "lh-" + hashlib.sha256(
            (tool + json.dumps(keyed, sort_keys=True)).encode()
        ).hexdigest()[:40]
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": event}}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            response = await client.post(url, json=body)
    except httpx.HTTPError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="learning unavailable") from error
    message = response.json() if response.status_code == 200 else {}
    try:
        payload = json.loads(message["result"]["content"][0]["text"])
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="learning gave no answer") from error
    if message["result"].get("isError"):
        error = payload.get("error")
        detail = error.get("message") if isinstance(error, dict) else str(error or "rejected")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(detail)[:300])
    return {"state": payload.get("state"), "result": _absolute_media(payload.get("result") or {}),
            "evidence": payload.get("evidence")}


_MEDIA_PATH = re.compile(r"^/lernsequenz-medien/[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.(png|jpg|webp)$")


def _absolute_media(result: dict[str, Any]) -> dict[str, Any]:
    """Pictures of a task (drawn terminal windows) are served by learning-api: their paths
    get the player origin. Anything else in an image field is dropped, as is every picture
    when no origin is configured (the page would load it from its own host)."""
    task = result.get("task") if isinstance(result, dict) else None
    presentation = task.get("presentation") if isinstance(task, dict) else None
    if not isinstance(presentation, dict):
        return result
    origin = _player_origin()

    def fix(entry: dict[str, Any]) -> None:
        image = entry.get("image")
        if image is None:
            return
        if origin and isinstance(image, str) and _MEDIA_PATH.fullmatch(image):
            entry["image"] = origin + image
        else:
            entry.pop("image")

    fix(presentation)
    for side in ("left", "right"):
        for entry in presentation.get(side) or []:
            if isinstance(entry, dict):
                fix(entry)
    return result


def _actor(user: PublicUser, org_id: int | None) -> dict[str, str]:
    return {"actor_id": learner_id(user, org_id), "actor_type": "local_user"}


@router.post("/practice/sessions")
async def start_session(
    payload: SessionStart,
    request: Request,
    current_user: PublicUser = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    user = _person(current_user)
    course = await _course_by_public_id(db_session, payload.course_id.removeprefix("course_"))
    await _authorize_course(request, db_session, user, course, AccessAction.READ)
    state = await _state_for_course(db_session, course)
    blueprint = {"max_attempts": 20} if payload.mode == "training" else {"item_count": 10}
    return await _call("learning_session_start", {
        "event_type": "learning.session.start",
        "actor": _actor(user, await _org_of(db_session, user)),
        "course_id": str(UUID(course.course_uuid.removeprefix("course_"))),
        "payload": {"course_revision": state.revision, "mode": payload.mode, "blueprint": blueprint},
    }, write=True, fresh=True)


async def _org_of(db_session: AsyncSession, user: PublicUser) -> int:
    """The person's organisation, from the server; never taken from the browser."""
    org_id = (
        await db_session.execute(
            select(UserOrganization.org_id).where(UserOrganization.user_id == user.id).order_by(UserOrganization.id)
        )
    ).scalars().first()
    if org_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="no organisation")
    return int(org_id)


@router.get("/practice/sessions/{session_id}")
async def current_task(
    session_id: UUID,
    current_user: PublicUser = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    user = _person(current_user)
    org_id = await _org_of(db_session, user)
    return await _call("learning_task_next", {
        "event_type": "learning.task.next", "actor": _actor(user, org_id), "session_id": str(session_id), "payload": {},
    })


@router.get("/practice/player-token")
async def player_token_for_embed(
    current_user: PublicUser = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
) -> dict[str, str | None]:
    """A short-lived signed token the embedded sequence player sends to learning-api, so
    answers and notes there count for this person (learning-api verifies it with the
    shared service key)."""
    from src.services.learning.person_token import person_token

    user = _person(current_user)
    return {"token": person_token(learner_id(user, await _org_of(db_session, user))), "origin": _player_origin()}


def _player_origin() -> str | None:
    """The one origin the web may hand the person token to; nothing when not configured."""
    parts = urlsplit(os.environ.get("LEARNHOUSE_LEARNING_PLAYER_ORIGIN", "").strip())
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme in ("http", "https") and parts.netloc else None


@router.post("/practice/sessions/{session_id}/answer")
async def answer(
    session_id: UUID,
    payload: AnswerWrite,
    current_user: PublicUser = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    user = _person(current_user)
    org_id = await _org_of(db_session, user)
    return await _call("learning_task_answer", {
        "event_type": "learning.task.answer", "actor": _actor(user, org_id), "session_id": str(session_id),
        "expected_revision": payload.revision, "payload": {"answer": payload.answer},
    }, write=True)


@router.post("/practice/sessions/{session_id}/hint")
async def hint(
    session_id: UUID,
    payload: HintRequest,
    current_user: PublicUser = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    user = _person(current_user)
    org_id = await _org_of(db_session, user)
    return await _call("learning_hint_request", {
        "event_type": "learning.hint.request", "actor": _actor(user, org_id), "session_id": str(session_id),
        "payload": {"task_id": payload.task_id},
    })


@router.post("/practice/sessions/{session_id}/canvas")
async def open_canvas(
    session_id: UUID,
    payload: CanvasOpen,
    current_user: PublicUser = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Open the drawing task; Learning answers with its signed drawing page for this person."""
    user = _person(current_user)
    actor = _actor(user, await _org_of(db_session, user))
    # Same reference for the same task and person: reopening shows the same canvas.
    ref = "lh-z-" + hashlib.sha256(f"{session_id}:{payload.activity_id}:{actor['actor_id']}".encode()).hexdigest()[:32]
    opened = await _call("learning_canvas_open", {
        "event_type": "learning.canvas.open", "actor": actor, "session_id": str(session_id),
        "payload": {"activity_id": str(payload.activity_id), "session_ref": ref},
    })
    page_url = opened["result"].get("page_url")
    if not isinstance(page_url, str) or not page_url.startswith(("https://", "http://")):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="drawing page unavailable")
    return {"page_url": page_url}


@router.post("/practice/sessions/{session_id}/tutor")
async def tutor(
    session_id: UUID,
    course_id: str,
    payload: TutorQuestion,
    current_user: PublicUser = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    user = _person(current_user)
    org_id = await _org_of(db_session, user)
    return await _call("learning_tutor_ask", {
        "event_type": "learning.tutor.ask", "actor": _actor(user, org_id), "session_id": str(session_id),
        "course_id": str(UUID(course_id.removeprefix("course_"))), "payload": {"question": payload.question},
    })


# --- notes: kept by learning-api per person, read and annotated through this backend ---

NOTES_BASE_ENV = "LEARNING_RETRIEVAL_SERVICE_URL"   # learning-api, already configured for retrieval
_NOTE_ID = re.compile(r"^[0-9a-fA-F-]{36}$")


async def _notes_request(
    method: str, path: str, user: PublicUser, db_session: AsyncSession, *, json: dict[str, Any] | None = None,
    not_found: str = "note not found", pass_400: bool = False,
) -> dict[str, Any]:
    """learning-api's notes API, always for the signed-in person: the service key and the
    learner id come from this server, never from the browser."""
    key = os.environ.get(LOCAL_LEARNING_SERVICE_KEY_ENV, "")
    if len(key) < 32:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="notes are not configured")
    base = os.environ.get(NOTES_BASE_ENV, "http://learning-api:8090").rstrip("/")
    headers = {
        "X-LearnHouse-Learning-Service-Key": key,
        "X-Learning-Actor": learner_id(user, await _org_of(db_session, user)),
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, f"{base}{path}", headers=headers, json=json)
    except httpx.HTTPError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="learning unavailable") from error
    if response.status_code == 404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found)
    if pass_400 and response.status_code == 400:
        try:
            body = response.json()
        except ValueError:
            body = None
        code = body.get("code") if isinstance(body, dict) else None
        message = body.get("message") if isinstance(body, dict) else None
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={
            "code": str(code or "bewertung_ungueltig")[:60],
            "message": str(message or "Die Bewertung ist nicht gültig.")[:200],
        })
    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="learning gave no answer")
    return response.json()


@router.get("/practice/notes")
async def list_notes(
    current_user: PublicUser = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    return await _notes_request("GET", "/api/v1/notizen", _person(current_user), db_session)


@router.patch("/practice/notes/{note_id}")
async def set_note_text(
    note_id: str,
    payload: NoteText,
    current_user: PublicUser = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    if not _NOTE_ID.match(note_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="note id is not valid")
    return await _notes_request(
        "PATCH", f"/api/v1/notizen/{note_id}", _person(current_user), db_session, json={"own_text": payload.own_text},
    )


# --- course rating: one rating per person and course, kept by learning-api ---

@router.post("/practice/course-rating")
async def rate_course(
    payload: CourseRatingWrite,
    request: Request,
    current_user: PublicUser = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    user = _person(current_user)
    course = await _course_by_public_id(db_session, payload.course_id.removeprefix("course_"))
    await _authorize_course(request, db_session, user, course, AccessAction.READ)
    return await _notes_request(
        "POST", "/api/v1/kursbewertung", user, db_session,
        json={
            "course_id": str(UUID(course.course_uuid.removeprefix("course_"))),
            "kurs_titel": course.name,
            "smiley": payload.smiley,
            "stichworte": payload.stichworte,
        },
        not_found="course not found", pass_400=True,
    )


@router.get("/practice/course-rating/{course_id}")
async def get_course_rating(
    course_id: str,
    request: Request,
    current_user: PublicUser = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    user = _person(current_user)
    try:
        course = await _course_by_public_id(db_session, course_id.removeprefix("course_"))
        await _authorize_course(request, db_session, user, course, AccessAction.READ)
        public_id = str(UUID(course.course_uuid.removeprefix("course_")))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="course not found") from error
    return await _notes_request(
        "GET", f"/api/v1/kursbewertung/{public_id}", user, db_session, not_found="rating not found",
    )
