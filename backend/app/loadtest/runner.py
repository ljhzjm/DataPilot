import asyncio
import math
from dataclasses import dataclass
from time import perf_counter

import httpx
from pydantic import BaseModel, Field


class LoadTestConfig(BaseModel):
    url: str
    requests: int = Field(default=100, ge=1, le=100_000)
    concurrency: int = Field(default=10, ge=1, le=1000)
    timeout_seconds: float = Field(default=10, gt=0, le=120)
    authorization: str | None = None
    cookie: str | None = None


class LoadTestReport(BaseModel):
    url: str
    requests: int = Field(ge=0)
    success_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    error_rate: float = Field(ge=0, le=1)
    requests_per_second: float = Field(ge=0)
    average_ms: float = Field(ge=0)
    p50_ms: float = Field(ge=0)
    p95_ms: float = Field(ge=0)
    p99_ms: float = Field(ge=0)
    status_counts: dict[str, int] = Field(default_factory=dict)


@dataclass(slots=True)
class _Sample:
    status_code: int
    duration_ms: float
    error: str | None = None


async def run_load_test(config: LoadTestConfig) -> LoadTestReport:
    headers: dict[str, str] = {}
    if config.authorization:
        headers["Authorization"] = config.authorization
    if config.cookie:
        headers["Cookie"] = config.cookie

    queue: asyncio.Queue[int] = asyncio.Queue()
    for index in range(config.requests):
        queue.put_nowait(index)
    samples: list[_Sample] = []
    lock = asyncio.Lock()
    started = perf_counter()

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(config.timeout_seconds),
        follow_redirects=False,
    ) as client:

        async def worker() -> None:
            while True:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                sample_started = perf_counter()
                status_code = 0
                error: str | None = None
                try:
                    response = await client.get(config.url, headers=headers)
                    status_code = response.status_code
                except httpx.HTTPError as exc:
                    error = type(exc).__name__
                duration_ms = (perf_counter() - sample_started) * 1000
                async with lock:
                    samples.append(
                        _Sample(
                            status_code=status_code,
                            duration_ms=duration_ms,
                            error=error,
                        )
                    )

        await asyncio.gather(*(worker() for _ in range(config.concurrency)))

    elapsed = max(perf_counter() - started, 1e-9)
    durations = sorted(sample.duration_ms for sample in samples)
    success_count = sum(
        1 for sample in samples if sample.error is None and 200 <= sample.status_code < 400
    )
    error_count = len(samples) - success_count
    status_counts: dict[str, int] = {}
    for sample in samples:
        key = str(sample.status_code) if sample.error is None else f"error:{sample.error}"
        status_counts[key] = status_counts.get(key, 0) + 1

    return LoadTestReport(
        url=config.url,
        requests=len(samples),
        success_count=success_count,
        error_count=error_count,
        error_rate=error_count / len(samples) if samples else 0,
        requests_per_second=len(samples) / elapsed,
        average_ms=sum(durations) / len(durations) if durations else 0,
        p50_ms=_percentile(durations, 0.50),
        p95_ms=_percentile(durations, 0.95),
        p99_ms=_percentile(durations, 0.99),
        status_counts=status_counts,
    )


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if not sorted_values:
        return 0
    index = max(0, math.ceil(percentile * len(sorted_values)) - 1)
    return sorted_values[index]
