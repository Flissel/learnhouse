from __future__ import annotations

import hashlib
import json
from uuid import uuid4

import pytest
from sqlmodel import select

from src.db.courses.activities import Activity
from src.db.courses.chapters import Chapter
from src.tests.learning.test_bootstrap import (
    SERVICE_HEADER,
    SERVICE_KEY,
    _enable_local_mode,
    _mounted_learning_client,
)


def _draft(job_id: str, course_id: str) -> dict:
    source_id = str(uuid4())
    chunk_id = str(uuid4())
    citation_id = str(uuid4())
    return {
        "schema_version": "course-draft-v1",
        "job_id": job_id,
        "attempt_number": 1,
        "title": "Grounded AI Operations",
        "outcomes": ["Operate an authorized workflow"],
        "source_provenance": [
            {"source_id": source_id, "revision": 1, "content_hash": "a" * 64}
        ],
        "citations": [
            {
                "citation_id": citation_id,
                "source_id": source_id,
                "source_revision": 1,
                "chunk_id": chunk_id,
                "content_hash": "b" * 64,
                "locator": {"page": 4},
            }
        ],
        "concepts": [{"concept_id": "authority", "title": "Authority"}],
        "chapters": [
            {
                "chapter_id": "foundations",
                "title": "Foundations",
                "lesson_ids": ["lesson-authority"],
                "activity_ids": ["task-authority"],
            }
        ],
        "lessons": [
            {
                "lesson_id": "lesson-authority",
                "chapter_id": "foundations",
                "title": "Authority boundaries",
                "body": "Provider execution stays behind OpenFang.",
                "concept_ids": ["authority"],
                "claims": [
                    {
                        "claim_id": "claim-authority",
                        "text": "Provider execution stays behind OpenFang.",
                        "citation_ids": [citation_id],
                    }
                ],
            }
        ],
        "activities": [
            {
                "activity_id": "task-authority",
                "chapter_id": "foundations",
                "type": "case",
                "concept_ids": ["authority"],
                "prompt": "Choose the authorized path.",
                "expected_answer": "Route through OpenFang.",
                "citation_ids": [citation_id],
                "rubric": [
                    {
                        "criterion_id": "routing",
                        "description": "Uses the authority chain",
                        "points": 2,
                    }
                ],
            }
        ],
    }


def _draft_hash(draft: dict) -> str:
    encoded = json.dumps(
        draft, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


@pytest.mark.asyncio
async def test_factory_draft_maps_real_course_structure_and_has_readback(
    db, monkeypatch
) -> None:
    _enable_local_mode(monkeypatch)
    job_id = str(uuid4())
    async with _mounted_learning_client(db) as client:
        created = await client.post(
            "/api/v1/learning/courses",
            headers={SERVICE_HEADER: SERVICE_KEY},
            json={"title": "Draft target", "description": "", "about": ""},
        )
        course = created.json()["course"]
        draft = _draft(job_id, course["course_id"])
        draft_hash = _draft_hash(draft)
        payload = {
            "expected_revision": 1,
            "draft_hash": draft_hash,
            "draft": draft,
        }

        mapped = await client.put(
            f"/api/v1/learning/courses/{course['course_id']}/factory-draft",
            headers={SERVICE_HEADER: SERVICE_KEY},
            json=payload,
        )
        replay = await client.put(
            f"/api/v1/learning/courses/{course['course_id']}/factory-draft",
            headers={SERVICE_HEADER: SERVICE_KEY},
            json=payload,
        )
        readback = await client.get(
            f"/api/v1/learning/courses/{course['course_id']}/factory-draft",
            headers={SERVICE_HEADER: SERVICE_KEY},
        )

    assert mapped.status_code == replay.status_code == readback.status_code == 200
    assert mapped.json() == replay.json() == readback.json()
    assert mapped.json()["draft"] == {
        "factory_job_id": job_id,
        "attempt_number": 1,
        "draft_hash": draft_hash,
        "revision": 2,
        "chapter_count": 1,
        "activity_count": 2,
    }
    chapters = (await db.execute(select(Chapter))).scalars().all()
    activities = (await db.execute(select(Activity))).scalars().all()
    assert len(chapters) == 1
    assert len(activities) == 2
    assert {activity.extra_metadata["learning_kind"] for activity in activities} == {
        "lesson",
        "case",
    }


@pytest.mark.asyncio
async def test_factory_draft_rejects_stale_replacement_and_published_course(
    db, monkeypatch
) -> None:
    _enable_local_mode(monkeypatch)
    async with _mounted_learning_client(db) as client:
        created = await client.post(
            "/api/v1/learning/courses",
            headers={SERVICE_HEADER: SERVICE_KEY},
            json={"title": "Protected target", "description": "", "about": ""},
        )
        course = created.json()["course"]
        first_job = str(uuid4())
        first_draft = _draft(first_job, course["course_id"])
        first = await client.put(
            f"/api/v1/learning/courses/{course['course_id']}/factory-draft",
            headers={SERVICE_HEADER: SERVICE_KEY},
            json={
                "expected_revision": 1,
                "draft_hash": _draft_hash(first_draft),
                "draft": first_draft,
            },
        )
        stale_draft = _draft(str(uuid4()), course["course_id"])
        stale = await client.put(
            f"/api/v1/learning/courses/{course['course_id']}/factory-draft",
            headers={SERVICE_HEADER: SERVICE_KEY},
            json={
                "expected_revision": 1,
                "draft_hash": _draft_hash(stale_draft),
                "draft": stale_draft,
            },
        )
        reviewed = await client.post(
            f"/api/v1/learning/courses/{course['course_id']}/review",
            headers={SERVICE_HEADER: SERVICE_KEY},
            json={"review": "approved", "expected_revision": 2},
        )
        published = await client.post(
            f"/api/v1/learning/courses/{course['course_id']}/publish",
            headers={SERVICE_HEADER: SERVICE_KEY},
            json={"expected_revision": 3},
        )
        published_draft = _draft(str(uuid4()), course["course_id"])
        after_publish = await client.put(
            f"/api/v1/learning/courses/{course['course_id']}/factory-draft",
            headers={SERVICE_HEADER: SERVICE_KEY},
            json={
                "expected_revision": 4,
                "draft_hash": _draft_hash(published_draft),
                "draft": published_draft,
            },
        )

    assert first.status_code == reviewed.status_code == published.status_code == 200
    assert stale.status_code == 409
    assert after_publish.status_code == 409
    assert after_publish.json()["detail"] == "published_course_is_immutable"
