import pytest

from app.agent import LLMResponse, ToolCall
from app.evaluation.live import _run_live_case, live_scenarios
from app.evaluation.runner import SequenceModel


@pytest.mark.asyncio
async def test_live_evaluation_case_accepts_expected_tool_trajectory() -> None:
    scenario = live_scenarios()[0]
    model = SequenceModel(
        [
            LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="schema",
                        name="get_schema",
                        arguments={"table_name": "sales"},
                    )
                ]
            ),
            LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="query",
                        name="run_sql",
                        arguments={"sql": "SELECT region, amount FROM sales ORDER BY region"},
                    )
                ]
            ),
            LLMResponse(content="East 15，West 20。"),
        ]
    )

    result = await _run_live_case(model, scenario)

    assert result.passed is True
    assert result.status == "completed"
