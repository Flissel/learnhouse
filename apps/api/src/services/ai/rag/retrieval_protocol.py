from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class RetrievalChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk_id: str = Field(min_length=1, max_length=256)
    score: float
    course_id: str = Field(min_length=36, max_length=36)
    source_id: str = Field(min_length=1, max_length=256)
    source_revision: int = Field(ge=1)
    content: str = Field(min_length=1, max_length=100_000)
    content_hash: str = Field(min_length=64, max_length=64)
    locator: dict[str, object]
    metadata: dict[str, object]
    ingestion_spec_version: str = Field(min_length=1, max_length=32)


class RetrievalEnvelope(BaseModel):
    chunks: list[RetrievalChunk] = Field(max_length=20)


class CourseRetriever(Protocol):
    async def retrieve(
        self, query: str, *, course_id: str, limit: int
    ) -> tuple[RetrievalChunk, ...]: ...
