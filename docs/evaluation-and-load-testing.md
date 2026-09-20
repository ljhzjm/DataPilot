# 评测与压测

DataPilot 提供两级 Agent 评测和一套无额外依赖的 HTTP 压测工具。

## 确定性评测

默认评测使用固定 `LLMResponse`，不访问外部模型：

```powershell
Set-Location backend
uv run python -m app.evaluation
```

覆盖内容：

- Schema 读取与 SQL 工具选择；
- SQL 自纠错；
- 危险 SQL 拒绝；
- 重复调用终止；
- Token 预算；
- 最大步数；
- 图表工具选择。

JSON 报告：

```powershell
uv run python -m app.evaluation --json
```

## 真实模型评测

真实模型评测使用当前 `LLM_*` 配置，调用三个独立场景，验证模型是否选择正确工具并遵守
写操作拒绝规则：

```powershell
uv run python -m app.evaluation --live
```

未配置 `LLM_API_KEY` 时退出码为 `2`，不会发起网络请求。真实模型评测结果受模型能力、
供应商状态和 Prompt 变化影响，因此不应替代确定性安全回归。

## HTTP 压测

默认对就绪检查执行 100 个请求、并发 10：

```powershell
uv run python -m app.loadtest
```

常用参数：

```powershell
uv run python -m app.loadtest `
  --url http://127.0.0.1:18000/api/health/ready `
  --requests 500 `
  --concurrency 25 `
  --max-p95-ms 500 `
  --max-error-rate 0
```

访问受保护接口时传入 Cookie 或 Bearer Token：

```powershell
uv run python -m app.loadtest `
  --url http://127.0.0.1:18000/api/conversations `
  --cookie "datapilot_session=<session-token>"
```

报告包含 RPS、平均延迟、P50、P95、P99、错误率和状态码分布。P95 或错误率超过阈值时
进程退出码为 `1`，可接入后续 CI 流水线。
