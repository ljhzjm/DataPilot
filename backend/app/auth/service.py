import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.schemas import AuthSessionView, UserView, WorkspaceView
from app.auth.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)
from app.db.models import AuthSession, User, Workspace, WorkspaceMember, utc_now

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")


class AuthError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AuthContext:
    user_id: UUID
    workspace_id: UUID
    session_id: UUID
    username: str
    display_name: str


@dataclass(frozen=True, slots=True)
class AuthResult:
    token: str
    session: AuthSessionView


class AuthService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        session_ttl_seconds: int = 7 * 24 * 60 * 60,
    ) -> None:
        self._session_factory = session_factory
        self._session_ttl_seconds = session_ttl_seconds

    async def register(
        self,
        *,
        username: str,
        password: str,
        display_name: str,
    ) -> AuthResult:
        normalized_username = username.strip().casefold()
        async with self._session_factory() as session:
            existing = await session.scalar(
                select(User).where(func.lower(User.username) == normalized_username)
            )
            if existing is not None:
                raise AuthError("Username is already registered.")

            user = User(
                username=username.strip(),
                display_name=display_name,
                password_hash=hash_password(password),
            )
            session.add(user)
            await session.flush()

            workspace = await session.scalar(
                select(Workspace)
                .where(
                    Workspace.id == DEFAULT_WORKSPACE_ID,
                    Workspace.owner_id.is_(None),
                )
                .with_for_update()
            )
            role = "owner"
            if workspace is None:
                workspace = Workspace(
                    name=f"{display_name} 的工作空间",
                    slug=f"workspace-{uuid4().hex[:12]}",
                    owner_id=user.id,
                )
                session.add(workspace)
                await session.flush()
            else:
                workspace.owner_id = user.id
                workspace.updated_at = utc_now()

            session.add(
                WorkspaceMember(
                    workspace_id=workspace.id,
                    user_id=user.id,
                    role=role,
                )
            )
            token = generate_session_token()
            auth_session = AuthSession(
                user_id=user.id,
                workspace_id=workspace.id,
                token_hash=hash_session_token(token),
                expires_at=datetime.now(UTC) + timedelta(seconds=self._session_ttl_seconds),
                last_seen_at=utc_now(),
            )
            session.add(auth_session)
            await session.commit()
            await session.refresh(user)
            await session.refresh(auth_session)
            return AuthResult(
                token=token,
                session=AuthSessionView(
                    user=_user_view(user),
                    workspace=_workspace_view(workspace, role),
                ),
            )

    async def login(self, *, username: str, password: str) -> AuthResult:
        normalized_username = username.strip().casefold()
        async with self._session_factory() as session:
            user = await session.scalar(
                select(User).where(func.lower(User.username) == normalized_username)
            )
            if user is None or not verify_password(password, user.password_hash):
                raise AuthError("Invalid username or password.")

            membership = await session.scalar(
                select(WorkspaceMember)
                .where(WorkspaceMember.user_id == user.id)
                .order_by(WorkspaceMember.created_at)
            )
            if membership is None:
                raise AuthError("User has no workspace membership.")
            workspace = await session.get(Workspace, membership.workspace_id)
            if workspace is None:
                raise AuthError("Workspace not found.")

            token = generate_session_token()
            auth_session = AuthSession(
                user_id=user.id,
                workspace_id=workspace.id,
                token_hash=hash_session_token(token),
                expires_at=datetime.now(UTC) + timedelta(seconds=self._session_ttl_seconds),
                last_seen_at=utc_now(),
            )
            session.add(auth_session)
            await session.commit()
            await session.refresh(auth_session)
            return AuthResult(
                token=token,
                session=AuthSessionView(
                    user=_user_view(user),
                    workspace=_workspace_view(workspace, membership.role),
                ),
            )

    async def authenticate(self, token: str) -> AuthContext | None:
        token_hash = hash_session_token(token)
        async with self._session_factory() as session:
            auth_session = await session.scalar(
                select(AuthSession).where(
                    AuthSession.token_hash == token_hash,
                    AuthSession.expires_at > utc_now(),
                )
            )
            if auth_session is None:
                return None
            user = await session.get(User, auth_session.user_id)
            membership = await session.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == auth_session.workspace_id,
                    WorkspaceMember.user_id == auth_session.user_id,
                )
            )
            if user is None or membership is None:
                return None
            auth_session.last_seen_at = utc_now()
            await session.commit()
            return AuthContext(
                user_id=user.id,
                workspace_id=auth_session.workspace_id,
                session_id=auth_session.id,
                username=user.username,
                display_name=user.display_name,
            )

    async def logout(self, session_id: UUID) -> None:
        async with self._session_factory() as session:
            auth_session = await session.get(AuthSession, session_id)
            if auth_session is not None:
                await session.delete(auth_session)
                await session.commit()

    async def current_session(self, context: AuthContext) -> AuthSessionView | None:
        async with self._session_factory() as session:
            user = await session.get(User, context.user_id)
            workspace = await session.get(Workspace, context.workspace_id)
            membership = await session.scalar(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == context.workspace_id,
                    WorkspaceMember.user_id == context.user_id,
                )
            )
            if user is None or workspace is None or membership is None:
                return None
            return AuthSessionView(
                user=_user_view(user),
                workspace=_workspace_view(workspace, membership.role),
            )


def _user_view(user: User) -> UserView:
    return UserView(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        created_at=user.created_at,
    )


def _workspace_view(workspace: Workspace, role: str) -> WorkspaceView:
    return WorkspaceView(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        role=role,
    )
