from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class LearningCourseState(SQLModel, table=True):
    """Revisioned local-learning metadata owned by the LearnHouse database."""

    __tablename__ = "learning_course_state"

    id: int | None = Field(default=None, primary_key=True)
    course_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("course.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        )
    )
    revision: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    review_status: str = Field(
        default="pending", sa_column=Column(String(32), nullable=False)
    )
    source_metadata: dict = Field(default_factory=dict, sa_column=Column(JSONB))


class LearningCourseCollectionState(SQLModel, table=True):
    """Stable collection aggregate used by paged course-list readback."""

    __tablename__ = "learning_course_collection_state"

    id: int | None = Field(default=None, primary_key=True)
    org_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("organization.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        )
    )
    revision: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    fingerprint: str = Field(default="", sa_column=Column(String(4096), nullable=False))


class LearningCourseSource(SQLModel, table=True):
    """Course-source metadata links normal LearnHouse media to a course aggregate."""

    __tablename__ = "learning_course_source"
    __table_args__ = (UniqueConstraint("source_uuid"),)

    id: int | None = Field(default=None, primary_key=True)
    course_id: int = Field(
        sa_column=Column(
            Integer, ForeignKey("course.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    media_id: int = Field(
        sa_column=Column(
            Integer, ForeignKey("media.id", ondelete="CASCADE"), nullable=False, unique=True
        )
    )
    source_uuid: str = Field(
        sa_column=Column(String(36), nullable=False, unique=True, index=True)
    )
    revision: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    title: str = Field(default="", sa_column=Column(String(512), nullable=False))
    source_url: str = Field(default="", sa_column=Column(String(2048), nullable=False))
