from fastapi import APIRouter

from src.core.learning_mode import is_local_learning_mode_enabled


def mount_local_learning_bootstrap(target_router: APIRouter) -> bool:
    if not is_local_learning_mode_enabled():
        return False

    from src.routers.learning import bootstrap
    from src.routers.learning import service

    target_router.include_router(
        bootstrap.router,
        prefix="/learning",
        tags=["learning"],
    )
    target_router.include_router(
        service.router,
        prefix="/learning",
        tags=["learning"],
    )
    return True
