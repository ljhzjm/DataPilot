from app.core.config import get_settings
from app.datasets.processor import DatasetProcessor
from app.datasets.service import DatasetService
from app.db.session import AsyncSessionLocal
from app.tools.duckdb_engine import DuckDBAnalyticsEngine


def build_dataset_service(engine: DuckDBAnalyticsEngine) -> DatasetService:
    settings = get_settings()
    return DatasetService(
        processor=DatasetProcessor(
            engine=engine,
            upload_root=settings.dataset_upload_dir,
            max_upload_bytes=settings.dataset_max_upload_bytes,
            max_rows=settings.dataset_max_rows,
            max_columns=settings.dataset_max_columns,
        ),
        session_factory=AsyncSessionLocal,
        engine=engine,
    )
