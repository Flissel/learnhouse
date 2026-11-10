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


TEIL_B_TABLES = {"learning_person", "learning_link", "learning_gruppe", "learning_entfernung"}


def test_runtime_schema_registers_the_teil_b_tables() -> None:
    runtime_schema._load_all_models()

    assert TEIL_B_TABLES <= set(runtime_schema.SQLModel.metadata.tables)


def _teil_b_revision():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(runtime_schema.APP_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(runtime_schema.APP_ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1
    return script.get_revision(heads[0])


def test_teil_b_migration_is_the_single_head_after_the_service_state() -> None:
    assert _teil_b_revision().down_revision == "d0e1f2a3b4c5"


def test_teil_b_migration_creates_and_drops_the_teil_b_tables() -> None:
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine, exc, inspect, text

    module = _teil_b_revision().module
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        for table in ('"user"', "organization", "usergroup", "course"):
            conn.execute(text(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)"))
        conn.execute(text('INSERT INTO "user" (id) VALUES (1)'))
        conn.execute(text("INSERT INTO organization (id) VALUES (1)"))
        context = MigrationContext.configure(conn)
        with Operations.context(context):
            module.upgrade()
            module.upgrade()  # idempotent like the other learning migrations
        inspector = inspect(conn)
        assert TEIL_B_TABLES <= set(inspector.get_table_names())
        assert {c["name"] for c in inspector.get_columns("learning_person")} == {"user_id", "actor_id", "erstellt_am"}
        assert {c["name"] for c in inspector.get_columns("learning_link")} == {
            "id", "token_sha256", "art", "org_id", "gruppe_id", "erstellt_von", "erstellt_am", "laeuft_ab",
            "zurueckgezogen_am",
        }
        assert {c["name"] for c in inspector.get_columns("learning_gruppe")} == {
            "id", "usergroup_id", "course_id", "offen", "erstellt_von", "erstellt_am",
        }
        assert {c["name"] for c in inspector.get_columns("learning_entfernung")} == {
            "user_id", "org_id", "entfernt_am",
        }
        entfernung = ("INSERT INTO learning_entfernung (user_id, org_id, entfernt_am) "
                      "VALUES (1, 1, CURRENT_TIMESTAMP)")
        conn.execute(text(entfernung))
        conn.execute(text("INSERT INTO learning_person (user_id, actor_id, erstellt_am) VALUES (1, 'lh-1-a', CURRENT_TIMESTAMP)"))
        link = ("INSERT INTO learning_link (token_sha256, art, org_id, erstellt_von, erstellt_am) "
                "VALUES (:t, :art, 1, 1, CURRENT_TIMESTAMP)")
        conn.execute(text(link), {"t": "a" * 64, "art": "admin"})
        for statement, values in (
            ("INSERT INTO learning_person (user_id, actor_id, erstellt_am) VALUES (2, 'lh-1-a', CURRENT_TIMESTAMP)", {}),
            (link, {"t": "b" * 64, "art": "root"}),
            (link, {"t": "a" * 64, "art": "kursleiter"}),
            (entfernung, {}),  # one note per person and provider
        ):
            # SQLite undoes only the failing statement; the transaction goes on.
            with pytest.raises(exc.IntegrityError):
                conn.execute(text(statement), values)
        with Operations.context(context):
            module.downgrade()
        assert not TEIL_B_TABLES & set(inspect(conn).get_table_names())
