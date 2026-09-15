from collections.abc import Sequence
from pathlib import Path

import pytest

from app.agent.models import ChatMessage, LLMResponse, TokenUsage
from app.agent.nl2sql import NL2SQLService, NL2SQLStatus
from app.tools.definitions import ToolDefinition
from app.tools.duckdb_engine import DuckDBAnalyticsEngine


class ScriptedModel:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = responses
        self.calls: list[list[ChatMessage]] = []

    async def chat(
        self,
        *,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolDefinition],
    ) -> LLMResponse:
        self.calls.append(list(messages))
        return self._responses.pop(0)


def make_engine(tmp_path: Path) -> DuckDBAnalyticsEngine:
    csv_path = tmp_path / "sales.csv"
    csv_path.write_text(
        "region,amount\nEast,10\nWest,20\nEast,5\n",
        encoding="utf-8",
    )
    engine = DuckDBAnalyticsEngine()
    engine.register_csv("sales", csv_path)
    return engine


@pytest.mark.asyncio
async def test_nl2sql_retries_after_execution_error(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    model = ScriptedModel(
        [
            LLMResponse(content="SELECT missing_column FROM sales"),
            LLMResponse(content="SELECT SUM(amount) AS total FROM sales"),
        ]
    )
    service = NL2SQLService(model=model, engine=engine)

    try:
        result = await service.generate("销售额总计是多少？")
    finally:
        engine.close()

    assert result.status is NL2SQLStatus.SUCCESS
    assert result.attempts == 2
    assert result.query_result is not None
    assert result.query_result.rows == [{"total": 35}]
    assert "missing_column" in result.errors[0]
    assert "执行错误" in (model.calls[1][-1].content or "")


@pytest.mark.asyncio
async def test_nl2sql_stops_after_two_retries(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    model = ScriptedModel(
        [
            LLMResponse(content="DELETE FROM sales"),
            LLMResponse(content="DROP TABLE sales"),
            LLMResponse(content="INSERT INTO sales VALUES ('North', 1)"),
        ]
    )
    service = NL2SQLService(model=model, engine=engine)

    try:
        result = await service.generate("修改数据")
    finally:
        engine.close()

    assert result.status is NL2SQLStatus.FAILED
    assert result.attempts == 3
    assert len(result.errors) == 3


@pytest.mark.asyncio
async def test_nl2sql_classifies_empty_result_without_inventing_answer(
    tmp_path: Path,
) -> None:
    engine = make_engine(tmp_path)
    model = ScriptedModel(
        [
            LLMResponse(content="SELECT region, amount FROM sales WHERE amount < 0"),
            LLMResponse(
                content=(
                    '{"reason":"无数据","suggestion":"当前筛选条件下没有记录，请确认金额范围。"}'
                )
            ),
        ]
    )
    service = NL2SQLService(model=model, engine=engine)

    try:
        result = await service.generate("有没有负销售额？")
    finally:
        engine.close()

    assert result.status is NL2SQLStatus.EMPTY_RESULT
    assert result.reason is not None
    assert result.reason.value == "无数据"
    assert result.suggestion == "当前筛选条件下没有记录，请确认金额范围。"
    assert "不要编造答案" in (model.calls[1][-1].content or "")


@pytest.mark.asyncio
async def test_nl2sql_prompt_contains_schema_and_three_sample_rows(tmp_path: Path) -> None:
    engine = make_engine(tmp_path)
    model = ScriptedModel(
        [
            LLMResponse(
                content="SELECT SUM(amount) AS total FROM sales",
                usage=TokenUsage(input_tokens=5, output_tokens=2),
            ),
        ]
    )
    service = NL2SQLService(model=model, engine=engine)

    try:
        await service.generate("总销售额")
    finally:
        engine.close()

    initial_prompt = model.calls[0][1].content or ""
    assert '"name":"region"' in initial_prompt
    assert '"data_type":"BIGINT"' in initial_prompt
    assert initial_prompt.count('"East"') == 2
    assert '"West"' in initial_prompt
