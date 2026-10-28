from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid5

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
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
from src.services.courses.activities.versioning import stage_activity_version
from src.services.learning.einbettung import _is_sequence_block
from src.services.learning.factory_draft import _TASK_NOTE
from src.services.learning.rich_text import lesson_doc, task_doc

_WERKSTATT_NAMESPACE = UUID("ae21a8f6-34d8-558c-8450-330269534eff")
_FREIGABEN = "werkstatt_freigaben"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WerkstattEintrag(_Strict):
    key: str = Field(min_length=1, max_length=200)
    art: Literal["lesson", "task"]
    titel: str = Field(min_length=1, max_length=500)
    markdown: str | None = Field(default=None, max_length=100_000)
    claims: list[str] = Field(default_factory=list, max_length=2_000)
    prompt: str | None = Field(default=None, max_length=20_000)


class WerkstattKapitel(_Strict):
    titel: str = Field(min_length=1, max_length=300)
    eintraege: list[WerkstattEintrag] = Field(max_length=5_000)


class WerkstattStandWrite(_Strict):
    expected_revision: int = Field(ge=0)
    freigabe_id: str = Field(min_length=1, max_length=200)
    kapitel: list[WerkstattKapitel] = Field(max_length=500)


class WerkstattStandRead(_Strict):
    revision: int
    aktualisiert: int
    neu: int
    unveroeffentlicht: int


def _content_for(entry: WerkstattEintrag) -> dict:
    if entry.art == "lesson":
        body = entry.markdown or ""
        return {
            **lesson_doc(body, entry.claims),
            "markdown": body,
            "claims": [{"text": claim} for claim in entry.claims],
        }
    prompt = entry.prompt or entry.titel
    return {**task_doc(prompt, _TASK_NOTE), "prompt": prompt}


def _with_kept_embeds(old: dict | None, new: dict) -> dict:
    """Learning's sequence players live in the lesson page; a new text must not drop them."""
    kept = [
        block
        for block in (old or {}).get("content", [])
        if isinstance(block, dict) and _is_sequence_block(block)
    ]
    if kept:
        new = {**new, "content": [*new.get("content", []), *kept]}
    return new


def _key_of(activity: Activity) -> str | None:
    meta = activity.extra_metadata or {}
    return meta.get("werkstatt_key") or meta.get("draft_activity_id")


async def apply_werkstatt_stand(
    *,
    db_session: AsyncSession,
    course: Course,
    state: LearningCourseState,
    payload: WerkstattStandWrite,
    user_id: int | None = None,
) -> WerkstattStandRead:
    done = (state.source_metadata or {}).get(_FREIGABEN, {})
    if payload.freigabe_id in done:
        return WerkstattStandRead.model_validate(done[payload.freigabe_id])

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

    now = str(datetime.now())
    course_id = int(course.id or 0)
    published = bool(course.published)
    activities = (
        await db_session.execute(select(Activity).where(Activity.course_id == course.id))
    ).scalars().all()
    by_key: dict[str, Activity] = {}
    for activity in activities:
        key = _key_of(activity)
        if key is not None:
            by_key.setdefault(key, activity)
    chapters = {
        chapter.name: chapter
        for chapter in (
            await db_session.execute(select(Chapter).where(Chapter.course_id == course.id))
        ).scalars().all()
    }
    course_links = (
        await db_session.execute(
            select(CourseChapter).where(CourseChapter.course_id == course.id)
        )
    ).scalars().all()
    next_chapter_order = max((link.order for link in course_links), default=0) + 1

    updated = created = 0
    seen: set[str] = set()
    for kapitel in payload.kapitel:
        chapter = chapters.get(kapitel.titel)
        if chapter is None:
            chapter = Chapter(
                name=kapitel.titel,
                description="",
                thumbnail_image="",
                org_id=course.org_id,
                course_id=course_id,
                chapter_uuid=f"chapter_{uuid5(_WERKSTATT_NAMESPACE, f'werkstatt:{course.course_uuid}:chapter:{kapitel.titel}')}",
                creation_date=now,
                update_date=now,
                extra_metadata={"werkstatt_generated": True},
            )
            db_session.add(chapter)
            await db_session.flush()
            db_session.add(
                CourseChapter(
                    order=next_chapter_order,
                    course_id=course_id,
                    chapter_id=int(chapter.id or 0),
                    org_id=course.org_id,
                    creation_date=now,
                    update_date=now,
                )
            )
            next_chapter_order += 1
            chapters[kapitel.titel] = chapter
        chapter_id = int(chapter.id or 0)
        links = {
            link.activity_id: link
            for link in (
                await db_session.execute(
                    select(ChapterActivity).where(ChapterActivity.course_id == course.id)
                )
            ).scalars().all()
        }

        ordered: list[ChapterActivity] = []
        for entry in kapitel.eintraege:
            seen.add(entry.key)
            content = _content_for(entry)
            activity = by_key.get(entry.key)
            if activity is not None:
                stage_activity_version(activity, user_id, db_session)
                activity.content = _with_kept_embeds(activity.content, content)
                activity.name = entry.titel
                activity.current_version = (activity.current_version or 1) + 1
                activity.update_date = now
                if published:
                    activity.published = True
                activity.extra_metadata = {
                    **(activity.extra_metadata or {}),
                    "werkstatt_key": entry.key,
                }
                db_session.add(activity)
                updated += 1
            else:
                activity = Activity(
                    name=entry.titel,
                    activity_type=ActivityTypeEnum.TYPE_DYNAMIC,
                    activity_sub_type=ActivitySubTypeEnum.SUBTYPE_DYNAMIC_PAGE,
                    content=content,
                    details={"learning_kind": entry.art},
                    published=published,
                    org_id=course.org_id,
                    course_id=course_id,
                    activity_uuid=f"activity_{uuid5(_WERKSTATT_NAMESPACE, f'werkstatt:{course.course_uuid}:{entry.key}')}",
                    creation_date=now,
                    update_date=now,
                    extra_metadata={
                        "werkstatt_generated": True,
                        "learning_kind": entry.art,
                        "werkstatt_key": entry.key,
                    },
                )
                db_session.add(activity)
                await db_session.flush()
                by_key[entry.key] = activity
                created += 1
            await db_session.flush()
            link = links.get(int(activity.id or 0))
            if link is None:
                link = ChapterActivity(
                    order=0,
                    chapter_id=chapter_id,
                    activity_id=int(activity.id or 0),
                    course_id=course_id,
                    org_id=course.org_id,
                    creation_date=now,
                    update_date=now,
                )
                db_session.add(link)
            else:
                link.chapter_id = chapter_id
                link.update_date = now
            ordered.append(link)
        for position, link in enumerate(ordered, start=1):
            link.order = position

    unpublished = 0
    for key, activity in by_key.items():
        if key not in seen and activity.published:
            activity.published = False
            activity.update_date = now
            db_session.add(activity)
            unpublished += 1
    await db_session.flush()

    result = WerkstattStandRead(
        revision=state.revision,
        aktualisiert=updated,
        neu=created,
        unveroeffentlicht=unpublished,
    )
    state.source_metadata = {
        **(state.source_metadata or {}),
        _FREIGABEN: {**done, payload.freigabe_id: result.model_dump(mode="json")},
    }
    return result
