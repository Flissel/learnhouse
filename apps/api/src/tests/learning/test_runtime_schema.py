from importlib.util import find_spec
from unittest.mock import Mock

import pytest

from scripts import runtime_schema


def test_runtime_schema_module_is_available() -> None:
    assert find_spec("scripts.runtime_schema") is not None


def test_schema_action_adopts_only_unversioned_databases() -> None:
    assert runtime_schema._plan_schema_action(set()) == "adopt"
    assert runtime_schema._plan_schema_action({"course", "activity"}) == "adopt"
    assert runtime_schema._plan_schema_action({"alembic_version"}) == "upgrade"


def test_runtime_schema_refuses_non_local_mode(monkeypatch) -> None:
    monkeypatch.delenv("LEARNHOUSE_LOCAL_LEARNING_MODE", raising=False)

    with pytest.raises(RuntimeError, match="local Learning mode"):
        runtime_schema.prepare_runtime_schema()


@pytest.mark.parametrize(
    ("tables", "expected_command"),
    [
        ({"course", "activity"}, "stamp"),
        ({"course", "activity", "alembic_version"}, "upgrade"),
    ],
)
def test_runtime_schema_adopts_or_upgrades_once(
    monkeypatch, tables: set[str], expected_command: str
) -> None:
    monkeypatch.setenv("LEARNHOUSE_LOCAL_LEARNING_MODE", "true")
    monkeypatch.setenv(
        "LEARNHOUSE_SQL_CONNECTION_STRING",
        "postgresql+asyncpg://learning:secret@postgres:5432/learning",
    )
    engine = Mock()
    inspector = Mock()
    inspector.get_table_names.return_value = sorted(tables)
    create_all = Mock()
    stamp = Mock()
    upgrade = Mock()
    monkeypatch.setattr(runtime_schema, "_load_all_models", Mock())
    monkeypatch.setattr(runtime_schema, "create_engine", Mock(return_value=engine))
    monkeypatch.setattr(runtime_schema, "inspect", Mock(return_value=inspector))
    monkeypatch.setattr(runtime_schema.SQLModel.metadata, "create_all", create_all)
    monkeypatch.setattr(runtime_schema.command, "stamp", stamp)
    monkeypatch.setattr(runtime_schema.command, "upgrade", upgrade)

    runtime_schema.prepare_runtime_schema()

    if expected_command == "stamp":
        create_all.assert_called_once_with(engine)
        stamp.assert_called_once()
        upgrade.assert_not_called()
    else:
        create_all.assert_not_called()
        stamp.assert_not_called()
        upgrade.assert_called_once()
    engine.dispose.assert_called_once_with()
