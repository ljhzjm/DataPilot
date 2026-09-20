from contextvars import ContextVar, Token
from uuid import UUID

_workspace_id: ContextVar[UUID | None] = ContextVar("datapilot_workspace_id", default=None)


def set_workspace_id(workspace_id: UUID) -> Token[UUID | None]:
    return _workspace_id.set(workspace_id)


def reset_workspace_id(token: Token[UUID | None]) -> None:
    _workspace_id.reset(token)


def require_workspace_id() -> UUID:
    workspace_id = _workspace_id.get()
    if workspace_id is None:
        raise RuntimeError("No workspace is active for the current operation.")
    return workspace_id


def get_workspace_id() -> UUID | None:
    return _workspace_id.get()
