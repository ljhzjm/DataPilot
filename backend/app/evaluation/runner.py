from collections.abc import Sequence
from time import perf_counter

from app.agent import Agent, AgentRunResult, ChatMessage, LLMResponse
from app.evaluation.models import (
    EvalCaseResult,
    EvalCategory,
    EvalCheck,
    EvalReport,
    EvalSummary,
)
from app.evaluation.scenarios import EvalEnvironment, EvalScenario, builtin_scenarios
from app.tools.definitions import ToolDefinition


class SequenceModel:
    """Deterministic model that returns a predeclared response for each Agent step."""

    def __init__(self, responses: Sequence[LLMResponse]) -> None:
        self._responses = list(responses)
        self._index = 0
        self.tool_names: tuple[str, ...] = ()

    async def chat(
        self,
        *,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition],
    ) -> LLMResponse:
        del messages
        self.tool_names = tuple(tool.function.name for tool in tools)
        if self._index >= len(self._responses):
            raise RuntimeError("Evaluation model has no scripted response left.")
        response = self._responses[self._index]
        self._index += 1
        return response


class AgentEvaluator:
    def __init__(
        self,
        scenarios: Sequence[EvalScenario] | None = None,
    ) -> None:
        self._scenarios = list(scenarios if scenarios is not None else builtin_scenarios())

    async def run(
        self,
        *,
        categories: set[EvalCategory] | None = None,
    ) -> EvalReport:
        scenarios = [
            scenario
            for scenario in self._scenarios
            if categories is None or scenario.category in categories
        ]
        results = [await self._run_scenario(scenario) for scenario in scenarios]
        return EvalReport(
            summary=_summarize(results),
            results=results,
        )

    async def _run_scenario(self, scenario: EvalScenario) -> EvalCaseResult:
        started = perf_counter()
        environment = scenario.build_environment()
        model = SequenceModel(scenario.build_responses())
        agent = Agent(
            model=model,
            tools=environment.registry,
            config=scenario.config,
        )

        try:
            result = await agent.run(scenario.description)
        except Exception as exc:
            return EvalCaseResult(
                case_id=scenario.case_id,
                category=scenario.category,
                description=scenario.description,
                passed=False,
                duration_ms=(perf_counter() - started) * 1000,
                step_count=0,
                tool_calls=0,
                failed_tool_calls=0,
                total_tokens=0,
                checks=[
                    EvalCheck(
                        name="agent_completed",
                        passed=False,
                        detail=f"{type(exc).__name__}: {exc}",
                    )
                ],
            )

        checks = _evaluate_checks(
            scenario,
            result,
            environment,
            available_tools=model.tool_names,
        )
        executions = [execution for step in result.steps for execution in step.tool_executions]
        return EvalCaseResult(
            case_id=scenario.case_id,
            category=scenario.category,
            description=scenario.description,
            passed=all(check.passed for check in checks),
            status=result.status,
            output=result.output,
            duration_ms=(perf_counter() - started) * 1000,
            step_count=len(result.steps),
            tool_calls=len(executions),
            failed_tool_calls=sum(1 for execution in executions if execution.error is not None),
            total_tokens=result.usage.total_tokens,
            checks=checks,
        )


def _evaluate_checks(
    scenario: EvalScenario,
    result: AgentRunResult,
    environment: EvalEnvironment,
    *,
    available_tools: tuple[str, ...],
) -> list[EvalCheck]:
    checks = [
        EvalCheck(
            name="available_tools",
            passed=all(tool_name in available_tools for tool_name in scenario.expected_tools),
            detail=(f"模型可见工具：{', '.join(available_tools) or '无'}。"),
        ),
        EvalCheck(
            name="terminal_status",
            passed=result.status == scenario.expected_status,
            detail=f"实际状态 {result.status}，期望状态 {scenario.expected_status}。",
        ),
    ]
    actual_tools = [call.name for step in result.steps for call in step.tool_calls]
    checks.append(
        EvalCheck(
            name="tool_sequence",
            passed=_is_subsequence(scenario.expected_tools, actual_tools),
            detail=f"实际工具序列：{actual_tools or ['无']}。",
        )
    )
    forbidden = [name for name in scenario.forbidden_tools if name in actual_tools]
    checks.append(
        EvalCheck(
            name="forbidden_tools",
            passed=not forbidden,
            detail=(
                "未调用禁止工具。" if not forbidden else f"调用了禁止工具：{', '.join(forbidden)}。"
            ),
        )
    )
    output = result.output or ""
    missing_terms = [term for term in scenario.required_output_terms if term not in output]
    checks.append(
        EvalCheck(
            name="required_output",
            passed=not missing_terms,
            detail=(
                "最终输出包含全部必要信息。"
                if not missing_terms
                else f"最终输出缺少：{', '.join(missing_terms)}。"
            ),
        )
    )
    failed_tool_calls = sum(
        1
        for step in result.steps
        for execution in step.tool_executions
        if execution.error is not None
    )
    if scenario.expected_failed_tool_calls is not None:
        checks.append(
            EvalCheck(
                name="failed_tool_calls",
                passed=failed_tool_calls == scenario.expected_failed_tool_calls,
                detail=(
                    f"失败工具调用 {failed_tool_calls} 次，"
                    f"期望 {scenario.expected_failed_tool_calls} 次。"
                ),
            )
        )
    checks.extend(check(result, environment) for check in scenario.custom_checks)
    return checks


def _is_subsequence(expected: Sequence[str], actual: Sequence[str]) -> bool:
    cursor = 0
    for name in actual:
        if cursor < len(expected) and name == expected[cursor]:
            cursor += 1
    return cursor == len(expected)


def _summarize(results: Sequence[EvalCaseResult]) -> EvalSummary:
    total_cases = len(results)
    passed_cases = sum(1 for result in results if result.passed)
    failed_cases = total_cases - passed_cases
    safety_results = [result for result in results if result.category == "guardrail"]
    safety_passed = sum(1 for result in safety_results if result.passed)
    total_tokens = sum(result.total_tokens for result in results)
    total_tool_calls = sum(result.tool_calls for result in results)
    failed_tool_calls = sum(result.failed_tool_calls for result in results)
    average_duration_ms = (
        sum(result.duration_ms for result in results) / total_cases if total_cases else 0
    )
    return EvalSummary(
        total_cases=total_cases,
        passed_cases=passed_cases,
        failed_cases=failed_cases,
        pass_rate=passed_cases / total_cases if total_cases else 1,
        safety_pass_rate=(safety_passed / len(safety_results) if safety_results else 1),
        total_tokens=total_tokens,
        total_tool_calls=total_tool_calls,
        failed_tool_calls=failed_tool_calls,
        average_duration_ms=average_duration_ms,
    )


__all__ = [
    "AgentEvaluator",
    "EvalCategory",
    "SequenceModel",
    "builtin_scenarios",
]
