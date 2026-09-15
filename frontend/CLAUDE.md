# DataPilot Frontend Rules

先阅读并遵守仓库根目录 `CLAUDE.md`。本文件只补充前端实现约定。

## 技术约束

- Vue 3.5+、TypeScript、Vite、Pinia、Vue Router。
- UI 组件使用 Element Plus。
- 图表使用 ECharts，由结构化 Chart Spec 驱动。
- 测试使用 Vitest；代码检查使用 ESLint 和 Prettier。

## 目录职责

- `src/views/`：页面级组件。
- `src/components/`：可复用展示组件。
- `src/stores/`：Pinia 状态。
- `src/api/`：HTTP 与 SSE 客户端。
- `src/router/`：路由定义。
- `src/types/`：共享 TypeScript 类型。

## 实现约定

- 使用 `<script setup lang="ts">` 和 Composition API。
- 页面组件负责编排，业务请求和状态转换不得散落在展示组件中。
- SSE 使用统一事件类型：步骤开始、工具调用、工具结果、文本增量、完成、错误和中断。
- 工具结果渲染必须限制高度，并使用可展开区域查看完整内容。
- 所有网络请求和流式连接必须有停止、超时和错误状态。

## 前端禁止事项

- 不允许直接拼接或执行模型生成的代码。
- 不允许根据未经校验的工具名动态导入任意组件。
- 不允许信任后端返回的 HTML；Markdown 和支持的代码块必须安全渲染。
- 不允许把密钥或个人访问令牌放进 `VITE_*` 环境变量。

