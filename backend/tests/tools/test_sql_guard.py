import pytest

from app.tools.sql_guard import SQLPolicy, SQLValidationError


def test_sql_policy_allows_select_against_whitelisted_tables() -> None:
    policy = SQLPolicy()

    sql = policy.validate(
        "SELECT region, SUM(amount) AS total FROM sales GROUP BY region",
        allowed_tables={"sales"},
    )

    assert sql.startswith("SELECT")
    assert "sales" in sql


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE sales SET amount = 0",
        "DELETE FROM sales",
        "SELECT * INTO backup FROM sales",
        "SELECT * FROM secrets",
        "SELECT * FROM read_csv_auto('/etc/passwd')",
        "SELECT read_text('/etc/passwd')",
        "SELECT getenv('SECRET')",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT pg_notify('channel', 'payload')",
        "SELECT 1; SELECT 2",
    ],
)
def test_sql_policy_rejects_unsafe_statements(sql: str) -> None:
    policy = SQLPolicy()

    with pytest.raises(SQLValidationError):
        policy.validate(sql, allowed_tables={"sales"})


def test_sql_policy_rejects_more_than_300_lines() -> None:
    sql = "SELECT 1\n" + "\n".join(f"-- line {index}" for index in range(301))

    with pytest.raises(SQLValidationError, match="manual review"):
        SQLPolicy().validate(sql, allowed_tables={"sales"})
