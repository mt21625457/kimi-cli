# Kimi HTTP API 文档

`src/kimi_http/` 提供基于 Quart + Hypercorn 的 HTTP/2 服务，所有接口统一挂在 `/api/v1` 前缀。服务通过 `python -m kimi_http.server` 或 `./kimi_http.sh` 启动，默认监听 `0.0.0.0:9000`。以下说明各接口的请求参数、返回格式以及示例。

> **身份与模型配置**：若在启动脚本/容器中设置了 `KIMI_BASE_URL`、`KIMI_API_KEY`、`KIMI_MODEL_NAME`，所有请求默认复用这些值。也可以在单个 `/runs` 请求中通过 `env` 字段覆盖。

## 通用说明

- **Base URL**：`http(s)://<host>:<port>/api/v1`
- **协议**：HTTP/1.1 和 HTTP/2 均可。推荐 `curl --http2` 进行流式调试。
- **Content-Type**：JSON 请求使用 `application/json`。`/runs` 返回 `application/x-ndjson`，每行一个 JSON 事件。
- **错误格式**：`{ "error": "invalid_request", "details": ... }`，状态码 4xx/5xx。

## GET /api/v1/health

返回服务状态与版本信息。

```http
GET /api/v1/health HTTP/2
```

**响应示例**

```json
{
  "status": "ok",
  "version": "0.54"
}
```

## POST /api/v1/runs

提交一次运行请求。服务会为该请求创建独立 `Session` + `Runtime`，执行 `command`，并以 NDJSON 流实时返回 wire 事件、审批决策和最终状态。

### 请求体字段

| 字段        | 类型      | 必填 | 说明 |
|-------------|-----------|------|------|
| `command`   | string    | ✔️   | 用户指令，等同于 shell/聊天输入。必须为非空文本。 |
| `work_dir`  | string    | ✔️   | 绝对路径，运行时会对其 `resolve()`；该目录必须存在。 |
| `agent_file`| string    | ❌   | 自定义 agent YAML，默认 `src/kimi_cli/agents/default/agent.yaml`。 |
| `model_name`| string    | ❌   | 指定 `~/.kimi/config.json` 中的模型名；若为空则沿用默认模型。 |
| `config_file` | string  | ❌   | 自定义配置文件路径，默认 `~/.kimi/config.json`。 |
| `env`       | object    | ❌   | 覆盖 provider/model 的环境变量。常见键：`KIMI_BASE_URL`、`KIMI_API_KEY`、`KIMI_MODEL_NAME`、`KIMI_MODEL_MAX_CONTEXT_SIZE`、`KIMI_MODEL_CAPABILITIES` 等。键名大小写不敏感，服务会统一转换为大写。 |
| `options`   | object    | ❌   | 运行期选项。`yolo` (bool, default true) 自动批准工具请求；`thinking` (bool, default false) 请求思维链模式（需模型支持）。 |
| `stream`    | bool      | ❌   | 默认 `true`，服务器会直接流式推送 NDJSON 事件（`thread.started`、`turn.started`、`item.completed`、`turn.completed` 等），每个事件是一行 JSON。设置为 `false` 时，返回单个 `{run_id, conversation[], status}` JSON。 |
| `include_events` | bool | ❌ | 仅在 `stream=true` 模式下有效。默认为 `false`（不返回原始事件）；当为 `true` 时，响应会额外包含 `events[]`，用于调试或审计。 |

### 响应格式

- `stream=true`（默认）：`Content-Type: application/x-ndjson`，响应体由多行 JSON 组成，每行对应一个事件，结构为 `{ "run_id": "...", "type": "thread.started", "payload": {...}, "ts": "ISO 时间" }`。常见事件：
  - `thread.started`：线程创建；`payload.thread_id` 即 `run_id`
  - `turn.started` / `turn.completed`：一次提问的生命周期，`payload.status` 表示 `finished` / `error` / `cancelled` 等状态
  - `item.started` / `item.completed`：线程项（当前实现聚合出 `item.type = "agent_message"` 的整句文本，后续会扩展命令执行、文件修改、MCP 调用等类型）
  - `approval_request` / `approval_response`、`error` 等
  - 服务器会在内部聚合文本，确保 `item` 事件一次输出完整句子，而非按 token 切分
- `stream=false`：`Content-Type: application/json`，返回 `{ "run_id": "...", "conversation": [...], "status": "finished" }`；若设置 `"include_events": true`，则额外附带 `events` 数组，其内容与流式事件一致。

### 请求示例

```bash
curl --http2 -N \
  -H 'Content-Type: application/json' \
  -d '{
        "work_dir": "/Users/alice/project",
        "command": "scan the repo",
        "options": {"yolo": true, "thinking": false}
      }' \
  http://localhost:9000/api/v1/runs
```

### 响应片段示例

```
{"run_id":"7c6...","type":"thread.started","payload":{"thread_id":"7c6...","work_dir":"/Users/alice/project","agent_file":"/Users/.../agent.yaml"},"ts":"2025-11-19T07:15:23.512Z"}
{"run_id":"7c6...","type":"turn.started","payload":{},"ts":"2025-11-19T07:15:23.700Z"}
{"run_id":"7c6...","type":"item.started","payload":{"item":{"id":"item_1","type":"agent_message","text":"Diagnosing..."}},"ts":"2025-11-19T07:15:27.100Z"}
{"run_id":"7c6...","type":"item.completed","payload":{"item":{"id":"item_1","type":"agent_message","text":"Diagnosing repo state…"}},"ts":"2025-11-19T07:15:28.300Z"}
{"run_id":"7c6...","type":"turn.completed","payload":{"status":"finished"},"ts":"2025-11-19T07:16:03.289Z"}
```

若发生错误，例如 LLM 未配置，流中会出现：

```
{"run_id":"7c6...","type":"error","payload":{"message":"LLM is not configured"},"ts":"..."}
{"run_id":"7c6...","type":"turn.completed","payload":{"status":"error"},"ts":"..."}
```

## POST /api/v1/runs/{run_id}/cancel

取消进行中的 run，请求成功后会在对应的事件流里收到 `run_completed` 状态为 `cancelled`。

```bash
curl -X POST http://localhost:9000/api/v1/runs/<run_id>/cancel
```

**响应示例**

```json
{
  "run_id": "7c6...",
  "status": "cancelling"
}
```

若 run 不存在或已结束，返回 `404`。

## 部署与运行

- **本地启动**：`./kimi_http.sh`（需预先导出 `KIMI_BASE_URL`、`KIMI_API_KEY`、`KIMI_MODEL_NAME`）。
- **Docker Compose**：`docker compose up --build`（参见 `docker-compose.yml`，env 通过 `.env` 或 shell 导出）。
- **独立二进制**：`make build_http && ./dist/kimi_http --host 0.0.0.0 --port 9000`。

## 故障排查

| 症状 | 说明/处理 |
|------|-----------|
| `405 Method Not Allowed` | `/runs` 仅支持 POST；调试时需指定 `-X POST -H 'Content-Type: application/json'`。 |
| `LLM is not configured` | 启动时未设置 `KIMI_BASE_URL/KIMI_API_KEY/KIMI_MODEL_NAME`，或配置文件缺少默认模型。可通过请求体 `env` 覆盖。 |
| `curl: (16) Error in the HTTP2 framing layer` | 确保使用最新 `curl --http2`，以及环境中安装的 `h2` 版本与 hypercorn 兼容（锁定 `<4.3` 已处理）。 |
| `PermissionError` | `work_dir` 必须存在且服务对其有读写权限；容器部署时注意 volume 映射。 |

如需扩展更多路由或认证机制，可在 `src/kimi_http/server.py` 中添加新的蓝图或中间件。EOF
