import hmac
import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.events.database import get_db_session
from src.core.learning_mode import (
    LOCAL_LEARNING_BOOTSTRAP_HEADER,
    LOCAL_LEARNING_BOOTSTRAP_KEY_ENV,
    LOCAL_LEARNING_BOOTSTRAP_KEY_MIN_LENGTH,
    is_local_learning_mode_enabled,
    provision_local_learning_mode,
)


router = APIRouter()


class LocalLearningOwnerRead(BaseModel):
    username: str


class LocalLearningOrganizationRead(BaseModel):
    name: str
    slug: str


class LocalLearningBootstrapResponse(BaseModel):
    status: Literal["created", "ready"]
    owner: LocalLearningOwnerRead
    organization: LocalLearningOrganizationRead
    locale: str
    permissions: list[str]


def require_local_learning_bootstrap(request: Request) -> None:
    if not is_local_learning_mode_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    configured_key = os.environ.get(LOCAL_LEARNING_BOOTSTRAP_KEY_ENV, "")
    if len(configured_key) < LOCAL_LEARNING_BOOTSTRAP_KEY_MIN_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local learning bootstrap is not configured securely",
        )

    supplied_key = request.headers.get(LOCAL_LEARNING_BOOTSTRAP_HEADER, "")
    if not hmac.compare_digest(
        supplied_key.encode("utf-8"),
        configured_key.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid local learning bootstrap credentials",
        )


@router.post(
    "/bootstrap",
    response_model=LocalLearningBootstrapResponse,
    dependencies=[Depends(require_local_learning_bootstrap)],
)
async def bootstrap_local_learning_mode(
    db_session: AsyncSession = Depends(get_db_session),
) -> LocalLearningBootstrapResponse:
    provisioned = await provision_local_learning_mode(db_session)
    return LocalLearningBootstrapResponse(
        status="created" if provisioned.created else "ready",
        owner=LocalLearningOwnerRead(username=provisioned.user.username),
        organization=LocalLearningOrganizationRead(
            name=provisioned.organization.name,
            slug=provisioned.organization.slug,
        ),
        locale=provisioned.locale,
        permissions=list(provisioned.permissions),
    )
