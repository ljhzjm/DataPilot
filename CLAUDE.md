# DataPilot 项目规则

本文件是本项目所有开发工作的最高优先级工程约束。进入 `backend/` 或 `frontend/` 前，还必须阅读对应目录下的 `CLAUDE.md`。

## 项目目标

DataPilot 是对话式数据分析智能体：用户上传 CSV/Excel 或连接只读数据库，用自然语言提问；自实现的 Agent 循环自主选择 SQL、Python 和图表工具，系统返回分析结果、表格或图表，并完整展示执行轨迹。

项目重点不是简单调用大模型，而是 Agent 编排、工具调用、安全执行、过程可观测、评测和工程化。

## 固定技术栈

- 前端：Vue 3.5+、TypeScript、Vite、Pinia、Vue Router、Element Plus、ECharts。
- 后端：Python 3.11、FastAPI、Pydantic v2、SQLAlchemy 2.0、uv。
- 业务数据：PostgreSQL 16，保存会话、消息、步骤、文件元数据、成本和评测记录。
- 分析引擎：DuckDB，查询 CSV、Parquet 和分析型外部数据；不得替代 PostgreSQL 业务存储。
- 缓存与任务：Redis。
- 模型接入：所有供应商统一经过 `app/llm/` 网关，不硬编码供应商 SDK。
- 部署：Docker Compose。

## 强制禁止事项

1. 模型生成的所有 SQL/Python 代码一律视为不可信输入，必须经过对应安全校验；Python 必须在沙箱中执行，禁止在 FastAPI、Celery 或本地开发主进程中直接执行。
2. SQL 只允许 SELECT。禁止 INSERT、UPDATE、DELETE、DROP、ALTER、CREATE、TRUNCATE、GRANT 等写操作；外部数据库连接必须使用只读账号，并开启只读事务。
3. Agent 循环必须自实现，禁止引入 LangChain Agent、LlamaIndex Agent 或其他框架的 Agent 循环替代核心编排逻辑。
4. 单次生成超过 300 行代码或 SQL 时必须先停止并请求人工 review，不得继续执行。
5. 禁止把密钥、Token 或数据库密码写入源码；只提交 `.env.example`。
6. 禁止把模型输出直接传给 shell、文件系统、数据库或 Docker API；所有参数必须先做类型、范围、白名单和路径校验。
7. 禁止把任意代码输入当作可信工具结果；工具结果进入模型前必须做长度截断和敏感信息过滤。
8. 禁止删除或弱化安全测试、超时限制、资源限制和只读约束来让功能“先跑起来”。

## 架构边界

- `backend/app/api/`：HTTP/SSE 接口，只做参数校验、鉴权、编排入口和响应转换。
- `backend/app/agent/`：自实现 Agent 循环、上下文、护栏、执行状态和轨迹事件。
- `backend/app/tools/`：工具定义、注册表、参数模型和执行适配器。
- `backend/app/sandbox/`：Docker 沙箱生命周期与统一执行接口。
- `backend/app/llm/`：模型供应商适配、路由、重试、成本记录。
- `backend/app/db/`：PostgreSQL 模型与会话管理。
- `frontend/src/`：Vue 页面、组件、状态、API 与 SSE 客户端。
- `sandbox/`：不可信代码运行镜像，只包含白名单分析依赖。

## 工程约定

- 后端使用 `ruff`、`mypy`、`pytest`；前端使用 ESLint、Prettier、Vitest。
- 功能改动必须附带可运行测试；涉及安全边界时必须同时提供拒绝路径测试。
- 所有外部输入、工具参数和工具输出使用明确的 Pydantic 模型。
- 新增抽象必须解决真实复杂度，不为“以后可能需要”预建空框架。
- 任何实现都不能改变本文档定义的安全边界；需要变更时必须先说明原因和替代风险。
- 每个阶段完成后必须提供“需要你实际操作”清单，明确区分：
  - 必须由用户执行的步骤；
  - 可选验证或体验步骤；
  - 已由开发流程自动完成、无需用户重复操作的步骤；
  - 因当前阶段尚未实现而暂时不需要操作的步骤。
- 不得只给出笼统结论；涉及 Docker、数据库、模型密钥、浏览器、部署平台、
  第三方账号、数据上传或人工安全评审时，必须指出具体操作位置和预期结果。
