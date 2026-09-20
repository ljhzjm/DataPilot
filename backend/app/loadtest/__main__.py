import argparse
import asyncio
from collections.abc import Sequence

from app.loadtest.runner import LoadTestConfig, run_load_test


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run an HTTP load test against DataPilot.",
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:18000/api/health/ready",
    )
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--authorization", default=None)
    parser.add_argument("--cookie", default=None)
    parser.add_argument("--max-p95-ms", type=float, default=1000)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = asyncio.run(
        run_load_test(
            LoadTestConfig(
                url=args.url,
                requests=args.requests,
                concurrency=args.concurrency,
                timeout_seconds=args.timeout,
                authorization=args.authorization,
                cookie=args.cookie,
            )
        )
    )
    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        print(f"URL: {report.url}")
        print(
            f"Requests: {report.requests}, success={report.success_count}, "
            f"errors={report.error_count}, error_rate={report.error_rate:.2%}"
        )
        print(
            f"RPS: {report.requests_per_second:.2f}, "
            f"avg={report.average_ms:.1f}ms, p50={report.p50_ms:.1f}ms, "
            f"p95={report.p95_ms:.1f}ms, p99={report.p99_ms:.1f}ms"
        )
        print(f"Statuses: {report.status_counts}")
    passed = report.error_rate <= args.max_error_rate and report.p95_ms <= args.max_p95_ms
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
