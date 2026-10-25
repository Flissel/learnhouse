import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

import src.core.learning_mode as learning_mode
import src.routers.learning as learning_router_module
import src.routers.learning.bootstrap as bootstrap_module
import src.routers.learning.service as learning_service_module
from src.core.events.database import get_db_session
from src.core.learning_mode import (
    LOCAL_LEARNING_LOCALE,
    LOCAL_LEARNING_ORG_NAME,
    LOCAL_LEARNING_ORG_SLUG,
    LOCAL_LEARNING_OWNER_EMAIL,
    LOCAL_LEARNING_OWNER_USERNAME,
    provision_local_learning_mode,
)
from src.db.organization_config import OrganizationConfig
from src.db.organizations import Organization
from src.db.roles import Role
from src.db.user_organizations import UserOrganization
from src.db.users import User
from src.db.courses.chapters import Chapter
from src.db.courses.courses import Course
from src.security.rbac.constants import ADMIN_ROLE_ID
from src.security.security import security_verify_password


BOOTSTRAP_HEADER = "X-LearnHouse-Local-Bootstrap-Key"
BOOTSTRAP_KEY = "test-only-local-bootstrap-key-32-characters"
OWNER_PASSWORD = "test-only-local-owner-password"
SERVICE_HEADER = "X-LearnHouse-Learning-Service-Key"
SERVICE_KEY = "test-only-learning-service-key-32chars"


def _enable_local_mode(monkeypatch) -> None:
    monkeypatch.setenv("LEARNHOUSE_LOCAL_LEARNING_MODE", "true")
    monkeypatch.setenv("LEARNHOUSE_LOCAL_BOOTSTRAP_KEY", BOOTSTRAP_KEY)
    monkeypatch.setenv("LEARNHOUSE_INITIAL_ADMIN_PASSWORD", OWNER_PASSWORD)
    monkeypatch.setenv("LEARNHOUSE_LEARNING_SERVICE_KEY", SERVICE_KEY)
    monkeypatch.delenv("LEARNHOUSE_ALLOW_REMOTE_LEARNING_BOOTSTRAP", raising=False)


@asynccontextmanager
async def _bootstrap_client(db: AsyncSession):
    app = FastAPI()
    app.include_router(
        bootstrap_module.router,
        prefix="/api/v1/learning",
    )

    async def override_db_session():
        yield db

    app.dependency_overrides[get_db_session] = override_db_session
    transport = ASGITransport(
        app=app,
        client=("172.18.0.4", 43123),
        raise_app_exceptions=False,
    )
    async with AsyncClient(transport=transport, base_url="http://learnhouse-api") as client:
        yield client


@asynccontextmanager
async def _mounted_learning_client(db: AsyncSession):
    app = FastAPI()
    app.include_router(bootstrap_module.router, prefix="/api/v1/learning")
    app.include_router(learning_service_module.router, prefix="/api/v1/learning")

    async def override_db_session():
        yield db

    app.dependency_overrides[get_db_session] = override_db_session
    transport = ASGITransport(
        app=app,
        client=("172.18.0.4", 43123),
        raise_app_exceptions=True,
    )
    async with AsyncClient(transport=transport, base_url="http://learnhouse-api") as client:
        yield client


@asynccontextmanager
async def _concurrent_learning_client(engine):
    app = FastAPI()
    app.include_router(learning_service_module.router, prefix="/api/v1/learning")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_db_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session
    transport = ASGITransport(app=app, client=("172.18.0.4", 43123))
    async with AsyncClient(transport=transport, base_url="http://learnhouse-api") as client:
        yield client


def test_bootstrap_router_is_mounted_only_for_explicit_local_mode(monkeypatch):
    mount = getattr(
        learning_router_module,
        "mount_local_learning_bootstrap",
        None,
    )
    assert callable(mount)

    monkeypatch.delenv("LEARNHOUSE_LOCAL_LEARNING_MODE", raising=False)
    disabled_router = APIRouter()
    assert mount(disabled_router) is False
    assert [route.path for route in disabled_router.routes] == []

    monkeypatch.setenv("LEARNHOUSE_LOCAL_LEARNING_MODE", "false")
    false_router = APIRouter()
    assert mount(false_router) is False
    assert [route.path for route in false_router.routes] == []

    monkeypatch.setenv("LEARNHOUSE_LOCAL_LEARNING_MODE", "true")
    enabled_router = APIRouter()
    assert mount(enabled_router) is True
    assert len(enabled_router.routes) == 2


@pytest.mark.asyncio
async def test_revisioned_learning_service_api_is_authenticated_and_revision_safe(
    db, monkeypatch
):
    """The parent bridge may call only the local-mode service, never public routes."""
    _enable_local_mode(monkeypatch)

    async with _mounted_learning_client(db) as client:
        empty = await client.get(
            "/api/v1/learning/courses?page=1&limit=20",
            headers={SERVICE_HEADER: SERVICE_KEY},
        )
        assert empty.status_code == 200
        assert empty.json() == {
            "aggregate": {"aggregate_id": "default", "revision": 0},
            "courses": [],
        }

        missing = await client.get("/api/v1/learning/courses")
        wrong = await client.get(
            "/api/v1/learning/courses",
            headers={
                SERVICE_HEADER: "wrong-learning-service-key-that-is-long-enough",
                "X-User-Id": "999999",
                "X-Forwarded-User": "untrusted",
            },
        )
        assert missing.status_code == 403
        assert wrong.status_code == 403

        created = await client.post(
            "/api/v1/learning/courses",
            headers={SERVICE_HEADER: SERVICE_KEY, "X-User-Id": "999999"},
            json={
                "title": "Revisioned learning",
                "description": "A controlled course.",
                "about": "Created through LearnHouse services.",
            },
        )
        assert created.status_code == 200
        course = created.json()["course"]
        assert course["course_id"]
        assert course["revision"] == 1
        assert course["review_status"] == "pending"

        empty_or_first_page = await client.get(
            "/api/v1/learning/courses?page=1&limit=1",
            headers={SERVICE_HEADER: SERVICE_KEY},
        )
        assert empty_or_first_page.status_code == 200
        collection = empty_or_first_page.json()
        assert collection["aggregate"]["aggregate_id"] == "default"
        assert collection["aggregate"]["revision"] >= 1
        assert len(collection["courses"]) == 1

        source = await client.post(
            f"/api/v1/learning/courses/{course['course_id']}/sources",
            headers={SERVICE_HEADER: SERVICE_KEY},
            json={
                "title": "Source",
                "source_url": "https://example.invalid/source",
                "expected_revision": 1,
            },
        )
        assert source.status_code == 200
        assert source.json()["source"]["revision"] == 2

        reviewed = await client.post(
            f"/api/v1/learning/courses/{course['course_id']}/review",
            headers={SERVICE_HEADER: SERVICE_KEY},
            json={"review": "approved", "expected_revision": 2},
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["course"]["revision"] == 3
        assert reviewed.json()["course"]["review_status"] == "approved"

        stale_publish = await client.post(
            f"/api/v1/learning/courses/{course['course_id']}/publish",
            headers={SERVICE_HEADER: SERVICE_KEY},
            json={"expected_revision": 2},
        )
        assert stale_publish.status_code == 409
        assert stale_publish.json()["detail"] == "revision_conflict"

        published = await client.post(
            f"/api/v1/learning/courses/{course['course_id']}/publish",
            headers={SERVICE_HEADER: SERVICE_KEY},
            json={"expected_revision": 3},
        )
        assert published.status_code == 200
        assert published.json()["course"]["revision"] == 4
        assert published.json()["course"]["published"] is True

        stored_course = (await db.execute(select(Course))).scalars().one()
        chapter = Chapter(
            name="A chapter",
            description="",
            thumbnail_image="",
            org_id=stored_course.org_id,
            course_id=stored_course.id,
            chapter_uuid="chapter_00000000-0000-0000-0000-000000000102",
            creation_date="now",
            update_date="now",
        )
        db.add(chapter)
        await db.commit()

        opened = await client.get(
            f"/api/v1/learning/courses/{course['course_id']}",
            headers={SERVICE_HEADER: SERVICE_KEY},
        )
        chapter_opened = await client.get(
            "/api/v1/learning/chapters/00000000-0000-0000-0000-000000000102",
            headers={SERVICE_HEADER: SERVICE_KEY},
        )
        progress = await client.get(
            f"/api/v1/learning/courses/{course['course_id']}/progress",
            headers={SERVICE_HEADER: SERVICE_KEY},
        )
        source_readback = await client.get(
            f"/api/v1/learning/sources/{source.json()['source']['source_id']}",
            headers={SERVICE_HEADER: SERVICE_KEY},
        )
        assert opened.status_code == chapter_opened.status_code == progress.status_code == 200
        assert source_readback.status_code == 200
        assert chapter_opened.json()["chapter"]["chapter_id"] == (
            "00000000-0000-0000-0000-000000000102"
        )
        assert progress.json()["progress"]["revision"] == 4

        second = await client.post(
            "/api/v1/learning/courses",
            headers={SERVICE_HEADER: SERVICE_KEY},
            json={
                "title": "Second course",
                "description": "Second.",
                "about": "Second.",
            },
        )
        assert second.status_code == 200
        first_page = await client.get(
            "/api/v1/learning/courses?page=1&limit=1",
            headers={SERVICE_HEADER: SERVICE_KEY},
        )
        second_page = await client.get(
            "/api/v1/learning/courses?page=2&limit=1",
            headers={SERVICE_HEADER: SERVICE_KEY},
        )
        assert first_page.status_code == second_page.status_code == 200
        assert first_page.json()["aggregate"] == second_page.json()["aggregate"]
        assert first_page.json()["courses"][0]["course_id"] != second_page.json()["courses"][0]["course_id"]


@pytest.mark.asyncio
async def test_learning_service_compare_and_set_allows_one_current_revision_writer(
    engine, monkeypatch
):
    _enable_local_mode(monkeypatch)
    monkeypatch.setattr(learning_mode, "_SQLITE_PROVISIONING_LOCK", asyncio.Lock())

    async with _concurrent_learning_client(engine) as client:
        created = await client.post(
            "/api/v1/learning/courses",
            headers={SERVICE_HEADER: SERVICE_KEY},
            json={"title": "CAS", "description": "", "about": ""},
        )
        assert created.status_code == 200
        course_id = created.json()["course"]["course_id"]

        first, second = await asyncio.gather(
            client.post(
                f"/api/v1/learning/courses/{course_id}/review",
                headers={SERVICE_HEADER: SERVICE_KEY},
                json={"review": "approved", "expected_revision": 1},
            ),
            client.post(
                f"/api/v1/learning/courses/{course_id}/review",
                headers={SERVICE_HEADER: SERVICE_KEY},
                json={"review": "approved", "expected_revision": 1},
            ),
        )

    assert sorted((first.status_code, second.status_code)) == [200, 409]


@pytest.mark.asyncio
async def test_disabled_mode_fails_closed_even_if_router_is_imported(db, monkeypatch):
    monkeypatch.delenv("LEARNHOUSE_LOCAL_LEARNING_MODE", raising=False)
    monkeypatch.setenv("LEARNHOUSE_LOCAL_BOOTSTRAP_KEY", BOOTSTRAP_KEY)

    async with _bootstrap_client(db) as client:
        response = await client.post(
            "/api/v1/learning/bootstrap",
            headers={BOOTSTRAP_HEADER: BOOTSTRAP_KEY},
        )

    assert response.status_code == 404
    assert (await db.execute(select(Organization))).scalars().all() == []
    assert (await db.execute(select(User))).scalars().all() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {BOOTSTRAP_HEADER: "wrong-bootstrap-key-that-is-still-long-enough"},
        {
            BOOTSTRAP_HEADER: "wrong-bootstrap-key-that-is-still-long-enough",
            "Origin": "http://127.0.0.1:3000",
            "X-Forwarded-For": "127.0.0.1",
        },
    ],
    ids=["missing", "wrong", "spoofed-loopback"],
)
async def test_missing_or_wrong_bootstrap_key_is_rejected(
    db, monkeypatch, headers
):
    _enable_local_mode(monkeypatch)

    async with _bootstrap_client(db) as client:
        response = await client.post(
            "/api/v1/learning/bootstrap",
            headers=headers,
        )

    assert response.status_code == 403
    assert BOOTSTRAP_KEY not in response.text
    supplied_key = headers.get(BOOTSTRAP_HEADER)
    if supplied_key:
        assert supplied_key not in response.text
    assert (await db.execute(select(Organization))).scalars().all() == []
    assert (await db.execute(select(User))).scalars().all() == []


@pytest.mark.asyncio
async def test_short_configured_bootstrap_key_fails_closed(db, monkeypatch):
    _enable_local_mode(monkeypatch)
    monkeypatch.setenv("LEARNHOUSE_LOCAL_BOOTSTRAP_KEY", "too-short")

    async with _bootstrap_client(db) as client:
        response = await client.post(
            "/api/v1/learning/bootstrap",
            headers={BOOTSTRAP_HEADER: "too-short"},
        )

    assert response.status_code == 503
    assert "too-short" not in response.text
    assert (await db.execute(select(Organization))).scalars().all() == []


@pytest.mark.asyncio
async def test_bootstrap_provisions_without_authenticating_or_setting_cookies(
    db, monkeypatch
):
    _enable_local_mode(monkeypatch)
    issue_session = AsyncMock(side_effect=AssertionError("must not issue a session"))
    set_cookies = Mock(side_effect=AssertionError("must not set auth cookies"))
    monkeypatch.setattr(
        bootstrap_module,
        "issue_session_or_challenge",
        issue_session,
        raising=False,
    )
    monkeypatch.setattr(
        bootstrap_module,
        "set_auth_cookies",
        set_cookies,
        raising=False,
    )

    async with _bootstrap_client(db) as client:
        first = await client.post(
            "/api/v1/learning/bootstrap",
            headers={
                BOOTSTRAP_HEADER: BOOTSTRAP_KEY,
                "Origin": "https://untrusted.example",
                "X-Forwarded-For": "127.0.0.1",
            },
        )

        monkeypatch.delenv("LEARNHOUSE_INITIAL_ADMIN_PASSWORD")
        second = await client.post(
            "/api/v1/learning/bootstrap",
            headers={BOOTSTRAP_HEADER: BOOTSTRAP_KEY},
        )

        monkeypatch.setenv(
            "LEARNHOUSE_INITIAL_ADMIN_PASSWORD",
            "changed-password-that-must-not-authenticate",
        )
        third = await client.post(
            "/api/v1/learning/bootstrap",
            headers={BOOTSTRAP_HEADER: BOOTSTRAP_KEY},
        )

    assert first.status_code == 200
    assert first.json() == {
        "status": "created",
        "owner": {"username": LOCAL_LEARNING_OWNER_USERNAME},
        "organization": {
            "name": LOCAL_LEARNING_ORG_NAME,
            "slug": LOCAL_LEARNING_ORG_SLUG,
        },
        "locale": LOCAL_LEARNING_LOCALE,
        "permissions": ["admin"],
    }
    assert second.status_code == 200
    assert second.json()["status"] == "ready"
    assert third.status_code == 200
    assert third.json()["status"] == "ready"
    assert "authenticated" not in first.json()
    assert first.headers.get_list("set-cookie") == []
    assert second.headers.get_list("set-cookie") == []
    assert third.headers.get_list("set-cookie") == []
    issue_session.assert_not_awaited()
    set_cookies.assert_not_called()

    serialized = json.dumps([first.json(), second.json(), third.json()]).lower()
    assert OWNER_PASSWORD not in serialized
    assert BOOTSTRAP_KEY not in serialized
    assert "password" not in serialized
    assert "access_token" not in serialized
    assert "refresh_token" not in serialized

    users = (await db.execute(select(User))).scalars().all()
    organizations = (await db.execute(select(Organization))).scalars().all()
    memberships = (await db.execute(select(UserOrganization))).scalars().all()
    roles = (await db.execute(select(Role).order_by(Role.id))).scalars().all()
    org_configs = (await db.execute(select(OrganizationConfig))).scalars().all()

    assert len(users) == 1
    assert len(organizations) == 1
    assert len(memberships) == 1
    assert len(org_configs) == 1
    assert memberships[0].role_id == ADMIN_ROLE_ID
    assert [role.id for role in roles] == [1, 2, 3, 4]
    assert roles[0].rights["dashboard"]["action_access"] is True
    assert (
        org_configs[0].config["customization"]["general"]["default_language"]
        == LOCAL_LEARNING_LOCALE
    )
    assert users[0].password != OWNER_PASSWORD
    assert security_verify_password(OWNER_PASSWORD, users[0].password)


@pytest.mark.asyncio
async def test_concurrent_bootstrap_serializes_supported_service_creates(
    engine, monkeypatch
):
    _enable_local_mode(monkeypatch)
    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def provision_once():
        async with factory() as session:
            return await provision_local_learning_mode(session)

    first, second = await asyncio.gather(provision_once(), provision_once())

    assert sorted([first.created, second.created]) == [False, True]
    assert {first.user.id, second.user.id} == {first.user.id}
    assert {first.organization.id, second.organization.id} == {
        first.organization.id
    }
    assert first.user.username == second.user.username == LOCAL_LEARNING_OWNER_USERNAME
    assert str(first.user.email) == str(second.user.email) == LOCAL_LEARNING_OWNER_EMAIL
    assert first.organization.slug == second.organization.slug == LOCAL_LEARNING_ORG_SLUG
    assert first.permissions == second.permissions == ("admin",)

    async with factory() as verification_db:
        assert len((await verification_db.execute(select(User))).scalars().all()) == 1
        assert len(
            (await verification_db.execute(select(Organization))).scalars().all()
        ) == 1
        assert len(
            (await verification_db.execute(select(OrganizationConfig))).scalars().all()
        ) == 1
        memberships = (
            await verification_db.execute(select(UserOrganization))
        ).scalars().all()
        assert len(memberships) == 1
        assert memberships[0].role_id == ADMIN_ROLE_ID


@pytest.mark.asyncio
async def test_bootstrap_lock_is_released_when_a_supported_service_fails(
    engine, monkeypatch
):
    _enable_local_mode(monkeypatch)
    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    original_create = learning_mode.install_create_organization
    call_count = 0

    async def fail_once(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("injected create failure")
        return await original_create(*args, **kwargs)

    monkeypatch.setattr(
        learning_mode,
        "install_create_organization",
        fail_once,
    )

    async with factory() as first_db:
        with pytest.raises(RuntimeError, match="injected create failure"):
            await provision_local_learning_mode(first_db)

    async with factory() as second_db:
        recovered = await asyncio.wait_for(
            provision_local_learning_mode(second_db),
            timeout=2,
        )

    assert recovered.created is True
    assert recovered.organization.slug == LOCAL_LEARNING_ORG_SLUG


@pytest.mark.asyncio
async def test_owner_identity_conflicts_fail_closed(db, monkeypatch):
    _enable_local_mode(monkeypatch)
    await learning_mode.install_default_elements(db)
    organization = await learning_mode.install_create_organization(
        learning_mode.OrganizationCreate(
            name=LOCAL_LEARNING_ORG_NAME,
            description=LOCAL_LEARNING_ORG_NAME,
            slug=LOCAL_LEARNING_ORG_SLUG,
            email="",
            logo_image="",
            thumbnail_image="",
            about="",
            label="",
        ),
        db,
    )
    assert organization.id is not None
    await learning_mode.install_create_organization_user(
        learning_mode.UserCreate(
            username=LOCAL_LEARNING_OWNER_USERNAME,
            email="different-owner@school.dev",
            password=OWNER_PASSWORD,
        ),
        LOCAL_LEARNING_ORG_SLUG,
        db,
        is_superadmin=True,
    )

    with pytest.raises(HTTPException) as conflict:
        await provision_local_learning_mode(db)

    assert conflict.value.status_code == 409
