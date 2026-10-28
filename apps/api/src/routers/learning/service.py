from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from src.core.events.database import get_db_session
from src.core.learning_mode import is_local_learning_mode_enabled, provision_local_learning_mode
from src.db.courses.activities import Activity
from src.db.courses.chapters import Chapter
from src.db.courses.courses import Course, CourseCreate
from src.db.courses.learning_state import (
    LearningCourseCollectionState,
    LearningCourseSource,
    LearningCourseState,
)
from src.db.media.media import Media, MediaTypeEnum
from src.db.resource_authors import (
    ResourceAuthor,
    ResourceAuthorshipEnum,
    ResourceAuthorshipStatusEnum,
)
from src.db.users import PublicUser
from src.security.rbac import AccessAction, check_resource_access
from src.services.courses.courses import create_course, get_course
from src.services.learning.einbettung import SequenceEmbedWrite, embed_sequences
from src.services.learning.kunden import CustomerCreate, CustomerRead, create_customer, list_customers
from src.services.learning.factory_draft import (
    FactoryDraftRead,
    FactoryDraftWrite,
    apply_factory_draft,
    factory_draft_readback,
)
from src.services.learning.werkstatt_stand import (
    WerkstattStandRead,
    WerkstattStandWrite,
    apply_werkstatt_stand,
)


LOCAL_LEARNING_SERVICE_KEY_ENV = "LEARNHOUSE_LEARNING_SERVICE_KEY"
LOCAL_LEARNING_SERVICE_HEADER = "X-LearnHouse-Learning-Service-Key"
LOCAL_LEARNING_SERVICE_KEY_MIN_LENGTH = 32
_COURSE_PREFIX = "course_"
_CHAPTER_PREFIX = "chapter_"

router = APIRouter()


class AggregateRead(BaseModel):
    aggregate_id: str
    revision: int


class CourseRead(BaseModel):
    course_id: str
    title: str
    description: str
    revision: int
    review_status: str
    published: bool


class CourseEnvelope(BaseModel):
    course: CourseRead


class CourseListEnvelope(BaseModel):
    aggregate: AggregateRead
    courses: list[CourseRead]


class SourceRead(BaseModel):
    source_id: str
    title: str
    revision: int


class SourceEnvelope(BaseModel):
    source: SourceRead


class ChapterRead(BaseModel):
    chapter_id: str
    course_id: str
    title: str
    revision: int


class ChapterEnvelope(BaseModel):
    chapter: ChapterRead


class ProgressRead(BaseModel):
    course_id: str
    completed: int
    total: int
    revision: int


class ProgressEnvelope(BaseModel):
    progress: ProgressRead


class FactoryDraftEnvelope(BaseModel):
    draft: FactoryDraftRead


class CreateCourseRequest(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=512)]
    description: str = ""
    about: str = ""


class SourceImportRequest(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=512)]
    source_url: Annotated[str, Field(min_length=1, max_length=2048)]
    expected_revision: Annotated[int, Field(ge=0)]


class ReviewRequest(BaseModel):
    review: Literal["approved", "changes_requested"]
    expected_revision: Annotated[int, Field(ge=0)]


class PublishRequest(BaseModel):
    expected_revision: Annotated[int, Field(ge=0)]


def require_local_learning_service(request: Request) -> None:
    if not is_local_learning_mode_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    configured_key = os.environ.get(LOCAL_LEARNING_SERVICE_KEY_ENV, "")
    if len(configured_key) < LOCAL_LEARNING_SERVICE_KEY_MIN_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local learning service is not configured securely",
        )

    supplied_key = request.headers.get(LOCAL_LEARNING_SERVICE_HEADER, "")
    if not hmac.compare_digest(
        supplied_key.encode("utf-8"), configured_key.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid local learning service credentials",
        )


async def _local_owner(db_session: AsyncSession) -> tuple[PublicUser, int]:
    """Resolve the sole local owner server-side; request identity headers are ignored."""
    provisioned = await provision_local_learning_mode(db_session)
    return (
        PublicUser.model_validate(provisioned.user),
        int(provisioned.organization.id or 0),
    )


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


def _chapter_id(chapter: Chapter) -> str:
    return _stable_uuid(chapter.chapter_uuid, _CHAPTER_PREFIX)


async def _course_by_public_id(
    db_session: AsyncSession, course_id: str
) -> Course:
    try:
        normalized = str(UUID(course_id))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error
    course = (
        await db_session.execute(
            select(Course).where(
                col(Course.course_uuid).in_((normalized, f"{_COURSE_PREFIX}{normalized}"))
            )
        )
    ).scalars().first()
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return course


async def _chapter_by_public_id(
    db_session: AsyncSession, chapter_id: str
) -> Chapter:
    try:
        normalized = str(UUID(chapter_id))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error
    chapter = (
        await db_session.execute(
            select(Chapter).where(
                col(Chapter.chapter_uuid).in_((normalized, f"{_CHAPTER_PREFIX}{normalized}"))
            )
        )
    ).scalars().first()
    if chapter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return chapter


async def _state_for_course(
    db_session: AsyncSession, course: Course
) -> LearningCourseState:
    state = (
        await db_session.execute(
            select(LearningCourseState).where(
                LearningCourseState.course_id == course.id
            )
        )
    ).scalars().first()
    if state is not None:
        return state
    state = LearningCourseState(course_id=int(course.id or 0))
    db_session.add(state)
    await db_session.flush()
    return state


async def _collection_fingerprint(
    db_session: AsyncSession, org_id: int
) -> str:
    rows = (
        await db_session.execute(
            select(Course, LearningCourseState)
            .outerjoin(
                LearningCourseState, LearningCourseState.course_id == Course.id
            )
            .where(Course.org_id == org_id)
            .order_by(Course.creation_date, Course.id)
        )
    ).all()
    values = [
        (_course_id(course), state.revision if state is not None else 0)
        for course, state in rows
    ]
    return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()


async def _collection_state(
    db_session: AsyncSession, org_id: int, *, advance: bool = False
) -> LearningCourseCollectionState:
    fingerprint = await _collection_fingerprint(db_session, org_id)
    state = (
        await db_session.execute(
            select(LearningCourseCollectionState).where(
                LearningCourseCollectionState.org_id == org_id
            )
        )
    ).scalars().first()
    if state is None:
        state = LearningCourseCollectionState(org_id=org_id, fingerprint=fingerprint)
        db_session.add(state)
        await db_session.flush()
        if advance:
            state.revision = 1
        return state
    if advance or state.fingerprint != fingerprint:
        state.revision += 1
        state.fingerprint = fingerprint
    return state


def _course_read(course: Course, state: LearningCourseState) -> CourseRead:
    return CourseRead(
        course_id=_course_id(course),
        title=course.name,
        description=course.description or "",
        revision=state.revision,
        review_status=state.review_status,
        published=bool(course.published),
    )


async def _authorize_course(
    request: Request,
    db_session: AsyncSession,
    owner: PublicUser,
    course: Course,
    action: AccessAction,
) -> None:
    await check_resource_access(
        request, db_session, owner, course.course_uuid, action
    )


async def _compare_and_advance(
    db_session: AsyncSession,
    state: LearningCourseState,
    expected_revision: int,
) -> int:
    result = await db_session.execute(
        update(LearningCourseState)
        .where(
            LearningCourseState.id == state.id,
            LearningCourseState.revision == expected_revision,
        )
        .values(revision=expected_revision + 1)
    )
    if result.rowcount != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="revision_conflict",
        )
    await db_session.refresh(state)
    return state.revision


@router.get(
    "/courses",
    response_model=CourseListEnvelope,
    dependencies=[Depends(require_local_learning_service)],
)
async def list_courses(
    request: Request,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    db_session: AsyncSession = Depends(get_db_session),
) -> CourseListEnvelope:
    owner, org_id = await _local_owner(db_session)
    rows = (
        await db_session.execute(
            select(Course)
            .where(Course.org_id == org_id)
            .order_by(Course.creation_date, Course.id)
            .offset((page - 1) * limit)
            .limit(limit)
        )
    ).scalars().all()
    courses: list[CourseRead] = []
    for course in rows:
        await get_course(request, course.course_uuid, owner, db_session)
        courses.append(_course_read(course, await _state_for_course(db_session, course)))
    aggregate = await _collection_state(db_session, org_id)
    await db_session.commit()
    return CourseListEnvelope(
        aggregate=AggregateRead(aggregate_id="default", revision=aggregate.revision),
        courses=courses,
    )


@router.post(
    "/courses",
    response_model=CourseEnvelope,
    dependencies=[Depends(require_local_learning_service)],
)
async def create_revisioned_course(
    payload: CreateCourseRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
) -> CourseEnvelope:
    owner, org_id = await _local_owner(db_session)
    created = await create_course(
        request,
        org_id,
        CourseCreate(
            name=payload.title,
            description=payload.description,
            about=payload.about,
            org_id=org_id,
            public=False,
            open_to_contributors=False,
        ),
        owner,
        db_session,
    )
    course = await _course_by_public_id(
        db_session, _stable_uuid(created.course_uuid, _COURSE_PREFIX)
    )
    state = await _state_for_course(db_session, course)
    state.revision = 1
    await _collection_state(db_session, org_id, advance=True)
    await db_session.commit()
    return CourseEnvelope(course=_course_read(course, state))


@router.get(
    "/courses/{course_id}",
    response_model=CourseEnvelope,
    dependencies=[Depends(require_local_learning_service)],
)
async def open_course(
    course_id: str,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
) -> CourseEnvelope:
    owner, _ = await _local_owner(db_session)
    course = await _course_by_public_id(db_session, course_id)
    await get_course(request, course.course_uuid, owner, db_session)
    return CourseEnvelope(course=_course_read(course, await _state_for_course(db_session, course)))


@router.post(
    "/courses/{course_id}/sources",
    response_model=SourceEnvelope,
    dependencies=[Depends(require_local_learning_service)],
)
async def import_source(
    course_id: str,
    payload: SourceImportRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
) -> SourceEnvelope:
    owner, org_id = await _local_owner(db_session)
    course = await _course_by_public_id(db_session, course_id)
    await _authorize_course(request, db_session, owner, course, AccessAction.UPDATE)
    state = await _state_for_course(db_session, course)
    revision = await _compare_and_advance(db_session, state, payload.expected_revision)
    media = Media(
        name=payload.title,
        description="",
        media_type=MediaTypeEnum.EMBED,
        url=payload.source_url,
        public=False,
        org_id=org_id,
        media_uuid=f"media_{uuid4()}",
        creation_date=str(datetime.now()),
        update_date=str(datetime.now()),
    )
    db_session.add(media)
    await db_session.flush()
    db_session.add(
        ResourceAuthor(
            resource_uuid=media.media_uuid,
            user_id=owner.id,
            authorship=ResourceAuthorshipEnum.CREATOR,
            authorship_status=ResourceAuthorshipStatusEnum.ACTIVE,
            creation_date=str(datetime.now()),
            update_date=str(datetime.now()),
        )
    )
    source = LearningCourseSource(
        course_id=int(course.id or 0),
        media_id=int(media.id or 0),
        source_uuid=str(uuid4()),
        revision=revision,
        title=payload.title,
        source_url=payload.source_url,
    )
    db_session.add(source)
    state.source_metadata = {"count": int(state.source_metadata.get("count", 0)) + 1}
    await _collection_state(db_session, org_id, advance=True)
    await db_session.commit()
    return SourceEnvelope(
        source=SourceRead(
            source_id=source.source_uuid, title=source.title, revision=source.revision
        )
    )


@router.get(
    "/sources/{source_id}",
    response_model=SourceEnvelope,
    dependencies=[Depends(require_local_learning_service)],
)
async def get_source(
    source_id: str,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
) -> SourceEnvelope:
    owner, _ = await _local_owner(db_session)
    source = (
        await db_session.execute(
            select(LearningCourseSource).where(LearningCourseSource.source_uuid == source_id)
        )
    ).scalars().first()
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    course = (
        await db_session.execute(select(Course).where(Course.id == source.course_id))
    ).scalars().first()
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await _authorize_course(request, db_session, owner, course, AccessAction.READ)
    return SourceEnvelope(
        source=SourceRead(
            source_id=source.source_uuid, title=source.title, revision=source.revision
        )
    )


@router.put(
    "/courses/{course_id}/factory-draft",
    response_model=FactoryDraftEnvelope,
    dependencies=[Depends(require_local_learning_service)],
)
async def put_factory_draft(
    course_id: str,
    payload: FactoryDraftWrite,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
) -> FactoryDraftEnvelope:
    owner, _ = await _local_owner(db_session)
    course = await _course_by_public_id(db_session, course_id)
    await _authorize_course(request, db_session, owner, course, AccessAction.UPDATE)
    state = await _state_for_course(db_session, course)
    draft = await apply_factory_draft(
        db_session=db_session,
        course=course,
        state=state,
        payload=payload,
    )
    await db_session.commit()
    return FactoryDraftEnvelope(draft=draft)


@router.put(
    "/courses/{course_id}/werkstatt-stand",
    response_model=WerkstattStandRead,
    dependencies=[Depends(require_local_learning_service)],
)
async def put_werkstatt_stand(
    course_id: str,
    payload: WerkstattStandWrite,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
) -> WerkstattStandRead:
    """A released Werkstatt state into the course, also a published one, updating in place."""
    owner, _ = await _local_owner(db_session)
    course = await _course_by_public_id(db_session, course_id)
    await _authorize_course(request, db_session, owner, course, AccessAction.UPDATE)
    state = await _state_for_course(db_session, course)
    result = await apply_werkstatt_stand(
        db_session=db_session,
        course=course,
        state=state,
        payload=payload,
        user_id=getattr(owner, "id", None),
    )
    await db_session.commit()
    return result


@router.get(
    "/courses/{course_id}/factory-draft",
    response_model=FactoryDraftEnvelope,
    dependencies=[Depends(require_local_learning_service)],
)
async def get_factory_draft(
    course_id: str,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
) -> FactoryDraftEnvelope:
    owner, _ = await _local_owner(db_session)
    course = await _course_by_public_id(db_session, course_id)
    await _authorize_course(request, db_session, owner, course, AccessAction.READ)
    state = await _state_for_course(db_session, course)
    return FactoryDraftEnvelope(draft=factory_draft_readback(state))


@router.put(
    "/courses/{course_id}/lernsequenz-einbettungen",
    dependencies=[Depends(require_local_learning_service)],
)
async def put_sequence_embeds(
    course_id: str,
    payload: SequenceEmbedWrite,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Learning's sequence players in a factory lesson; also for published courses."""
    owner, _ = await _local_owner(db_session)
    course = await _course_by_public_id(db_session, course_id)
    await _authorize_course(request, db_session, owner, course, AccessAction.UPDATE)
    return await embed_sequences(db_session, course, payload)


@router.post(
    "/courses/{course_id}/review",
    response_model=CourseEnvelope,
    dependencies=[Depends(require_local_learning_service)],
)
async def review_course(
    course_id: str,
    payload: ReviewRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
) -> CourseEnvelope:
    owner, org_id = await _local_owner(db_session)
    course = await _course_by_public_id(db_session, course_id)
    await _authorize_course(request, db_session, owner, course, AccessAction.UPDATE)
    state = await _state_for_course(db_session, course)
    await _compare_and_advance(db_session, state, payload.expected_revision)
    state.review_status = payload.review
    await _collection_state(db_session, org_id, advance=True)
    await db_session.commit()
    return CourseEnvelope(course=_course_read(course, state))


@router.post(
    "/courses/{course_id}/publish",
    response_model=CourseEnvelope,
    dependencies=[Depends(require_local_learning_service)],
)
async def publish_course(
    course_id: str,
    payload: PublishRequest,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
) -> CourseEnvelope:
    owner, org_id = await _local_owner(db_session)
    course = await _course_by_public_id(db_session, course_id)
    await _authorize_course(request, db_session, owner, course, AccessAction.UPDATE)
    state = await _state_for_course(db_session, course)
    if state.review_status != "approved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="review_not_approved")
    await _compare_and_advance(db_session, state, payload.expected_revision)
    course.published = True
    activities = (
        await db_session.execute(select(Activity).where(Activity.course_id == course.id))
    ).scalars().all()
    for activity in activities:
        if (
            activity.extra_metadata
            and activity.extra_metadata.get("factory_generated") is True
        ):
            activity.published = True
    await _collection_state(db_session, org_id, advance=True)
    await db_session.commit()
    return CourseEnvelope(course=_course_read(course, state))


@router.get(
    "/chapters/{chapter_id}",
    response_model=ChapterEnvelope,
    dependencies=[Depends(require_local_learning_service)],
)
async def open_chapter(
    chapter_id: str,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
) -> ChapterEnvelope:
    owner, _ = await _local_owner(db_session)
    chapter = await _chapter_by_public_id(db_session, chapter_id)
    course = (
        await db_session.execute(select(Course).where(Course.id == chapter.course_id))
    ).scalars().first()
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await _authorize_course(request, db_session, owner, course, AccessAction.READ)
    state = await _state_for_course(db_session, course)
    return ChapterEnvelope(
        chapter=ChapterRead(
            chapter_id=_chapter_id(chapter),
            course_id=_course_id(course),
            title=chapter.name,
            revision=state.revision,
        )
    )


@router.get(
    "/courses/{course_id}/progress",
    response_model=ProgressEnvelope,
    dependencies=[Depends(require_local_learning_service)],
)
async def show_progress(
    course_id: str,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
) -> ProgressEnvelope:
    owner, _ = await _local_owner(db_session)
    course = await _course_by_public_id(db_session, course_id)
    await _authorize_course(request, db_session, owner, course, AccessAction.READ)
    state = await _state_for_course(db_session, course)
    total = int(state.source_metadata.get("count", 0))
    return ProgressEnvelope(
        progress=ProgressRead(
            course_id=_course_id(course),
            completed=total,
            total=total,
            revision=state.revision,
        )
    )


@router.post(
    "/customers",
    response_model=CustomerRead,
    dependencies=[Depends(require_local_learning_service)],
)
async def post_customer(
    payload: CustomerCreate,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session),
) -> CustomerRead:
    """A customer: usergroup with its private courses and an invite code into the group."""
    owner, org_id = await _local_owner(db_session)
    courses = [await _course_by_public_id(db_session, course_id) for course_id in payload.course_ids]
    for course in courses:
        await _authorize_course(request, db_session, owner, course, AccessAction.UPDATE)
    return await create_customer(request, db_session, owner, org_id, payload.name.strip(), courses)


@router.get(
    "/customers",
    response_model=list[CustomerRead],
    dependencies=[Depends(require_local_learning_service)],
)
async def get_customers(db_session: AsyncSession = Depends(get_db_session)) -> list[CustomerRead]:
    _, org_id = await _local_owner(db_session)
    return await list_customers(db_session, org_id)
