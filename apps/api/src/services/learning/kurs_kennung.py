"""The Learning ``course_id`` of a LearnHouse course: its ``course_uuid`` without ``course_``.

Lives in the service layer so services (``verwaltung``) and the learning routers share one
definition without a router import inside a service."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status

from src.db.courses.courses import Course

_COURSE_PREFIX = "course_"


def _stable_uuid(value: str, prefix: str) -> str:
    raw = value[len(prefix) :] if value.startswith(prefix) else value
    try:
        return str(UUID(raw))
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local learning resource has an invalid stable identifier",
        ) from error


def _course_id(course: Course) -> str:
    return _stable_uuid(course.course_uuid, _COURSE_PREFIX)
