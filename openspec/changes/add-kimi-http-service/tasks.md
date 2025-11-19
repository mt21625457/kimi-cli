## 1. Implementation
- [ ] 1.1 在 `src/kimi_http/` 下创建 Python 包（`__init__.py`, `server.py`, `runtime.py`），实现 `python -m kimi_http.server --host/--port` 入口，所有路由挂载 `/api/v1` 前缀，无需修改 `src/kimi_cli/`。
- [ ] 1.2 选用原生支持 HTTP/2 的 ASGI 组合（如 Quart + Hypercorn）：实现 `GET /api/v1/health`、`POST /api/v1/runs`、`POST /api/v1/runs/{id}/cancel`，并在 HTTP/2 链路上验证。
- [ ] 1.3 编写运行器：为每个 `/api/v1/runs` 请求创建独立 `Session`、`Runtime`、`KimiSoul`，利用 `run_soul` 获取 wire 事件，以 HTTP/2 data frame/NDJSON 流写回响应。
- [ ] 1.4 处理审批/取消/超时：默认自动批准工具请求，监控客户端断连或取消 API 触发 `cancel_event`，同时提供统一的错误响应格式。
- [ ] 1.5 为 HTTP server 添加并发/取消/审批/错误路径测试，以及 README/文档说明 HTTP/2 部署、启动指令、示例 payload、环境变量覆盖与依赖安装。
- [ ] 1.6 在仓库根目录提供 `docker-compose.yml` 与示例 `.env`/文档，说明如何通过 `KIMI_BASE_URL`、`KIMI_API_KEY`、`KIMI_MODEL_NAME` 等环境变量配置容器运行，并验证 `docker compose up` 可启动 HTTP 服务。
- [ ] 1.7 在 Makefile 中新增 `build_http` 目标，基于 PyInstaller（或等价工具）打包 `src/kimi_http` 服务，输出 `dist/kimi_http` 单一可执行文件，并在文档中说明使用方式。
