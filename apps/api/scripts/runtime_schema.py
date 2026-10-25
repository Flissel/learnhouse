"""Prepare the controlled local Learning runtime schema."""

import importlib
import os
from pathlib import Path
from typing import Literal

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlmodel import SQLModel


APP_ROOT = Path(__file__).resolve().parents[1]


def _plan_schema_action(table_names: set[str]) -> Literal["adopt", "upgrade"]:
    return "upgrade" if "alembic_version" in table_names else "adopt"


def _load_all_models() -> None:
    db_root = APP_ROOT / "src" / "db"
    for module_path in sorted(db_root.rglob("*.py")):
        if module_path.name == "__init__.py":
            continue
        relative = module_path.relative_to(APP_ROOT).with_suffix("")
        importlib.import_module(".".join(relative.parts))


def _sync_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _alembic_config(database_url: str) -> Config:
    config = Config(str(APP_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def prepare_runtime_schema() -> None:
    if os.environ.get("LEARNHOUSE_LOCAL_LEARNING_MODE", "").lower() != "true":
        raise RuntimeError("runtime schema adoption requires local Learning mode")
    raw_url = os.environ.get("LEARNHOUSE_SQL_CONNECTION_STRING", "").strip()
    if not raw_url:
        raise RuntimeError("LEARNHOUSE_SQL_CONNECTION_STRING is required")

    _load_all_models()
    database_url = _sync_url(raw_url)
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        action = _plan_schema_action(set(inspect(engine).get_table_names()))
        config = _alembic_config(database_url)
        if action == "adopt":
            SQLModel.metadata.create_all(engine)
            command.stamp(config, "head")
        else:
            command.upgrade(config, "head")
    finally:
        engine.dispose()


def main() -> int:
    prepare_runtime_schema()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
