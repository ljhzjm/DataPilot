from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.tools.registry import RegisteredTool, tool

ChartType = Literal["line", "bar", "area", "pie", "scatter"]


class ChartSpec(BaseModel):
    chart_type: ChartType = Field(alias="type")
    title: str = Field(min_length=1, max_length=120)
    x_field: str = Field(min_length=1, max_length=128)
    y_fields: list[str] = Field(min_length=1, max_length=5)
    data: list[dict[str, Any]] = Field(min_length=1, max_length=1000)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def validate_chart_shape(self) -> "ChartSpec":
        if len(set(self.y_fields)) != len(self.y_fields):
            raise ValueError("y_fields must be unique.")

        if self.chart_type == "pie" and len(self.y_fields) != 1:
            raise ValueError("Pie charts require exactly one y field.")
        if self.chart_type == "scatter" and len(self.y_fields) != 1:
            raise ValueError("Scatter charts require exactly one y field.")

        required_fields = {self.x_field, *self.y_fields}
        for row_index, row in enumerate(self.data):
            missing = required_fields.difference(row)
            if missing:
                raise ValueError(f"Chart data row {row_index} is missing fields: {sorted(missing)}")
            for field_name in self.y_fields:
                value = row[field_name]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"Chart field '{field_name}' must contain numeric values.")
        return self


class ChartArtifact(BaseModel):
    kind: Literal["chart"] = "chart"
    spec: ChartSpec


def build_plot_chart_tool() -> RegisteredTool:
    @tool(
        name="plot_chart",
        description=(
            "做什么：校验并生成前端 ECharts 可直接渲染的图表配置。"
            "何时使用：SQL 或 Python 分析已经产生可用于可视化的结构化数据，"
            "且用户需要柱状图、折线图、面积图、饼图或散点图时使用。"
            "参数 spec：包含 type、title、x_field、y_fields 和 data；"
            "data 中每一行必须包含 x_field 和全部 y_fields，y 值必须为数字。"
            '示例：{"spec":{"type":"bar","title":"区域销售额",'
            '"x_field":"region","y_fields":["total"],'
            '"data":[{"region":"East","total":120}]}}。'
        ),
        parallel_safe=True,
    )
    async def plot_chart(spec: ChartSpec) -> dict[str, Any]:
        artifact = ChartArtifact(spec=spec)
        return artifact.model_dump(mode="json", by_alias=True)

    return plot_chart


__all__ = ["ChartArtifact", "ChartSpec", "ChartType", "build_plot_chart_tool"]
