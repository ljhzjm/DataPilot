from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.agent import AgentConfig, AgentRunResult, LLMResponse, TokenUsage, ToolCall
from app.evaluation.models import EvalCategory, EvalCheck
from app.tools.registry import ToolRegistry, tool


@dataclass(slots=True)
class EvalEnvironment:
    registry: ToolRegistry
    state: dict[str, Any] = field(default_factory=dict)


EvalEnvironmentFactory = Callable[[], EvalEnvironment]
EvalResponsesFactory = Callable[[], list[LLMResponse]]
EvalCheckFunction = Callable[[AgentRunResult, EvalEnvironment], EvalCheck]


@dataclass(frozen=True, slots=True)
class EvalScenario:
    case_id: str
    category: EvalCategory
    description: str
    config: AgentConfig
    build_environment: EvalEnvironmentFactory
    build_responses: EvalResponsesFactory
    expected_status: str
    expected_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    required_output_terms: tuple[str, ...] = ()
    expected_failed_tool_calls: int | None = None
    custom_checks: tuple[EvalCheckFunction, ...] = ()


def builtin_scenarios() -> list[EvalScenario]:
    return [
        EvalScenario(
            case_id="sql_schema_then_query",
            category="orchestration",
            description="先读取 Schema，再执行聚合 SQL，并返回结果。",
            config=_config(max_steps=4),
            build_environment=_analytics_environment,
            build_responses=lambda: [
                _tool_response(
                    "schema-call",
                    "get_schema",
                    {"table_name": "sales"},
                ),
                _tool_response(
                    "query-call",
                    "run_sql",
                    {
                        "sql": (
                            "SELECT region, SUM(amount) AS total "
                            "FROM sales GROUP BY region ORDER BY region"
                        )
                    },
                ),
                _final_response("East 15，West 20。"),
            ],
            expected_status="completed",
            expected_tools=("get_schema", "run_sql"),
            required_output_terms=("East 15", "West 20"),
            expected_failed_tool_calls=0,
        ),
        EvalScenario(
            case_id="sql_self_correction",
            category="orchestration",
            description="首次 SQL 字段错误后，根据工具错误重新生成正确 SQL。",
            config=_config(max_steps=5),
            build_environment=_analytics_environment,
            build_responses=lambda: [
                _tool_response(
                    "bad-query",
                    "run_sql",
                    {"sql": "SELECT missing_column FROM sales"},
                ),
                _tool_response(
                    "fixed-query",
                    "run_sql",
                    {"sql": "SELECT region, amount FROM sales ORDER BY amount"},
                ),
                _final_response("已修正字段并完成查询。"),
            ],
            expected_status="completed",
            expected_tools=("run_sql", "run_sql"),
            required_output_terms=("已修正",),
            expected_failed_tool_calls=1,
        ),
        EvalScenario(
            case_id="unsafe_sql_rejected",
            category="guardrail",
            description="DELETE 写操作必须被工具拒绝，Agent 不得执行写 SQL。",
            config=_config(max_steps=4),
            build_environment=_analytics_environment,
            build_responses=lambda: [
                _tool_response(
                    "delete-query",
                    "run_sql",
                    {"sql": "DELETE FROM sales"},
                ),
                _final_response("写操作已被安全策略拒绝。"),
            ],
            expected_status="completed",
            expected_tools=("run_sql",),
            required_output_terms=("写操作", "拒绝"),
            expected_failed_tool_calls=1,
            custom_checks=(_check_no_write_executed,),
        ),
        EvalScenario(
            case_id="duplicate_tool_call_blocked",
            category="guardrail",
            description="连续提交相同工具调用时立即终止，避免无限循环。",
            config=_config(max_steps=5),
            build_environment=_analytics_environment,
            build_responses=lambda: [
                _tool_response(
                    "same-query-1",
                    "run_sql",
                    {"sql": "SELECT region, amount FROM sales"},
                ),
                _tool_response(
                    "same-query-2",
                    "run_sql",
                    {"sql": " select  region, amount from sales "},
                ),
            ],
            expected_status="loop_detected",
            expected_tools=("run_sql",),
            expected_failed_tool_calls=0,
            custom_checks=(_check_duplicate_executed_once,),
        ),
        EvalScenario(
            case_id="token_budget_stops_execution",
            category="guardrail",
            description="模型响应超过 Token 预算时，停止执行尚未运行的工具。",
            config=_config(max_steps=4, max_total_tokens=10),
            build_environment=_analytics_environment,
            build_responses=lambda: [
                _tool_response(
                    "expensive-call",
                    "run_sql",
                    {"sql": "SELECT region, amount FROM sales"},
                    usage=TokenUsage(input_tokens=8, output_tokens=3),
                )
            ],
            expected_status="token_budget_exceeded",
            expected_tools=(),
            expected_failed_tool_calls=0,
            custom_checks=(_check_no_tool_executed,),
        ),
        EvalScenario(
            case_id="max_steps_stops_agent",
            category="guardrail",
            description="达到最大步数后停止，并保留实际执行过的步骤。",
            config=_config(max_steps=2),
            build_environment=_analytics_environment,
            build_responses=lambda: [
                _tool_response(
                    "step-1",
                    "run_sql",
                    {"sql": "SELECT region FROM sales"},
                ),
                _tool_response(
                    "step-2",
                    "run_sql",
                    {"sql": "SELECT amount FROM sales"},
                ),
                _tool_response(
                    "step-3",
                    "run_sql",
                    {"sql": "SELECT quantity FROM sales"},
                ),
            ],
            expected_status="max_steps",
            expected_tools=("run_sql", "run_sql"),
            expected_failed_tool_calls=0,
            custom_checks=(_check_two_tool_executions,),
        ),
        EvalScenario(
            case_id="chart_spec_tool_selection",
            category="orchestration",
            description="结构化图表需求选择 plot_chart，不生成绘图代码。",
            config=_config(max_steps=3),
            build_environment=_analytics_environment,
            build_responses=lambda: [
                _tool_response(
                    "chart-call",
                    "plot_chart",
                    {
                        "spec": {
                            "type": "bar",
                            "title": "区域销售额",
                            "x_field": "region",
                            "y_fields": ["total"],
                            "data": [
                                {"region": "East", "total": 15},
                                {"region": "West", "total": 20},
                            ],
                        }
                    },
                ),
                _final_response("图表已生成。"),
            ],
            expected_status="completed",
            expected_tools=("plot_chart",),
            forbidden_tools=("run_python",),
            required_output_terms=("图表",),
            expected_failed_tool_calls=0,
        ),
    ]


def _config(
    *,
    max_steps: int,
    max_total_tokens: int = 1000,
) -> AgentConfig:
    return AgentConfig(
        max_steps=max_steps,
        max_total_tokens=max_total_tokens,
        stream_model=False,
        parallel_tool_calls=False,
    )


def _tool_response(
    call_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    usage: TokenUsage | None = None,
) -> LLMResponse:
    return LLMResponse(
        tool_calls=[
            ToolCall(
                id=call_id,
                name=tool_name,
                arguments=arguments,
            )
        ],
        usage=usage or TokenUsage(input_tokens=10, output_tokens=2),
        finish_reason="tool_calls",
    )


def _final_response(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        usage=TokenUsage(input_tokens=10, output_tokens=4),
        finish_reason="stop",
    )


def _analytics_environment() -> EvalEnvironment:
    state: dict[str, Any] = {
        "executed_sql": [],
        "write_attempted": False,
    }
    registry = ToolRegistry()

    @tool(
        name="get_schema",
        description=(
            "做什么：读取测试销售表的字段。"
            "何时使用：生成 SQL 前。"
            "参数 table_name：表名。"
            '示例：{"table_name":"sales"}。'
        ),
    )
    async def get_schema(table_name: str) -> dict[str, Any]:
        return {
            "table_name": table_name,
            "columns": [
                {"name": "region", "data_type": "VARCHAR"},
                {"name": "amount", "data_type": "BIGINT"},
            ],
        }

    @tool(
        name="run_sql",
        description=(
            "做什么：执行评测用只读 SQL。"
            "何时使用：需要聚合或筛选测试数据时。"
            "参数 sql：只读 SELECT。"
            '示例：{"sql":"SELECT region, amount FROM sales"}。'
        ),
    )
    async def run_sql(sql: str) -> dict[str, Any]:
        normalized = " ".join(sql.strip().split())
        state["executed_sql"].append(normalized)
        if not normalized.upper().startswith("SELECT"):
            state["write_attempted"] = True
            raise ValueError("Only SELECT statements are allowed.")
        if "missing_column" in normalized:
            raise RuntimeError("Binder Error: column missing_column does not exist.")
        return {
            "columns": ["region", "amount"],
            "rows": [
                {"region": "East", "amount": 15},
                {"region": "West", "amount": 20},
            ],
            "row_count": 2,
            "truncated": False,
        }

    @tool(
        name="plot_chart",
        description=(
            "做什么：校验并返回结构化图表 Spec。"
            "何时使用：用户要求图表时。"
            "参数 spec：图表类型、字段和数据。"
            '示例：{"spec":{"type":"bar","title":"销售","x_field":"region",'
            '"y_fields":["amount"],"data":[{"region":"East","amount":15}]}}。'
        ),
    )
    async def plot_chart(spec: dict[str, Any]) -> dict[str, Any]:
        return {"kind": "chart", "spec": spec}

    registry.register(get_schema)
    registry.register(run_sql)
    registry.register(plot_chart)
    return EvalEnvironment(registry=registry, state=state)


def _check_no_write_executed(
    result: AgentRunResult,
    environment: EvalEnvironment,
) -> EvalCheck:
    del result
    passed = environment.state.get("write_attempted") is True
    return EvalCheck(
        name="write_sql_never_executed",
        passed=passed,
        detail=("写 SQL 在策略层被拒绝。" if passed else "未观察到写 SQL 的拒绝路径。"),
    )


def _check_duplicate_executed_once(
    result: AgentRunResult,
    environment: EvalEnvironment,
) -> EvalCheck:
    del result
    calls = environment.state.get("executed_sql")
    count = len(calls) if isinstance(calls, list) else 0
    return EvalCheck(
        name="duplicate_executed_once",
        passed=count == 1,
        detail=f"重复工具只执行了 {count} 次。",
    )


def _check_no_tool_executed(
    result: AgentRunResult,
    environment: EvalEnvironment,
) -> EvalCheck:
    del result
    calls = environment.state.get("executed_sql")
    count = len(calls) if isinstance(calls, list) else 0
    return EvalCheck(
        name="budget_prevents_tool_execution",
        passed=count == 0,
        detail=f"预算终止前执行了 {count} 个工具。",
    )


def _check_two_tool_executions(
    result: AgentRunResult,
    environment: EvalEnvironment,
) -> EvalCheck:
    del result
    calls = environment.state.get("executed_sql")
    count = len(calls) if isinstance(calls, list) else 0
    return EvalCheck(
        name="max_steps_preserves_two_executions",
        passed=count == 2,
        detail=f"最大步数内执行了 {count} 个工具。",
    )
