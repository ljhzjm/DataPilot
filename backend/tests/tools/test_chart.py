import pytest
from pydantic import ValidationError

from app.tools.chart import ChartSpec, build_plot_chart_tool


@pytest.mark.asyncio
async def test_plot_chart_returns_validated_echarts_payload() -> None:
    plot_chart = build_plot_chart_tool()

    result = await plot_chart.invoke(
        {
            "spec": {
                "type": "bar",
                "title": "区域销售额",
                "x_field": "region",
                "y_fields": ["total"],
                "data": [
                    {"region": "East", "total": 120},
                    {"region": "West", "total": 80},
                ],
            }
        }
    )

    assert result["kind"] == "chart"
    assert result["spec"]["type"] == "bar"
    assert result["spec"]["data"][0]["total"] == 120


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "spec",
    [
        {
            "type": "radar",
            "title": "非法图表",
            "x_field": "region",
            "y_fields": ["total"],
            "data": [{"region": "East", "total": 120}],
        },
        {
            "type": "pie",
            "title": "饼图只能有一个指标",
            "x_field": "region",
            "y_fields": ["total", "profit"],
            "data": [{"region": "East", "total": 120, "profit": 20}],
        },
        {
            "type": "line",
            "title": "缺少数据字段",
            "x_field": "month",
            "y_fields": ["sales"],
            "data": [{"month": "2026-01"}],
        },
        {
            "type": "bar",
            "title": "禁止代码字段",
            "x_field": "region",
            "y_fields": ["total"],
            "data": [{"region": "East", "total": 120}],
            "matplotlib_code": "import matplotlib.pyplot as plt",
        },
    ],
)
async def test_plot_chart_rejects_invalid_spec(spec: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ChartSpec.model_validate(spec)
