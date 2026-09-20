from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_alembic_has_one_head_and_generates_initial_schema_sql() -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    output = StringIO()

    with redirect_stdout(output):
        command.upgrade(config, "head", sql=True)

    sql = output.getvalue()
    assert script.get_heads() == ["20260920_0006"]
    assert "CREATE TABLE conversations" in sql
    assert "CREATE TABLE messages" in sql
    assert "CREATE TABLE agent_steps" in sql
    assert "CREATE TABLE datasets" in sql
    assert "ADD COLUMN request_id" in sql
    assert "ADD COLUMN next_sequence" in sql
    assert "ADD COLUMN archived_at" in sql
    assert "CREATE TABLE usage_records" in sql
    assert "ADD COLUMN trace_id" in sql
    assert "CREATE TABLE artifacts" in sql
    assert "CREATE TABLE users" in sql
    assert "CREATE TABLE workspaces" in sql
    assert "CREATE TABLE auth_sessions" in sql
    assert "ADD COLUMN workspace_id" in sql
