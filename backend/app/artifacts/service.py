import asyncio
import base64
import mimetypes
import shutil
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.artifacts.schemas import ArtifactView
from app.db.models import Artifact, utc_now
from app.sandbox.models import SandboxArtifact

_ALLOWED_ARTIFACT_SUFFIXES = {".csv", ".json", ".png"}
_MAX_ARTIFACT_PATH_LENGTH = 240


class ArtifactStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        storage_root: Path,
    ) -> None:
        self._session_factory = session_factory
        self._storage_root = storage_root.resolve()

    async def persist(
        self,
        workspace_id: UUID,
        artifacts: list[SandboxArtifact],
    ) -> list[ArtifactView]:
        if not artifacts:
            return []

        batch_id = uuid4()
        batch_dir = self._storage_root / str(batch_id)
        records: list[Artifact] = []
        try:
            async with self._session_factory() as session:
                for item in artifacts:
                    artifact_id = uuid4()
                    relative_path = _safe_relative_path(item.path)
                    content = base64.b64decode(item.content_base64, validate=True)
                    if len(content) != item.size:
                        raise ValueError(f"Artifact size mismatch: {relative_path}")
                    target = batch_dir / str(artifact_id) / relative_path
                    await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
                    await asyncio.to_thread(target.write_bytes, content)
                    record = Artifact(
                        id=artifact_id,
                        workspace_id=workspace_id,
                        filename=relative_path.name,
                        stored_path=str(target),
                        mime_type=(
                            mimetypes.guess_type(relative_path.name)[0]
                            or "application/octet-stream"
                        ),
                        size=len(content),
                        metadata_json={
                            "relative_path": relative_path.as_posix(),
                            "sandbox_mime_type": item.mime_type,
                        },
                        created_at=utc_now(),
                    )
                    session.add(record)
                    records.append(record)
                await session.commit()
        except Exception:
            await asyncio.to_thread(
                shutil.rmtree,
                batch_dir,
                ignore_errors=True,
            )
            raise
        return [_artifact_view(record) for record in records]


class ArtifactService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def get(
        self,
        workspace_id: UUID,
        artifact_id: UUID,
    ) -> Artifact | None:
        async with self._session_factory() as session:
            record = await session.scalar(
                select(Artifact).where(
                    Artifact.id == artifact_id,
                    Artifact.workspace_id == workspace_id,
                )
            )
            return record if isinstance(record, Artifact) else None


def _artifact_view(record: Artifact) -> ArtifactView:
    return ArtifactView(
        id=record.id,
        filename=record.filename,
        mime_type=record.mime_type,
        size=record.size,
        url=f"/api/artifacts/{record.id}",
        created_at=record.created_at,
    )


def _safe_relative_path(value: str) -> Path:
    path = PurePosixPath(value)
    if (
        not value
        or len(value) > _MAX_ARTIFACT_PATH_LENGTH
        or "\\" in value
        or ":" in value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"Invalid artifact path: {value}")
    if path.suffix.casefold() not in _ALLOWED_ARTIFACT_SUFFIXES:
        raise ValueError(f"Unsupported artifact type: {value}")
    return Path(*path.parts)
