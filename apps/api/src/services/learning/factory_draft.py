from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid5

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.db.courses.activities import (
    Activity,
    ActivitySubTypeEnum,
    ActivityTypeEnum,
)
from src.db.courses.chapter_activities import ChapterActivity
from src.db.courses.chapters import Chapter
from src.db.courses.course_chapters import CourseChapter
from src.db.courses.courses import Course
from src.db.courses.learning_state import LearningCourseState
from src.services.learning.rich_text import lesson_doc, task_doc


_FACTORY_NAMESPACE = UUID("ae21a8f6-34d8-558c-8450-330269534eff")
_TASK_NOTE = (
    "Diese Aufgabe bearbeiten Sie in der Übung mit dem Lern-Tutor. Dort wird Ihre "
    "Antwort bewertet, und Sie bekommen Hinweise."
)
_HASH_PATTERN = r"^[0-9a-f]{64}$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceRef(_Strict):
    source_id: str = Field(min_length=36, max_length=36)
    revision: int = Field(ge=1)
    content_hash: str = Field(pattern=_HASH_PATTERN)


class Citation(_Strict):
    citation_id: str = Field(min_length=36, max_length=36)
    source_id: str = Field(min_length=36, max_length=36)
    source_revision: int = Field(ge=1)
    chunk_id: str = Field(min_length=36, max_length=36)
    content_hash: str = Field(pattern=_HASH_PATTERN)
    locator: dict[str, str | int] = Field(min_length=1, max_length=20)


class Claim(_Strict):
    claim_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=20_000)
    citation_ids: list[str] = Field(min_length=1, max_length=100)


class Concept(_Strict):
    concept_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)


class ChapterDraft(_Strict):
    chapter_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    lesson_ids: list[str] = Field(min_length=1, max_length=1_000)
    activity_ids: list[str] = Field(min_length=1, max_length=2_000)


class LessonDraft(_Strict):
    lesson_id: str = Field(min_length=1, max_length=200)
    chapter_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=100_000)
    concept_ids: list[str] = Field(min_length=1, max_length=200)
    claims: list[Claim] = Field(max_length=2_000)


class Rubric(_Strict):
    criterion_id: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2_000)
    points: int = Field(ge=1, le=1_000)


class ActivityDraft(_Strict):
    activity_id: str = Field(min_length=1, max_length=200)
    chapter_id: str = Field(min_length=1, max_length=200)
    type: Literal["quiz", "open", "case", "code", "penecho_canvas"]
    concept_ids: list[str] = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=20_000)
    expected_answer: str = Field(min_length=1, max_length=50_000)
    citation_ids: list[str] = Field(min_length=1, max_length=100)
    rubric: list[Rubric] = Field(max_length=100)


class FactoryCourseDraft(_Strict):
    schema_version: Literal["course-draft-v1"]
    job_id: str = Field(min_length=36, max_length=36)
    attempt_number: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=500)
    outcomes: list[str] = Field(min_length=1, max_length=100)
    source_provenance: list[SourceRef] = Field(min_length=1, max_length=256)
    citations: list[Citation] = Field(min_length=1, max_length=10_000)
    concepts: list[Concept] = Field(min_length=1, max_length=2_000)
    chapters: list[ChapterDraft] = Field(min_length=1, max_length=500)
    lessons: list[LessonDraft] = Field(min_length=1, max_length=5_000)
    activities: list[ActivityDraft] = Field(min_length=1, max_length=10_000)

    @model_validator(mode="after")
    def validate_graph(self) -> "FactoryCourseDraft":
        for values in (
            [item.chapter_id for item in self.chapters],
            [item.lesson_id for item in self.lessons],
            [item.activity_id for item in self.activities],
            [item.concept_id for item in self.concepts],
            [item.citation_id for item in self.citations],
        ):
            if len(values) != len(set(values)):
                raise ValueError("factory draft identifiers must be unique")
        chapter_ids = {item.chapter_id for item in self.chapters}
        if any(item.chapter_id not in chapter_ids for item in self.lessons):
            raise ValueError("factory lesson references an unknown chapter")
        if any(item.chapter_id not in chapter_ids for item in self.activities):
            raise ValueError("factory activity references an unknown chapter")
        return self


class FactoryDraftWrite(_Strict):
    expected_revision: int = Field(ge=0)
    draft_hash: str = Field(pattern=_HASH_PATTERN)
    draft: FactoryCourseDraft

    @model_validator(mode="after")
    def validate_hash(self) -> "FactoryDraftWrite":
        if self.draft_hash != _hash_json(self.draft.model_dump(mode="json")):
            raise ValueError("factory draft hash mismatch")
        return self


class FactoryDraftRead(_Strict):
    factory_job_id: str
    attempt_number: int
    draft_hash: str
    revision: int
    chapter_count: int
    activity_count: int


async def apply_factory_draft(
    *,
    db_session: AsyncSession,
    course: Course,
    state: LearningCourseState,
    payload: FactoryDraftWrite,
) -> FactoryDraftRead:
    if course.published:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="published_course_is_immutable",
        )
    current = _metadata_read(state)
    if current is not None and (
        current.factory_job_id == payload.draft.job_id
        and current.attempt_number == payload.draft.attempt_number
        and current.draft_hash == payload.draft_hash
    ):
        return current
    advanced = await db_session.execute(
        update(LearningCourseState)
        .where(
            LearningCourseState.id == state.id,
            LearningCourseState.revision == payload.expected_revision,
        )
        .values(revision=payload.expected_revision + 1)
    )
    if advanced.rowcount != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="revision_conflict"
        )
    await db_session.refresh(state)

    await _delete_prior_factory_structure(db_session, course)
    now = str(datetime.now())
    chapter_rows: dict[str, Chapter] = {}
    for order, chapter in enumerate(payload.draft.chapters, start=1):
        row = Chapter(
            name=chapter.title,
            description="",
            thumbnail_image="",
            org_id=course.org_id,
            course_id=int(course.id or 0),
            chapter_uuid=f"chapter_{_stable_id(payload.draft, 'chapter', chapter.chapter_id)}",
            creation_date=now,
            update_date=now,
            extra_metadata={
                "factory_generated": True,
                "factory_job_id": payload.draft.job_id,
                "factory_attempt": payload.draft.attempt_number,
                "draft_chapter_id": chapter.chapter_id,
            },
        )
        db_session.add(row)
        await db_session.flush()
        db_session.add(
            CourseChapter(
                order=order,
                course_id=int(course.id or 0),
                chapter_id=int(row.id or 0),
                org_id=course.org_id,
                creation_date=now,
                update_date=now,
            )
        )
        chapter_rows[chapter.chapter_id] = row

    activity_count = 0
    for lesson in payload.draft.lessons:
        chapter = chapter_rows[lesson.chapter_id]
        await _add_activity(
            db_session,
            course=course,
            chapter=chapter,
            draft=payload.draft,
            source_id=lesson.lesson_id,
            title=lesson.title,
            kind="lesson",
            content={
                **lesson_doc(lesson.body, [claim.text for claim in lesson.claims]),
                "markdown": lesson.body,
                "concept_ids": lesson.concept_ids,
                "claims": [item.model_dump(mode="json") for item in lesson.claims],
            },
            order=activity_count + 1,
            now=now,
        )
        activity_count += 1
    for activity in payload.draft.activities:
        chapter = chapter_rows[activity.chapter_id]
        await _add_activity(
            db_session,
            course=course,
            chapter=chapter,
            draft=payload.draft,
            source_id=activity.activity_id,
            title=activity.prompt,
            kind=activity.type,
            # The page reaches the learner's browser: the question only. Expected answer and
            # rubric stay in the Learning engine, which grades.
            content={
                **task_doc(activity.prompt, _TASK_NOTE),
                "prompt": activity.prompt,
                "concept_ids": activity.concept_ids,
                "citation_ids": activity.citation_ids,
            },
            order=activity_count + 1,
            now=now,
        )
        activity_count += 1

    state.review_status = "pending"
    result = FactoryDraftRead(
        factory_job_id=payload.draft.job_id,
        attempt_number=payload.draft.attempt_number,
        draft_hash=payload.draft_hash,
        revision=state.revision,
        chapter_count=len(payload.draft.chapters),
        activity_count=activity_count,
    )
    state.source_metadata = {
        **state.source_metadata,
        "factory_draft": result.model_dump(mode="json"),
    }
    return result


async def _add_activity(
    db_session: AsyncSession,
    *,
    course: Course,
    chapter: Chapter,
    draft: FactoryCourseDraft,
    source_id: str,
    title: str,
    kind: str,
    content: dict,
    order: int,
    now: str,
) -> None:
    # Lessons and tasks are page documents: the Markdown subtype only loads a URL and
    # the assignment subtype rendered an empty page with a grading button.
    row = Activity(
        name=title,
        activity_type=ActivityTypeEnum.TYPE_DYNAMIC,
        activity_sub_type=ActivitySubTypeEnum.SUBTYPE_DYNAMIC_PAGE,
        content=content,
        details={"learning_kind": kind},
        published=False,
        org_id=course.org_id,
        course_id=int(course.id or 0),
        activity_uuid=f"activity_{_stable_id(draft, kind, source_id)}",
        creation_date=now,
        update_date=now,
        extra_metadata={
            "factory_generated": True,
            "factory_job_id": draft.job_id,
            "factory_attempt": draft.attempt_number,
            "learning_kind": kind,
            "draft_activity_id": source_id,
        },
    )
    db_session.add(row)
    await db_session.flush()
    db_session.add(
        ChapterActivity(
            order=order,
            chapter_id=int(chapter.id or 0),
            activity_id=int(row.id or 0),
            course_id=int(course.id or 0),
            org_id=course.org_id,
            creation_date=now,
            update_date=now,
        )
    )


async def _delete_prior_factory_structure(
    db_session: AsyncSession, course: Course
) -> None:
    chapters = (
        await db_session.execute(select(Chapter).where(Chapter.course_id == course.id))
    ).scalars().all()
    generated = [
        chapter
        for chapter in chapters
        if chapter.extra_metadata and chapter.extra_metadata.get("factory_generated") is True
    ]
    for chapter in generated:
        links = (
            await db_session.execute(
                select(ChapterActivity).where(ChapterActivity.chapter_id == chapter.id)
            )
        ).scalars().all()
        for link in links:
            activity = await db_session.get(Activity, link.activity_id)
            await db_session.delete(link)
            if activity is not None:
                await db_session.delete(activity)
        course_links = (
            await db_session.execute(
                select(CourseChapter).where(CourseChapter.chapter_id == chapter.id)
            )
        ).scalars().all()
        for link in course_links:
            await db_session.delete(link)
        await db_session.delete(chapter)
    await db_session.flush()


def factory_draft_readback(state: LearningCourseState) -> FactoryDraftRead:
    result = _metadata_read(state)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return result


def _metadata_read(state: LearningCourseState) -> FactoryDraftRead | None:
    value = state.source_metadata.get("factory_draft")
    return FactoryDraftRead.model_validate(value) if value is not None else None


def _stable_id(draft: FactoryCourseDraft, kind: str, source_id: str) -> str:
    return str(uuid5(_FACTORY_NAMESPACE, f"{draft.job_id}:{draft.attempt_number}:{kind}:{source_id}"))


def _hash_json(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
