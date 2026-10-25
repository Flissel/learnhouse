from __future__ import annotations

import os
from functools import lru_cache

import httpx
from pydantic import ValidationError

from src.services.ai.rag.retrieval_protocol import (
    CourseRetriever,
    RetrievalChunk,
    RetrievalEnvelope,
)


RETRIEVAL_URL_ENV = "LEARNING_RETRIEVAL_SERVICE_URL"
RETRIEVAL_KEY_ENV = "LEARNING_RETRIEVAL_SERVICE_KEY"
RETRIEVAL_KEY_HEADER = "X-VibeMind-Learning-Retrieval-Key"
RETRIEVAL_KEY_MIN_LENGTH = 32


class LearningRetrievalUnavailable(RuntimeError):
    pass


class QdrantRetriever(CourseRetriever):
    def __init__(
        self,
        base_url: str,
        service_key: str,
        *,
        timeout_seconds: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("learning retrieval URL must use HTTP or HTTPS")
        if len(service_key) < RETRIEVAL_KEY_MIN_LENGTH:
            raise ValueError("learning retrieval key is not configured securely")
        self._service_key = service_key
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout_seconds
        )

    async def retrieve(
        self, query: str, *, course_id: str, limit: int
    ) -> tuple[RetrievalChunk, ...]:
        if not query.strip() or not course_id or limit < 1 or limit > 20:
            raise ValueError("learning retrieval request is invalid")
        try:
            response = await self._client.post(
                "/api/v1/retrieval/query",
                headers={RETRIEVAL_KEY_HEADER: self._service_key},
                json={"query": query, "course_id": course_id, "limit": limit},
            )
            response.raise_for_status()
            envelope = RetrievalEnvelope.model_validate(response.json())
        except (httpx.HTTPError, ValueError, ValidationError) as error:
            raise LearningRetrievalUnavailable(
                "grounded learning retrieval is unavailable"
            ) from error
        if any(
            chunk.course_id != course_id or not chunk.locator
            for chunk in envelope.chunks
        ):
            raise LearningRetrievalUnavailable(
                "grounded learning retrieval returned invalid citations"
            )
        return tuple(envelope.chunks)


@lru_cache(maxsize=1)
def get_qdrant_retriever() -> CourseRetriever:
    return QdrantRetriever(
        os.environ.get(RETRIEVAL_URL_ENV, "").strip(),
        os.environ.get(RETRIEVAL_KEY_ENV, ""),
    )
