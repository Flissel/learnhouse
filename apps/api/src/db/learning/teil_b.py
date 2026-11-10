"""Learning Teil B: fixed learner id per account, groups with a course, invitation links."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    text,
    true,
)
from sqlmodel import Field, SQLModel

# The referenced tables must sit in the same metadata wherever these models are loaded.
from src.db import organizations as _organizations  # noqa: F401
from src.db import usergroups as _usergroups  # noqa: F401
from src.db import users as _users  # noqa: F401
from src.db.courses import courses as _courses  # noqa: F401

LINK_ARTEN = ("admin", "kursleiter", "gruppe")


def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


class LearningPerson(SQLModel, table=True):
    """One LearnHouse account, one Learning ``actor_id``; written once, then fixed."""

    __tablename__ = "learning_person"

    user_id: int = Field(
        sa_column=Column(
            Integer, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True, autoincrement=False
        )
    )
    actor_id: str = Field(sa_column=Column(String(128), nullable=False, unique=True))
    erstellt_am: datetime = Field(
        default_factory=_jetzt,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )


class LearningGruppe(SQLModel, table=True):
    """A LearnHouse user group that learns one course together; joinable while open."""

    __tablename__ = "learning_gruppe"

    id: int | None = Field(default=None, primary_key=True)
    usergroup_id: int = Field(
        sa_column=Column(
            Integer, ForeignKey("usergroup.id", ondelete="CASCADE"), nullable=False, unique=True
        )
    )
    course_id: int = Field(
        sa_column=Column(
            Integer, ForeignKey("course.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    offen: bool = Field(
        default=True, sa_column=Column(Boolean, nullable=False, server_default=true())
    )
    erstellt_von: int = Field(
        sa_column=Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    )
    erstellt_am: datetime = Field(
        default_factory=_jetzt,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )


class LearningLink(SQLModel, table=True):
    """An invitation link; only ``sha256(token)`` is stored, never the token."""

    __tablename__ = "learning_link"
    __table_args__ = (
        CheckConstraint(
            "art IN ('admin', 'kursleiter', 'gruppe')", name="ck_learning_link_art"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    token_sha256: str = Field(sa_column=Column(CHAR(64), nullable=False, unique=True))
    art: str = Field(sa_column=Column(String(16), nullable=False))
    org_id: int = Field(
        sa_column=Column(
            Integer, ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True
        )
    )
    gruppe_id: int | None = Field(
        default=None,
        sa_column=Column(
            Integer, ForeignKey("learning_gruppe.id", ondelete="CASCADE"), nullable=True
        ),
    )
    erstellt_von: int = Field(
        sa_column=Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    )
    erstellt_am: datetime = Field(
        default_factory=_jetzt,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )
    laeuft_ab: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    zurueckgezogen_am: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class LearningEntfernung(SQLModel, table=True):
    """A person was removed from a provider; links created before ``entfernt_am`` no longer
    admit her there. One note per person and provider, moved forward on a new removal."""

    __tablename__ = "learning_entfernung"

    user_id: int = Field(
        sa_column=Column(
            Integer, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True, autoincrement=False
        )
    )
    org_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("organization.id", ondelete="CASCADE"),
            primary_key=True,
            autoincrement=False,
        )
    )
    entfernt_am: datetime = Field(
        default_factory=_jetzt,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    )
