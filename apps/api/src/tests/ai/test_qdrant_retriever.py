from __future__ import annotations

import httpx
import pytest

from src.services.ai.rag.qdrant_retriever import (
    LearningRetrievalUnavailable,
    QdrantRetriever,
)


@pytest.mark.asyncio
async def test_qdrant_retriever_uses_learning_runtime_contract() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/retrieval/query"
        assert request.headers["X-VibeMind-Learning-Retrieval-Key"] == "k" * 32
        assert request.content == (
            b'{"query":"Explain this","course_id":'
            b'"11111111-1111-1111-1111-111111111111","limit":4}'
        )
        return httpx.Response(
            200,
            json={
                "chunks": [
                    {
                        "chunk_id": "chunk-1",
                        "score": 0.9,
                        "course_id": "11111111-1111-1111-1111-111111111111",
                        "source_id": "22222222-2222-2222-2222-222222222222",
                        "source_revision": 2,
                        "content": "Grounded text",
                        "content_hash": "a" * 64,
                        "locator": {"page": 3},
                        "metadata": {"title": "Guide"},
                        "ingestion_spec_version": "1.0",
                    }
                ]
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://learning-api:8090"
    )
    retriever = QdrantRetriever(
        "http://learning-api:8090", "k" * 32, client=client
    )

    chunks = await retriever.retrieve(
        "Explain this",
        course_id="11111111-1111-1111-1111-111111111111",
        limit=4,
    )

    assert len(chunks) == 1
    assert chunks[0].content == "Grounded text"
    assert chunks[0].locator == {"page": 3}
    await client.aclose()


@pytest.mark.asyncio
async def test_qdrant_retriever_fails_closed_on_invalid_citation_payload() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"chunks": [{"content": "untraceable"}]})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://learning-api:8090"
    )
    retriever = QdrantRetriever(
        "http://learning-api:8090", "k" * 32, client=client
    )

    with pytest.raises(LearningRetrievalUnavailable):
        await retriever.retrieve(
            "Explain this",
            course_id="11111111-1111-1111-1111-111111111111",
            limit=4,
        )
    await client.aclose()
