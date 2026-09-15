from collections.abc import Iterable

from sqlglot import exp, parse
from sqlglot.errors import ParseError

READ_ONLY_ROOTS = {"Select", "Union", "Intersect", "Except"}
FORBIDDEN_NODES = {
    "Alter",
    "Attach",
    "Command",
    "Commit",
    "Copy",
    "Create",
    "Delete",
    "Detach",
    "Drop",
    "Execute",
    "Grant",
    "Insert",
    "Into",
    "Pragma",
    "Prepare",
    "Rollback",
    "Set",
    "Transaction",
    "TruncateTable",
    "Update",
    "Use",
}
FORBIDDEN_FUNCTIONS = {
    "currentsetting",
    "dblink",
    "dblinkconnect",
    "getenv",
    "glob",
    "installextension",
    "loexport",
    "loimport",
    "loadextension",
    "mysqlscan",
    "parquetscan",
    "pgcancelbackend",
    "pgadvisorylock",
    "pgadvisorylockshared",
    "pgnotify",
    "pgreadbinaryfile",
    "pgreadfile",
    "pgreadserverfiles",
    "pgsleep",
    "pgstatfile",
    "pgterminatebackend",
    "postgresscan",
    "query",
    "querytable",
    "readblob",
    "readcsv",
    "readcsvauto",
    "readjson",
    "readjsonauto",
    "readparquet",
    "readtext",
    "setconfig",
    "sqlitescan",
}


class SQLValidationError(ValueError):
    pass


class SQLPolicy:
    def __init__(
        self,
        *,
        dialect: str = "duckdb",
        max_lines: int = 300,
        max_chars: int = 100_000,
        allow_qualified_tables: bool = False,
    ) -> None:
        self._dialect = dialect
        self._max_lines = max_lines
        self._max_chars = max_chars
        self._allow_qualified_tables = allow_qualified_tables

    def validate(self, sql: str, *, allowed_tables: Iterable[str]) -> str:
        if not sql.strip():
            raise SQLValidationError("SQL must not be empty.")
        if len(sql) > self._max_chars:
            raise SQLValidationError(
                f"SQL exceeds the maximum length of {self._max_chars} characters."
            )
        if len(sql.splitlines()) > self._max_lines:
            raise SQLValidationError(
                f"SQL exceeds {self._max_lines} lines and requires manual review."
            )

        try:
            statements = parse(sql, read=self._dialect)
        except ParseError as exc:
            raise SQLValidationError(f"SQL syntax error: {exc}") from exc

        if len(statements) != 1 or statements[0] is None:
            raise SQLValidationError("Only one SQL statement is allowed.")

        expression = statements[0]
        if type(expression).__name__ not in READ_ONLY_ROOTS:
            raise SQLValidationError("Only SELECT queries are allowed.")

        for node in expression.walk():
            if type(node).__name__ in FORBIDDEN_NODES:
                raise SQLValidationError(f"SQL operation is not allowed: {type(node).__name__}.")
            if isinstance(node, exp.Anonymous):
                function_name = str(node.this).replace("_", "").casefold()
                if function_name in FORBIDDEN_FUNCTIONS:
                    raise SQLValidationError(f"SQL function is not allowed: {node.this}")
            elif isinstance(node, exp.Func):
                function_name = type(node).__name__.replace("_", "").casefold()
                if function_name in FORBIDDEN_FUNCTIONS:
                    raise SQLValidationError(f"SQL function is not allowed: {type(node).__name__}")

        cte_names = {
            cte.alias_or_name.casefold()
            for cte in expression.find_all(exp.CTE)
            if cte.alias_or_name
        }
        allowed = {table_name.casefold() for table_name in allowed_tables}

        for table in expression.find_all(exp.Table):
            if not isinstance(table.this, exp.Identifier):
                raise SQLValidationError(
                    "Table functions and dynamic data sources are not allowed."
                )
            if table.catalog:
                raise SQLValidationError("Qualified or external table names are not allowed.")

            if table.db and not self._allow_qualified_tables:
                raise SQLValidationError("Qualified or external table names are not allowed.")

            table_name = (
                f"{table.db}.{table.name}".casefold() if table.db else table.name.casefold()
            )
            if table_name in cte_names:
                continue
            if table_name not in allowed:
                raise SQLValidationError(f"Table is not allowed: {table_name}")

        return expression.sql(dialect=self._dialect)
