import base64
from pathlib import Path
from typing import cast

import pytest
from docker import DockerClient

from app.sandbox.python_executor import DockerPythonExecutor


def test_collect_artifacts_limits_types_and_preserves_relative_paths(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "outputs"
    (output_dir / "nested").mkdir(parents=True)
    (output_dir / "nested" / "result.csv").write_bytes(b"value\n42\n")
    (output_dir / "chart.png").write_bytes(b"\x89PNG\r\n")
    (output_dir / "ignored.txt").write_text("not collected", encoding="utf-8")
    executor = DockerPythonExecutor(
        client=cast(DockerClient, object()),
        artifact_work_root=tmp_path,
        artifact_max_files=20,
        artifact_max_bytes=1024,
    )

    artifacts = executor._collect_artifacts(output_dir)

    by_path = {artifact.path: artifact for artifact in artifacts}
    assert set(by_path) == {"nested/result.csv", "chart.png"}
    assert base64.b64decode(by_path["nested/result.csv"].content_base64) == b"value\n42\n"


def test_collect_artifacts_rejects_excessive_total_size(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    (output_dir / "result.csv").write_bytes(b"x" * 200)
    executor = DockerPythonExecutor(
        client=cast(DockerClient, object()),
        artifact_work_root=tmp_path,
        artifact_max_files=20,
        artifact_max_bytes=100,
    )

    with pytest.raises(ValueError, match="limits"):
        executor._collect_artifacts(output_dir)
