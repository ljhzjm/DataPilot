# Agent 评测与安全回归

DataPilot 使用确定性评测模型验证 Agent 编排、工具选择和安全护栏。评测不依赖
外部模型 API，因此可以稳定运行在本地开发机和 CI 中。

## 执行方式

```powershell
Set-Location backend
uv run python -m app.evaluation
```

只运行某一类：

```powershell
uv run python -m app.evaluation --category guardrail
uv run python -m app.evaluation --category orchestration
```

输出完整 JSON 报告：

```powershell
uv run python -m app.evaluation --json
```

有任何用例失败时进程退出码为 `1`，可以直接用于 CI 回归门禁。

## 评测结构

```text
EvalScenario
  ├── 预置 LLMResponse 序列（SequenceModel）
  ├── 隔离的 ToolRegistry
  ├── 期望终止状态
  ├── 期望/禁止工具序列
  ├── 期望最终答案关键词
  └── 自定义安全检查
          │
          ▼
       Agent.run()
          │
          ▼
EvalCaseResult
  ├── pass/fail
  ├── 步骤数、工具调用数、失败工具数
  ├── Token 和耗时
  └── 逐项 EvalCheck
          │
          ▼
EvalReport + Summary
```

`SequenceModel` 每一步返回固定的 `LLMResponse`，因此测试的是 Agent 自身逻辑：

- 工具参数是否正确传入统一注册表；
- 工具结果是否正确回填到后续消息；
- 是否在重复调用、预算耗尽和最大步数时终止；
- 是否调用禁止工具或执行危险 SQL。

它不是模型质量评测，也不代替真实模型沙箱。真实模型回归可后续在此基础上接入
模型网关，但不应替代当前确定性安全门禁。

## 内置用例

| 用例 | 类型 | 验证内容 |
| --- | --- | --- |
| `sql_schema_then_query` | orchestration | 先读 Schema，再执行聚合 SQL |
| `sql_self_correction` | orchestration | SQL 报错后修正字段并重试 |
| `unsafe_sql_rejected` | guardrail | `DELETE` 在工具层被拒绝，未执行写操作 |
| `duplicate_tool_call_blocked` | guardrail | 语义相同的连续调用只执行一次并终止 |
| `token_budget_stops_execution` | guardrail | 超 Token 预算时停止即将执行的工具 |
| `max_steps_stops_agent` | guardrail | 达到最大步数后停止并保留轨迹 |
| `chart_spec_tool_selection` | orchestration | 图表需求选择 `plot_chart`，禁止 `run_python` 替代 |

## 指标

- `pass_rate`：全部用例通过率。
- `safety_pass_rate`：`guardrail` 类用例通过率。
- `failed_tool_calls`：预期有错误重试时用于检查失败路径确实发生。
- `total_tokens`：确定性响应中的累计 Token，用于检查预算逻辑。
- `average_duration_ms`：本地编排耗时，不包含真实模型网络延迟。

## 扩展新用例

在 `app/evaluation/scenarios.py` 中增加 `EvalScenario`：

1. 编写最小 `ToolRegistry`，只包含该用例需要的工具。
2. 编写固定 `LLMResponse` 序列。
3. 明确终止状态、工具序列和输出要求。
4. 安全边界必须增加自定义检查，不能只判断 `completed`。
5. 在 `tests/evaluation/test_evaluator.py` 中更新基线计数。
