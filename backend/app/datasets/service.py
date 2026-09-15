import asyncio
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.datasets.processor import (
    AsyncUpload,
    DatasetProcessor,
    ProcessedDataset,
)
from app.datasets.schemas import DatasetSummary, DatasetView
from app.db.models import Dataset
from app.tools.duckdb_engine import (
    ColumnInfo,
    DuckDBAnalyticsEngine,
    QueryResult,
)


class DatasetService:
    def __init__(
        self,
        *,
        processor: DatasetProcessor,
        session_factory: async_sessionmaker[AsyncSession],
        engine: DuckDBAnalyticsEngine,
    ) -> None:
        self._processor = processor
        self._session_factory = session_factory
        self._engine = engine

    async def ingest(self, filename: str, upload: AsyncUpload) -> DatasetView:
        dataset_id = uuid4()
        processed = await self._processor.process(
            dataset_id=dataset_id,
            filename=filename,
            upload=upload,
        )
        try:
            async with self._session_factory() as session:
                dataset = _dataset_from_processed(processed)
                session.add(dataset)
                await session.commit()
                await session.refresh(dataset)
                return _dataset_view(dataset)
        except Exception:
            self._processor.remove(dataset_id, processed.table_name)
            raise

    async def list_datasets(self) -> list[DatasetSummary]:
        statement = select(Dataset).order_by(desc(Dataset.created_at))
        async with self._session_factory() as session:
            datasets = list((await session.scalars(statement)).all())
        return [_dataset_summary(dataset) for dataset in datasets]

    async def get_dataset(self, dataset_id: UUID) -> DatasetView | None:
        async with self._session_factory() as session:
            dataset = await session.get(Dataset, dataset_id)
            return _dataset_view(dataset) if dataset is not None else None

    async def resolve_tables(self, table_names: list[str]) -> list[DatasetView]:
        if not table_names:
            return []
        statement = select(Dataset).where(Dataset.table_name.in_(table_names))
        async with self._session_factory() as session:
            datasets = list((await session.scalars(statement)).all())
        by_name = {dataset.table_name: dataset for dataset in datasets}
        missing = [name for name in table_names if name not in by_name]
        unavailable = [
            name for name in table_names if name in by_name and by_name[name].status != "ready"
        ]
        if missing or unavailable:
            names = ", ".join(missing + unavailable)
            raise ValueError(f"Datasets are not available for sandbox mounting: {names}.")
        return [_dataset_view(by_name[name]) for name in table_names]

    async def delete_dataset(self, dataset_id: UUID) -> bool:
        async with self._session_factory() as session:
            dataset = await session.get(Dataset, dataset_id)
            if dataset is None:
                return False
            table_name = dataset.table_name
            await session.execute(delete(Dataset).where(Dataset.id == dataset_id))
            await session.commit()
        self._processor.remove(dataset_id, table_name)
        return True

    async def preview_dataset(
        self,
        dataset_id: UUID,
        *,
        limit: int = 20,
    ) -> QueryResult | None:
        async with self._session_factory() as session:
            dataset = await session.get(Dataset, dataset_id)
            if dataset is None or dataset.status != "ready":
                return None
            table_name = dataset.table_name
        return await asyncio.to_thread(
            self._engine.preview_table,
            table_name,
            limit=limit,
        )

    async def restore_engine(self) -> None:
        async with self._session_factory() as session:
            datasets = list(
                (await session.scalars(select(Dataset).where(Dataset.status == "ready"))).all()
            )
            changed = False
            for dataset in datasets:
                parquet_path = Path(dataset.parquet_path or "")
                if not await asyncio.to_thread(parquet_path.is_file):
                    dataset.status = "failed"
                    dataset.error_message = "Stored Parquet file is missing."
                    changed = True
                    continue
                try:
                    self._engine.register_parquet(
                        dataset.table_name,
                        parquet_path,
                    )
                except Exception as exc:
                    dataset.status = "failed"
                    dataset.error_message = f"Unable to restore dataset: {exc}"
                    changed = True
            if changed:
                await session.commit()


def _dataset_from_processed(processed: ProcessedDataset) -> Dataset:
    return Dataset(
        id=processed.id,
        name=processed.name,
        original_filename=processed.original_filename,
        table_name=processed.table_name,
        file_type=processed.file_type,
        file_size=processed.file_size,
        status="ready",
        original_path=str(processed.original_path),
        parquet_path=str(processed.parquet_path),
        row_count=processed.row_count,
        columns=[column.model_dump(mode="json") for column in processed.columns],
    )


def _dataset_view(dataset: Dataset) -> DatasetView:
    return DatasetView(
        id=dataset.id,
        name=dataset.name,
        original_filename=dataset.original_filename,
        table_name=dataset.table_name,
        file_type=dataset.file_type,
        file_size=dataset.file_size,
        status=dataset.status,
        row_count=dataset.row_count,
        columns=[ColumnInfo.model_validate(column) for column in dataset.columns],
        error_message=dataset.error_message,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
    )


def _dataset_summary(dataset: Dataset) -> DatasetSummary:
    return DatasetSummary(
        id=dataset.id,
        name=dataset.name,
        original_filename=dataset.original_filename,
        table_name=dataset.table_name,
        file_type=dataset.file_type,
        file_size=dataset.file_size,
        status=dataset.status,
        row_count=dataset.row_count,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
    )
