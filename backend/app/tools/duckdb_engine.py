import threading
from pathlib import Path
from time import perf_counter
from typing import Any

import duckdb
from pydantic import BaseModel, Field

from app.core.serialization import json_safe


class TableInfo(BaseModel):
    name: str
    table_type: str


class ColumnInfo(BaseModel):
    name: str
    data_type: str
    nullable: bool


class TableSchema(BaseModel):
    table_name: str
    columns: list[ColumnInfo]
    sample_rows: list[dict[str, Any]]


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int = Field(ge=0)
    truncated: bool
    elapsed_ms: float = Field(ge=0)


class DuckDBAnalyticsEngine:
    def __init__(
        self,
        database: str | Path = ":memory:",
        *,
        max_query_rows: int = 1000,
        sample_rows: int = 3,
    ) -> None:
        if max_query_rows < 1:
            raise ValueError("max_query_rows must be positive.")
        if sample_rows < 0:
            raise ValueError("sample_rows must not be negative.")

        self._connection = duckdb.connect(str(database))
        self._lock = threading.RLock()
        self._max_query_rows = max_query_rows
        self._sample_rows = sample_rows

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def register_csv(self, table_name: str, csv_path: str | Path) -> None:
        self.register_file(table_name, csv_path)

    def register_parquet(self, table_name: str, parquet_path: str | Path) -> None:
        self.register_file(table_name, parquet_path)

    def register_file(self, table_name: str, file_path: str | Path) -> None:
        self._validate_identifier(table_name)
        path = Path(file_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        suffix = path.suffix.casefold()
        if suffix not in {".csv", ".tsv", ".parquet", ".pq"}:
            raise ValueError(f"Unsupported data file type: {suffix}")

        with self._lock:
            relation = (
                self._connection.read_parquet(str(path))
                if suffix in {".parquet", ".pq"}
                else self._connection.read_csv(str(path))
            )
            relation.create_view(table_name, replace=True)

    def list_tables(self) -> list[TableInfo]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT table_name, table_type
                FROM information_schema.tables
                WHERE table_schema = 'main'
                ORDER BY table_name
                """
            ).fetchall()
        return [TableInfo(name=str(row[0]), table_type=str(row[1])) for row in rows]

    def list_table_names(self) -> list[str]:
        return [table.name for table in self.list_tables()]

    def get_schema(self, table_name: str) -> TableSchema:
        self._validate_identifier(table_name)
        if table_name.casefold() not in {name.casefold() for name in self.list_table_names()}:
            raise KeyError(f"Unknown table: {table_name}")

        quoted_name = _quote_identifier(table_name)
        with self._lock:
            description = self._connection.execute(
                f"DESCRIBE SELECT * FROM {quoted_name}"  # noqa: S608
            ).fetchall()
            sample_cursor = self._connection.execute(
                f"SELECT * FROM {quoted_name} LIMIT {self._sample_rows}"  # noqa: S608
            )
            column_names = [str(column[0]) for column in sample_cursor.description]
            sample_rows = sample_cursor.fetchall()

        columns = [
            ColumnInfo(
                name=str(row[0]),
                data_type=str(row[1]),
                nullable=str(row[2]).upper() == "YES",
            )
            for row in description
        ]
        samples = [
            {
                column_name: json_safe(value)
                for column_name, value in zip(column_names, row, strict=True)
            }
            for row in sample_rows
        ]
        return TableSchema(
            table_name=table_name,
            columns=columns,
            sample_rows=samples,
        )

    def execute_select(self, sql: str, *, max_rows: int | None = None) -> QueryResult:
        row_limit = (
            self._max_query_rows if max_rows is None else min(max_rows, self._max_query_rows)
        )
        if row_limit < 1:
            raise ValueError("max_rows must be positive.")

        started = perf_counter()
        with self._lock:
            cursor = self._connection.execute(sql)
            column_names = [str(column[0]) for column in cursor.description]
            raw_rows = cursor.fetchmany(row_limit + 1)

        truncated = len(raw_rows) > row_limit
        visible_rows = raw_rows[:row_limit]
        rows = [
            {
                column_name: json_safe(value)
                for column_name, value in zip(column_names, row, strict=True)
            }
            for row in visible_rows
        ]
        return QueryResult(
            columns=column_names,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            elapsed_ms=(perf_counter() - started) * 1000,
        )

    @staticmethod
    def _validate_identifier(value: str) -> None:
        if not value or not value.replace("_", "").isalnum() or value[0].isdigit():
            raise ValueError("Invalid DuckDB identifier.")


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
