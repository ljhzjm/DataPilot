from uuid import uuid4

import pytest

from app.auth.middleware import _extract_token, _is_public
from app.auth.rate_limit import RateLimiter


class FakeRateLimitStore:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> bool:
        del key, seconds
        return True

    async def ttl(self, key: str) -> int:
        del key
        return 60


@pytest.mark.asyncio
async def test_rate_limiter_rejects_requests_above_limit() -> None:
    limiter = RateLimiter(FakeRateLimitStore())

    first = await limiter.check(key="workspace:test", limit=2, window_seconds=60)
    second = await limiter.check(key="workspace:test", limit=2, window_seconds=60)
    third = await limiter.check(key="workspace:test", limit=2, window_seconds=60)

    assert first.allowed is True
    assert first.remaining == 1
    assert second.allowed is True
    assert second.remaining == 0
    assert third.allowed is False


def test_auth_public_paths_and_bearer_token_extraction() -> None:
    assert _is_public("/api/health/ready") is True
    assert _is_public("/api/auth/login") is True
    assert _is_public("/api/conversations") is False

    workspace_id = uuid4()
    scope = {
        "headers": [
            (b"authorization", b"Bearer test-token"),
            (
                b"cookie",
                f"datapilot_session=cookie-token; workspace={workspace_id}".encode(),
            ),
        ]
    }
    assert _extract_token(scope, "datapilot_session") == "test-token"
