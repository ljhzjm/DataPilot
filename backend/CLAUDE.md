# DataPilot Backend Rules

先阅读并遵守仓库根目录 `CLAUDE.md`。本文件只补充后端实现约定。

## 技术约束

- Python 3.11。
- FastAPI + Pydantic v2。
- SQLAlchemy 2.0 + PostgreSQL。
- Redis 用于缓存、短期状态和任务协调。
- DuckDB 只作为分析查询引擎。
- 依赖由 `uv` 管理，提交 `pyproject.toml` 和 `uv.lock`。

## 目录职责

- `app/api/`：路由、请求响应模型、依赖注入，不写 Agent 业务逻辑。
- `app/agent/`：自实现循环、状态机、护栏和轨迹。
- `app/tools/`：工具注册表、参数模型、本地工具实现。
- `app/sandbox/`：沙箱容器管理和统一 `execute()` 接口。
- `app/llm/`：模型网关，禁止路由层直接调用供应商。
- `app/db/`：数据库连接、ORM 模型和迁移支持。
- `app/core/`：配置、日志和通用基础设施。
- `tests/`：单元测试与安全拒绝路径测试。

## 代码规范

- 使用完整类型标注和 Pydantic v2。
- 使用 `ruff format`、`ruff check` 和 `mypy`。
- 使用绝对导入，例如 `from app.core.config import get_settings`。
- 禁止吞掉异常；工具错误必须转换为结构化结果并记录安全上下文。
- 外部 I/O 必须有超时、重试边界和资源上限。

## 测试约定

- 使用 `pytest` 和 `pytest-asyncio`。
- 工具循环使用 mock LLM，不依赖真实模型。
- 沙箱测试必须覆盖超时、越权 SQL、网络隔离和资源限制。
- 每次改动至少提供正常路径与失败路径测试。

## 后端禁止事项

- 不允许在 API 进程、Celery worker 或测试辅助代码中执行模型生成的 Python。
- 不允许通过字符串拼接绕过 SQL AST/语法校验或表白名单。
- 不允许接受沙箱容器的任意镜像、挂载路径、环境变量或特权参数。
- 不允许硬编码模型供应商、模型名、密钥或 Token。
- 不允许让超过 300 行的单次生成直接进入执行流程。

