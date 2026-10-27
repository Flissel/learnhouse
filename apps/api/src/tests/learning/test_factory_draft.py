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
    # Live (25.10.): the Markdown subtype only loads a URL ("No markdown URL
    # configured") and assignments rendered empty. Both are page documents now,
    # and a task page never carries the expected answer or the rubric.
    by_kind = {activity.extra_metadata["learning_kind"]: activity for activity in activities}
    for activity in activities:
        assert activity.activity_sub_type == "SUBTYPE_DYNAMIC_PAGE"
        assert activity.content["type"] == "doc"
    lesson_text = json.dumps(by_kind["lesson"].content["content"])
    assert "Provider execution stays behind OpenFang." in lesson_text
    # 27.10.: the claims were stored but never shown; the page now ends with them.
    assert "Das Wichtigste in K\\u00fcrze" in lesson_text  # json.dumps escapes the umlaut
    task = by_kind["case"].content
    assert "expected_answer" not in task and "rubric" not in task
    assert "Route through OpenFang." not in json.dumps(task)
    assert task["content"][0]["content"][0]["text"] == "Choose the authorized path."
    # One form of address in the whole course: the note used to say "du".
    assert "bearbeiten Sie" in task["content"][1]["content"][0]["text"]


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


@pytest.mark.asyncio
async def test_sequence_players_are_embedded_idempotently_into_a_lesson(db, monkeypatch) -> None:
    _enable_local_mode(monkeypatch)
    player = "http://127.0.0.1:8090/lernsequenz/praes-x-kurs?k=" + "a" * 40
    async with _mounted_learning_client(db) as client:
        created = await client.post(
            "/api/v1/learning/courses",
            headers={SERVICE_HEADER: SERVICE_KEY},
            json={"title": "Embed target", "description": "", "about": ""},
        )
        course = created.json()["course"]
        draft = _draft(str(uuid4()), course["course_id"])
        await client.put(
            f"/api/v1/learning/courses/{course['course_id']}/factory-draft",
            headers={SERVICE_HEADER: SERVICE_KEY},
            json={"expected_revision": 1, "draft_hash": _draft_hash(draft), "draft": draft},
        )
        url = f"/api/v1/learning/courses/{course['course_id']}/lernsequenz-einbettungen"
        body = {"lesson_id": "lesson-authority", "embeds": [{"heading": "Interaktive Präsentation", "url": player}]}
        first = await client.put(url, headers={SERVICE_HEADER: SERVICE_KEY}, json=body)
        again = await client.put(url, headers={SERVICE_HEADER: SERVICE_KEY}, json=body)
        foreign = await client.put(
            url, headers={SERVICE_HEADER: SERVICE_KEY},
            json={"lesson_id": "lesson-authority", "embeds": [{"heading": "x", "url": "https://evil.example/x"}]},
        )
        missing = await client.put(
            url, headers={SERVICE_HEADER: SERVICE_KEY}, json={**body, "lesson_id": "nope"}
        )
        unauthenticated = await client.put(url, json=body)

    assert first.status_code == again.status_code == 200
    assert foreign.status_code == 422 and missing.status_code == 404
    assert unauthenticated.status_code in (401, 403)
    lesson = next(
        a for a in (await db.execute(select(Activity))).scalars().all()
        if a.extra_metadata["learning_kind"] == "lesson"
    )
    await db.refresh(lesson)
    embeds = [b for b in lesson.content["content"] if b["type"] == "blockEmbed"]
    assert len(embeds) == 1 and embeds[0]["attrs"]["embedUrl"] == player
    assert lesson.content["content"][0]["type"] != "blockEmbed"  # the lesson text stays first
