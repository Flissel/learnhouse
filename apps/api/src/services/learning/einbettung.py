"""Embed Learning sequence players (presentation, explainer video) into a factory lesson.

Learning builds the sequences after publication and sends their player links here. The
blocks are appended to the given lesson page; earlier sequence embeds are replaced, so
re-running is idempotent and a regenerated course gets its players back.
"""

from __future__ import annotations

import re

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.db.courses.activities import Activity
from src.db.courses.courses import Course

_PLAYER_URL = re.compile(r"^https?://[A-Za-z0-9.\-:\[\]]+/lernsequenz/[A-Za-z0-9._-]{1,128}\?k=[0-9a-f]{16,128}$")


class SequenceEmbed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    heading: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=10, max_length=600)
    height: int = Field(default=900, ge=300, le=2000)

    @field_validator("url")
    @classmethod
    def player_link_only(cls, value: str) -> str:
        if not _PLAYER_URL.fullmatch(value):
            raise ValueError("only Learning sequence player links can be embedded")
        return value


class SequenceEmbedWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lesson_id: str = Field(min_length=1, max_length=200)
    embeds: list[SequenceEmbed] = Field(min_length=1, max_length=4)


def _is_sequence_block(block: dict) -> bool:
    attrs = block.get("attrs") or {}
    if block.get("type") == "blockEmbed":
        return "/lernsequenz/" in str(attrs.get("embedUrl") or "")
    return block.get("type") == "heading" and attrs.get("lernsequenz") is True


async def embed_sequences(db_session: AsyncSession, course: Course, payload: SequenceEmbedWrite) -> dict:
    lessons = (
        await db_session.execute(select(Activity).where(Activity.course_id == course.id))
    ).scalars().all()
    lesson = next(
        (
            a for a in lessons
            if (a.extra_metadata or {}).get("factory_generated") is True
            and (a.extra_metadata or {}).get("learning_kind") == "lesson"
            and (a.extra_metadata or {}).get("draft_activity_id") == payload.lesson_id
        ),
        None,
    )
    if lesson is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lesson not found")
    content = dict(lesson.content or {})
    blocks = [b for b in content.get("content", []) if isinstance(b, dict) and not _is_sequence_block(b)]
    for embed in payload.embeds:
        blocks.append({
            "type": "heading",
            "attrs": {"level": 2, "lernsequenz": True},
            "content": [{"type": "text", "text": embed.heading}],
        })
        blocks.append({
            "type": "blockEmbed",
            "attrs": {
                "embedUrl": embed.url, "embedType": "url", "embedHeight": embed.height,
                "embedWidth": "100%", "alignment": "left", "embedAspectRatio": None, "embedCode": None,
            },
        })
    content["type"] = content.get("type", "doc")
    content["content"] = blocks
    lesson.content = content
    db_session.add(lesson)
    await db_session.commit()
    return {"lesson_id": payload.lesson_id, "activity_uuid": lesson.activity_uuid, "embeds": len(payload.embeds)}
