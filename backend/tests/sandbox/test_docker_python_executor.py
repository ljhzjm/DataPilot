from collections.abc import Iterator

import pytest
from docker import DockerClient
from docker.errors import DockerException, ImageNotFound

from app.sandbox.python_executor import DockerPythonExecutor

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def docker_python_executor() -> Iterator[DockerPythonExecutor]:
    try:
        client = DockerClient.from_env()
        client.ping()
        client.images.get("datapilot/sandbox:dev")
    except (DockerException, ImageNotFound) as exc:
        pytest.skip(f"Docker sandbox integration environment is unavailable: {exc}")

    yield DockerPythonExecutor(
        client=client,
        image="datapilot/sandbox:dev",
        timeout_seconds=1,
        output_limit_bytes=8192,
    )
    client.close()


@pytest.mark.asyncio
async def test_python_sandbox_executes_code_with_input_file(
    docker_python_executor: DockerPythonExecutor,
) -> None:
    result = await docker_python_executor.execute(
        """
from pathlib import Path

value = int(Path("input.txt").read_text(encoding="utf-8"))
print(value * 2)
""",
        input_files={"input.txt": "21"},
    )

    assert result.ok is True
    assert result.stdout.strip() == "42"
    assert result.stderr == ""
    assert result.timed_out is False


@pytest.mark.asyncio
async def test_python_sandbox_kills_infinite_loop(
    docker_python_executor: DockerPythonExecutor,
) -> None:
    result = await docker_python_executor.execute(
        "while True:\n    pass\n",
        timeout_seconds=0.5,
    )

    assert result.ok is False
    assert result.timed_out is True
    assert "timed out" in result.stderr.lower()


@pytest.mark.asyncio
async def test_python_sandbox_has_no_network_access(
    docker_python_executor: DockerPythonExecutor,
) -> None:
    result = await docker_python_executor.execute(
        """
import socket

socket.create_connection(("1.1.1.1", 53), timeout=1)
""",
    )

    assert result.ok is False
    assert "Network is unreachable" in result.stderr


@pytest.mark.asyncio
async def test_python_sandbox_truncates_stdout(
    docker_python_executor: DockerPythonExecutor,
) -> None:
    result = await docker_python_executor.execute("print('x' * 9000)")

    assert result.ok is True
    assert result.truncated is True
    assert len(result.stdout.encode("utf-8")) == 8192
