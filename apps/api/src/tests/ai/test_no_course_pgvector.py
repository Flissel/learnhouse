from __future__ import annotations

from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

import pytest

from src.services.ai.rag.embedding_service import embed_course_content
from src.services.ai.rag.query_service import query_course_rag
from src.services.ai.rag.retrieval_protocol import RetrievalChunk
from src.services.courses.activities.activities import _trigger_course_embedding


class _ForbiddenSession:
    def __getattr__(self, name: str):
        raise AssertionError(f"pgvector database access is forbidden: {name}")


class _CourseResult:
    def scalar_one_or_none(self) -> str:
        return "course_11111111-1111-1111-1111-111111111111"


class _CourseOnlySession:
    async def execute(self, statement):
        assert "course_embedding" not in str(statement).lower()
        return _CourseResult()


@pytest.mark.asyncio
async def test_learning_mode_never_writes_course_embeddings(monkeypatch) -> None:
    monkeypatch.setenv("LEARNHOUSE_LOCAL_LEARNING_MODE", "true")

    indexed = await embed_course_content(1, 2, _ForbiddenSession())

    assert indexed == 0


@pytest.mark.asyncio
async def test_learning_activity_update_never_starts_pgvector_indexing(monkeypatch) -> None:
    monkeypatch.setenv("LEARNHOUSE_LOCAL_LEARNING_MODE", "true")

    with patch(
        "src.core.events.database.get_db_session", new_callable=AsyncMock
    ) as get_db:
        await _trigger_course_embedding(1, 2)

    get_db.assert_not_called()


@pytest.mark.asyncio
async def test_learning_rag_reads_only_through_qdrant_adapter(monkeypatch) -> None:
    monkeypatch.setenv("LEARNHOUSE_LOCAL_LEARNING_MODE", "true")
    retriever = SimpleNamespace(
        retrieve=AsyncMock(
            return_value=(
                RetrievalChunk(
                    chunk_id="chunk-1",
                    score=0.95,
                    course_id="11111111-1111-1111-1111-111111111111",
                    source_id="22222222-2222-2222-2222-222222222222",
                    source_revision=2,
                    content="Grounded text",
                    content_hash="a" * 64,
                    locator={"page": 7},
                    metadata={"title": "Guide"},
                    ingestion_spec_version="1.0",
                ),
            )
        )
    )

    with patch(
        "src.services.ai.rag.qdrant_retriever.get_qdrant_retriever",
        return_value=retriever,
    ), patch(
        "src.services.ai.rag.query_service.embed_single_text",
        new_callable=AsyncMock,
    ) as legacy_embed:
        result = await query_course_rag(
            "Explain this", 9, _CourseOnlySession(), course_id=5, top_k=4
        )

    legacy_embed.assert_not_called()
    retriever.retrieve.assert_awaited_once_with(
        "Explain this",
        course_id="11111111-1111-1111-1111-111111111111",
        limit=4,
    )
    assert result["context"] == "[Source 1]\nGrounded text"
    assert result["sources"][0]["locator"] == {"page": 7}
