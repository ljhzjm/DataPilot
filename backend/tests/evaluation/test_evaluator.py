import json
from dataclasses import replace

import pytest

from app.evaluation import AgentEvaluator, builtin_scenarios
from app.evaluation.__main__ import main


@pytest.mark.asyncio
async def test_builtin_evaluation_baseline_passes() -> None:
    report = await AgentEvaluator().run()

    assert report.summary.total_cases == 7
    assert report.summary.passed_cases == 7
    assert report.summary.failed_cases == 0
    assert report.summary.pass_rate == 1
    assert report.summary.safety_pass_rate == 1
    assert report.summary.failed_tool_calls == 2
    assert report.summary.total_tool_calls == 9


@pytest.mark.asyncio
async def test_evaluation_fails_when_expected_tool_is_missing() -> None:
    scenario = replace(
        builtin_scenarios()[0],
        expected_tools=("tool_that_does_not_exist",),
    )

    report = await AgentEvaluator([scenario]).run()

    assert report.summary.failed_cases == 1
    failed_checks = {check.name for check in report.results[0].checks if not check.passed}
    assert failed_checks == {"available_tools", "tool_sequence"}


def test_evaluation_cli_emits_json_report(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--json", "--category", "guardrail"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["summary"]["total_cases"] == 4
    assert payload["summary"]["safety_pass_rate"] == 1
