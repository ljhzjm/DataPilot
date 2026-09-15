from io import BytesIO
from pathlib import Path
from uuid import uuid4

import openpyxl
import pytest

from app.datasets.processor import DatasetProcessingError, DatasetProcessor
from app.tools.duckdb_engine import DuckDBAnalyticsEngine


class FakeUpload:
    def __init__(self, content: bytes) -> None:
        self._stream = BytesIO(content)

    async def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)


@pytest.mark.asyncio
async def test_csv_upload_is_converted_to_parquet_and_bound_to_duckdb(
    tmp_path: Path,
) -> None:
    engine = DuckDBAnalyticsEngine()
    processor = DatasetProcessor(engine=engine, upload_root=tmp_path / "uploads")
    dataset_id = uuid4()
    content = b"region,amount\nEast,10\nWest,20\n"

    try:
        processed = await processor.process(
            dataset_id=dataset_id,
            filename="../../sales.csv",
            upload=FakeUpload(content),
        )
        result = engine.execute_select(
            f"SELECT SUM(amount) AS total FROM {processed.table_name}"  # noqa: S608
        )
    finally:
        engine.close()

    assert processed.original_filename == "sales.csv"
    assert processed.file_type == "csv"
    assert processed.row_count == 2
    assert processed.parquet_path.is_file()
    assert result.rows == [{"total": 30}]


@pytest.mark.asyncio
async def test_xlsx_upload_is_normalized_and_bound_to_duckdb(tmp_path: Path) -> None:
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet.append(["name", "amount", "amount"])
    worksheet.append(["Alice", 10, 1])
    worksheet.append(["Bob", 20, 2])
    excel_buffer = BytesIO()
    workbook.save(excel_buffer)
    workbook.close()

    engine = DuckDBAnalyticsEngine()
    processor = DatasetProcessor(engine=engine, upload_root=tmp_path / "uploads")

    try:
        processed = await processor.process(
            dataset_id=uuid4(),
            filename="employees.xlsx",
            upload=FakeUpload(excel_buffer.getvalue()),
        )
        result = engine.execute_select(
            f"SELECT name, amount, amount_2 FROM {processed.table_name} "  # noqa: S608
            "ORDER BY name"
        )
    finally:
        engine.close()

    assert processed.file_type == "xlsx"
    assert [column.name for column in processed.columns] == [
        "name",
        "amount",
        "amount_2",
    ]
    assert result.rows == [
        {"name": "Alice", "amount": 10, "amount_2": 1},
        {"name": "Bob", "amount": 20, "amount_2": 2},
    ]


@pytest.mark.asyncio
async def test_dataset_processor_rejects_unsupported_and_oversized_files(
    tmp_path: Path,
) -> None:
    engine = DuckDBAnalyticsEngine()
    processor = DatasetProcessor(
        engine=engine,
        upload_root=tmp_path / "uploads",
        max_upload_bytes=4,
    )

    try:
        with pytest.raises(DatasetProcessingError, match="Unsupported file type"):
            await processor.process(
                dataset_id=uuid4(),
                filename="data.json",
                upload=FakeUpload(b"{}"),
            )
        with pytest.raises(DatasetProcessingError, match="File exceeds"):
            await processor.process(
                dataset_id=uuid4(),
                filename="data.csv",
                upload=FakeUpload(b"a,b\n1,2\n"),
            )
    finally:
        engine.close()
