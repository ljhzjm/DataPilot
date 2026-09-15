"""Decode one sandbox task, create its temporary workspace, and run it."""

import base64
import json
import os
import sys
from pathlib import Path, PurePosixPath

WORKSPACE = Path("/workspace")
MAIN_FILE = WORKSPACE / "main.py"


def _safe_relative_path(value: str) -> Path:
    path = PurePosixPath(value)
    if path.is_absolute() or not value or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"Invalid sandbox input path: {value}")
    if path.parts[0] == "main.py":
        raise ValueError("Input files must not overwrite main.py.")
    return WORKSPACE.joinpath(*path.parts)


def _write_input_files(encoded: str) -> None:
    if not encoded:
        return
    files = json.loads(base64.b64decode(encoded).decode("utf-8"))
    if not isinstance(files, dict):
        raise ValueError("Sandbox input files must be an object.")

    for relative_path, content in files.items():
        if not isinstance(relative_path, str) or not isinstance(content, str):
            raise ValueError("Sandbox input files must map paths to base64 strings.")
        target = _safe_relative_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(content))


def main() -> None:
    encoded_files = os.environ.pop("SANDBOX_FILES_B64", "")
    encoded_code = os.environ.pop("SANDBOX_CODE_B64", "")
    if not encoded_code:
        raise ValueError("Missing sandbox code.")

    WORKSPACE.mkdir(parents=True, exist_ok=True)
    _write_input_files(encoded_files)
    MAIN_FILE.write_bytes(base64.b64decode(encoded_code))
    os.chdir(WORKSPACE)
    os.execv(sys.executable, [sys.executable, str(MAIN_FILE)])


if __name__ == "__main__":
    main()

