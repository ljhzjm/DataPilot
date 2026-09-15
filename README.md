# DataPilot

DataPilot 是一个对话式数据分析智能体。当前仓库已完成工程初始化、自实现 Agent 工具调用循环、工具注册表、NL2SQL 自纠错、结构化图表工具、DuckDB 只读查询、安全 SQL 护栏和独立 Docker Python 沙箱；前端执行轨迹将在后续阶段接入。

## 技术栈

- 前端：Vue 3、TypeScript、Vite、Pinia、Vue Router、Element Plus
- 后端：Python 3.11、FastAPI、SQLAlchemy 2.0、uv
- 数据：PostgreSQL 16 + pgvector、Redis、DuckDB
- 安全执行：独立 Docker 沙箱镜像
- 部署：Docker Compose

## 一键启动

前提：

- Docker Desktop 已启动，并允许当前用户使用 Docker。
- 本地运行前端时需要 Node.js 20.19 或更高版本；仅使用 Docker 时以容器内 Node 版本为准。

```powershell
Copy-Item .env.example .env
docker compose --profile sandbox up -d --build
```

启动后可访问：

- 前端：http://localhost:18080
- 后端接口文档：http://localhost:18000/docs
- 存活检查：http://localhost:18000/api/health/live
- 就绪检查：http://localhost:18000/api/health/ready

查看服务状态：

```powershell
docker compose ps
```

Compose 会先运行独立的 `migrate` 服务执行 `alembic upgrade head`，迁移成功后
才启动后端。现有数据库会自动登记为初始迁移版本，不会重复建表。

停止服务：

```powershell
docker compose --profile sandbox down
```

沙箱服务使用独立 profile。它不会获得业务网络，根文件系统只读，并限制为 512 MB 内存、64 个进程和 1 个 CPU。后端通过 Docker Socket 基于该镜像按任务启动临时容器，而不是在 FastAPI 进程内执行模型生成的代码。

## 当前 Agent 能力

- LLM 工具调用循环，不依赖框架 Agent。
- 并发或串行执行工具调用，并将结果回填消息。
- `@tool` 装饰器根据函数签名和 Pydantic 字段生成 JSON Schema。
- `list_tables`、`get_schema`、`run_sql` 三个初始工具。
- NL2SQL Prompt 注入表结构、字段类型和前 3 行样例。
- SQL 失败自动回填错误并最多重试 2 次。
- 空结果由模型返回“歧义”或“无数据”JSON，不生成硬编答案。
- `plot_chart` 只接受结构化 Chart Spec，禁止模型直接执行绘图代码。
- SQL 单语句、只读、表白名单和危险函数校验。
- 最大步数、Token 预算和连续重复工具调用检测。
- 独立 Docker Python 沙箱、10 秒超时、8 KB 输出截断和断网验证。
- DuckDB CSV/Parquet 查询和 PostgreSQL 只读事务执行器。
- MCP Client/Server 集成，支持工具发现、Schema 查询、JSON Schema 转换和统一注册。
- 独立 Sandbox Runner 持有 Docker Socket，FastAPI 后端不再直接控制 Docker。

## LLM 网关

`app/llm/` 提供 OpenAI 兼容网关、任务路由、流式事件和 Token 成本日志。
在 `.env` 中配置：

```dotenv
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=your-key
LLM_DEFAULT_MODEL=deepseek-chat
LLM_TASK_MODELS={"sql":"deepseek-reasoner","intent":"deepseek-chat"}
```

未配置 `LLM_API_KEY` 时，DataPilot 可使用预览运行时启动。将
`CHAT_RUNTIME_MODE=agent` 后，聊天 SSE 会使用真实模型、Agent 工具循环、
DuckDB 数据集、本地工具和 MCP 工具。

## 数据集上传

支持 `.csv`、`.tsv` 和 `.xlsx`，默认单文件上限 20 MB：

- `POST /api/datasets/upload`：上传并转为 Parquet
- `GET /api/datasets`：列出已登记数据集
- `GET /api/datasets/{id}`：查看字段和状态
- `GET /api/datasets/{id}/preview?limit=20`：预览数据
- `DELETE /api/datasets/{id}`：删除元数据、Parquet 和 DuckDB 视图

原始文件与 Parquet 保存在 `dataset_data` Docker Volume。后端启动时会根据
PostgreSQL 元数据恢复已经登记的 DuckDB 表。

## MCP 架构

DataPilot 通过 stdio JSON-RPC 连接独立 MCP Server，并把 MCP 工具转换成统一的
`RegisteredTool`。架构图和完整工具生命周期见
[MCP 架构文档](docs/mcp-architecture.md)。

## 本地开发

后端：

```powershell
Set-Location backend
uv sync --dev
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 18000
```

前端：

```powershell
Set-Location frontend
nvm use 20.19.0
npm install
npm run dev
```

## 当前目录

```text
DataPilot/
├── backend/          # FastAPI、Agent、工具、沙箱与 Alembic 迁移
├── frontend/         # Vue 3 应用
├── sandbox/          # 不可信 Python 代码的隔离执行镜像
├── docker-compose.yml
└── CLAUDE.md         # 项目级强制约束
```
