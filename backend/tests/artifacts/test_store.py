import asyncio
import base64
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.artifacts.service import ArtifactStore, _safe_relative_path
from app.sandbox.models import SandboxArtifact


class FakeSession:
    def __init__(self) -> None:
        self.records: list[Any] = []
        self.commits = 0

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    def add(self, record: Any) -> None:
        self.records.append(record)

    async def commit(self) -> None:
        self.commits += 1


class FakeSessionFactory:
    def __init__(self) -> None:
        self.session = FakeSession()

    def __call__(self) -> FakeSession:
        return self.session


@pytest.mark.asyncio
async def test_artifact_store_persists_validated_files(tmp_path: Path) -> None:
    factory = FakeSessionFactory()
    store = ArtifactStore(
        cast(async_sessionmaker[AsyncSession], factory),
        tmp_path,
    )
    content = b"region,total\nEast,42\n"

    views = await store.persist(
        [
            SandboxArtifact(
                path="result.csv",
                mime_type="text/csv",
                size=len(content),
                content_base64=base64.b64encode(content).decode("ascii"),
            )
        ]
    )

    assert factory.session.commits == 1
    assert len(views) == 1
    assert views[0].filename == "result.csv"
    stored = Path(cast(Any, factory.session.records[0]).stored_path)
    assert await asyncio.to_thread(stored.is_file)
    assert await asyncio.to_thread(stored.read_bytes) == content
    assert stored.is_relative_to(tmp_path)


@pytest.mark.asyncio
async def test_artifact_store_error_only_removes_current_batch(tmp_path: Path) -> None:
    historical = tmp_path / "historical" / "keep.csv"
    historical.parent.mkdir()
    historical.write_bytes(b"keep")
    factory = FakeSessionFactory()
    store = ArtifactStore(
        cast(async_sessionmaker[AsyncSession], factory),
        tmp_path,
    )

    with pytest.raises(ValueError, match="size mismatch"):
        await store.persist(
            [
                SandboxArtifact(
                    path="broken.csv",
                    mime_type="text/csv",
                    size=100,
                    content_base64=base64.b64encode(b"short").decode("ascii"),
                )
            ]
        )

    assert historical.read_bytes() == b"keep"
    assert factory.session.commits == 0


@pytest.mark.parametrize(
    "path",
    ["../escape.csv", "C:escape.csv", "folder\\escape.csv", "notes.txt"],
)
def test_artifact_store_rejects_unsafe_paths(path: str) -> None:
    with pytest.raises(ValueError):
        _safe_relative_path(path)
