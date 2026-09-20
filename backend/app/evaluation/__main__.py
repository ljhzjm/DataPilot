import argparse
import asyncio
from collections.abc import Sequence

from app.evaluation.live import run_live_evaluation
from app.evaluation.models import EvalReport
from app.evaluation.runner import AgentEvaluator


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run DataPilot deterministic Agent evaluation.",
    )
    parser.add_argument(
        "--category",
        action="append",
        choices=["orchestration", "guardrail"],
        help="Only run the selected category. Can be provided multiple times.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the complete JSON report.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run the optional real-model evaluation suite.",
    )
    args = parser.parse_args(argv)

    if args.live:
        try:
            report = asyncio.run(run_live_evaluation())
        except RuntimeError as exc:
            print(f"Live evaluation unavailable: {exc}")
            return 2
    else:
        categories = {category for category in args.category} if args.category else None
        report = asyncio.run(AgentEvaluator().run(categories=categories))
    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        _print_report(report)
    return 0 if report.summary.failed_cases == 0 else 1


def _print_report(report: EvalReport) -> None:
    print("DataPilot Agent Evaluation")
    print("")
    for result in report.results:
        marker = "PASS" if result.passed else "FAIL"
        print(
            f"{marker} {result.case_id}: "
            f"status={result.status}, steps={result.step_count}, "
            f"tools={result.tool_calls}, tokens={result.total_tokens}, "
            f"latency={result.duration_ms:.1f}ms"
        )
        for check in result.checks:
            if not check.passed:
                print(f"  - {check.name}: {check.detail}")
    summary = report.summary
    print("")
    print(
        "Summary: "
        f"{summary.passed_cases}/{summary.total_cases} passed, "
        f"pass_rate={summary.pass_rate:.1%}, "
        f"safety_pass_rate={summary.safety_pass_rate:.1%}, "
        f"tokens={summary.total_tokens}, "
        f"avg_latency={summary.average_duration_ms:.1f}ms"
    )


if __name__ == "__main__":
    raise SystemExit(main())
