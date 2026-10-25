import asyncio
import os
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass
from typing import AsyncIterator, cast

from fastapi import HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.db.organization_config import OrganizationConfig
from src.db.organizations import Organization, OrganizationCreate
from src.db.user_organizations import UserOrganization
from src.db.users import User, UserCreate, UserRead
from src.security.rbac.constants import ADMIN_ROLE_ID
from src.services.orgs.orgs import (
    get_org_default_language,
    update_org_with_config_no_auth,
)
from src.services.setup.setup import (
    install_create_organization,
    install_create_organization_user,
    install_default_elements,
)


LOCAL_LEARNING_OWNER_USERNAME = "admin"
LOCAL_LEARNING_OWNER_EMAIL = "admin@school.dev"
LOCAL_LEARNING_ORG_NAME = "Default Organization"
LOCAL_LEARNING_ORG_SLUG = "default"
LOCAL_LEARNING_LOCALE = "en"
LOCAL_LEARNING_PERMISSIONS = ("admin",)

LOCAL_LEARNING_MODE_ENV = "LEARNHOUSE_LOCAL_LEARNING_MODE"
LOCAL_LEARNING_BOOTSTRAP_KEY_ENV = "LEARNHOUSE_LOCAL_BOOTSTRAP_KEY"
LOCAL_LEARNING_BOOTSTRAP_HEADER = "X-LearnHouse-Local-Bootstrap-Key"
LOCAL_LEARNING_BOOTSTRAP_KEY_MIN_LENGTH = 32

_OWNER_PASSWORD_ENV = "LEARNHOUSE_INITIAL_ADMIN_PASSWORD"
_POSTGRES_PROVISIONING_LOCK_ID = 5497573966810632787
_SQLITE_PROVISIONING_LOCK = asyncio.Lock()


@dataclass(frozen=True)
class LocalLearningProvisioning:
    created: bool
    user: UserRead
    organization: Organization
    locale: str = LOCAL_LEARNING_LOCALE
    permissions: tuple[str, ...] = LOCAL_LEARNING_PERMISSIONS


def is_local_learning_mode_enabled() -> bool:
    return os.environ.get(LOCAL_LEARNING_MODE_ENV, "").strip().lower() == "true"


def _session_engine(db_session: AsyncSession) -> AsyncEngine:
    bind = db_session.bind
    if isinstance(bind, AsyncEngine):
        return bind
    engine = getattr(bind, "engine", None)
    if isinstance(engine, AsyncEngine):
        return engine
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Local learning provisioning database is unavailable",
    )


@asynccontextmanager
async def _provisioning_lock(
    db_session: AsyncSession,
) -> AsyncIterator[None]:
    engine = _session_engine(db_session)
    dialect = engine.dialect.name

    if dialect == "sqlite":
        if os.environ.get("TESTING", "").strip().lower() != "true":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Local learning provisioning database is unsupported",
            )
        async with _SQLITE_PROVISIONING_LOCK:
            yield
        return

    if dialect != "postgresql":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local learning provisioning database is unsupported",
        )

    async with engine.begin() as lock_connection:
        await lock_connection.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _POSTGRES_PROVISIONING_LOCK_ID},
        )
        yield


async def _get_organization(db_session: AsyncSession) -> Organization | None:
    return (
        await db_session.execute(
            select(Organization).where(Organization.slug == LOCAL_LEARNING_ORG_SLUG)
        )
    ).scalars().first()


async def _get_owner(db_session: AsyncSession) -> User | None:
    by_email = (
        await db_session.execute(
            select(User).where(User.email == LOCAL_LEARNING_OWNER_EMAIL)
        )
    ).scalars().first()
    by_username = (
        await db_session.execute(
            select(User).where(User.username == LOCAL_LEARNING_OWNER_USERNAME)
        )
    ).scalars().first()

    if by_email and by_username and by_email.id != by_username.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local learning owner identity conflicts with existing users",
        )
    owner = by_email or by_username
    if owner and (
        owner.username != LOCAL_LEARNING_OWNER_USERNAME
        or str(owner.email) != LOCAL_LEARNING_OWNER_EMAIL
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local learning owner identity conflicts with an existing user",
        )
    return owner


async def _require_admin_membership(
    db_session: AsyncSession, user_id: int, org_id: int
) -> None:
    membership = (
        await db_session.execute(
            select(UserOrganization).where(
                UserOrganization.user_id == user_id,
                UserOrganization.org_id == org_id,
            )
        )
    ).scalars().first()
    if membership is None or membership.role_id != ADMIN_ROLE_ID:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local learning owner is missing the default admin permissions",
        )


async def _ensure_locale(
    db_session: AsyncSession,
    organization: Organization,
) -> None:
    org_config = (
        await db_session.execute(
            select(OrganizationConfig).where(
                OrganizationConfig.org_id == organization.id
            )
        )
    ).scalars().first()
    if org_config is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local learning organization config is missing",
        )
    if get_org_default_language(org_config) == LOCAL_LEARNING_LOCALE:
        return

    updated_config = deepcopy(org_config.config)
    if "customization" in updated_config:
        updated_config.setdefault("customization", {}).setdefault("general", {})[
            "default_language"
        ] = LOCAL_LEARNING_LOCALE
    else:
        updated_config.setdefault("general", {})[
            "default_language"
        ] = LOCAL_LEARNING_LOCALE

    await update_org_with_config_no_auth(
        cast(Request, None),
        updated_config,
        int(organization.id or 0),
        db_session,
    )


async def _provision_locked(
    db_session: AsyncSession,
) -> LocalLearningProvisioning:
    await install_default_elements(db_session)

    organization = await _get_organization(db_session)
    if organization is not None and organization.name != LOCAL_LEARNING_ORG_NAME:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local learning organization conflicts with existing data",
        )

    stored_owner = await _get_owner(db_session)
    if stored_owner is not None and not stored_owner.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local learning owner is not the configured instance owner",
        )

    password = os.environ.get(_OWNER_PASSWORD_ENV)
    if stored_owner is None and not password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local learning owner credential is not configured",
        )

    created = False
    if organization is None:
        organization = await install_create_organization(
            OrganizationCreate(
                name=LOCAL_LEARNING_ORG_NAME,
                description=LOCAL_LEARNING_ORG_NAME,
                slug=LOCAL_LEARNING_ORG_SLUG,
                email="",
                logo_image="",
                thumbnail_image="",
                about="",
                label="",
            ),
            db_session,
        )
        created = True

    if stored_owner is None:
        owner = await install_create_organization_user(
            UserCreate(
                username=LOCAL_LEARNING_OWNER_USERNAME,
                email=LOCAL_LEARNING_OWNER_EMAIL,
                password=password or "",
            ),
            LOCAL_LEARNING_ORG_SLUG,
            db_session,
            is_superadmin=True,
        )
        created = True
    else:
        owner = UserRead.model_validate(stored_owner)

    await _require_admin_membership(
        db_session,
        owner.id,
        int(organization.id or 0),
    )
    await _ensure_locale(db_session, organization)

    return LocalLearningProvisioning(
        created=created,
        user=owner,
        organization=organization,
    )


async def provision_local_learning_mode(
    db_session: AsyncSession,
) -> LocalLearningProvisioning:
    async with _provisioning_lock(db_session):
        return await _provision_locked(db_session)
