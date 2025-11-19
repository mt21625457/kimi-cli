## Why
- 需要一个稳定的方式把 Kimi Agent 能力暴露给其他语言/进程，无需通过 CLI TTY 或 prompt-toolkit；HTTP 服务是最通用的集成手段。
- 目前 repo 中只有 Shell/Print/ACP/Wire UI，尚无常驻服务入口，也难以在 CI 或远程环境里以云原生方式复用。
- 需求约束为“不得修改现有代码，只能在 `src/kimi_http/` 下实现”，因此需要以组合方式封装 `KimiCLI` 并补齐多请求隔离、事件流输出。

## What Changes
- 在 `src/kimi_http/` 新增独立包，包含：配置解析、服务器启动（例如 `python -m kimi_http.server`）以及 HTTP handler，所有 API 均挂载在 `/api/v1/*` 下。
- 选用原生支持 HTTP/2 与流式响应的 ASGI 方案（优先 Quart + Hypercorn），确保 `POST /api/v1/runs`、`GET /api/v1/health`、`POST /api/v1/runs/{id}/cancel` 可在 HTTP/2 链接中稳定工作。
- `POST /api/v1/runs` 请求体允许指定 `work_dir`、`agent_file`、`model_name`、`env` 等参数；服务端为每个请求创建独立的 `Session`、`Runtime`、`KimiSoul`。
- 返回体使用 HTTP/2 data frame/Chunked NDJSON 流输送 `wire.message` 事件（Step、Status、Approval、结果）；工具审批默认自动通过，后续可挂钩自定义策略。
- 运行期提供并行执行、取消/超时、错误回显；任何共享逻辑都通过组合 `KimiCLI` 现有 API 完成，避免更改 `src/kimi_cli` 下的源码。
- 编写 README/文档片段说明依赖安装、HTTP/2 部署方法、请求示例以及环境变量覆盖规则，并新增 `docker-compose.yml` + `.env` 示例，展示如何通过 `KIMI_BASE_URL`、`KIMI_API_KEY`、`KIMI_MODEL_NAME` 等 env 配置容器化部署。
- 提供 `make build_http` 目标，产出无需 Python 依赖的 `kimi_http` 可执行文件，便于离线或生产环境部署。

## Impact
- 需要新增 HTTP 框架依赖（例如 FastAPI + Uvicorn），并在部署/打包时考虑其体积。
- 每个请求都要即时构建 Runtime，会增加 LLM 连接与 Session 创建开销；需通过合理的 pooling 或缓存路径控制资源。
- 新的服务入口需要额外的测试（并发/取消/审批），并确保不会破坏现有 CLI 行为。
