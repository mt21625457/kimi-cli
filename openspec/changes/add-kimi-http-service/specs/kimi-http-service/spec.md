## ADDED Requirements
### Requirement: HTTP 服务入口独立于现有 CLI 代码
Kimi CLI MUST 在 `src/kimi_http/` 目录下提供独立的 HTTP 服务入口（例如 `python -m kimi_http.server`），并通过组合现有的 `KimiCLI`/`KimiSoul` API 完成初始化，不得修改任何既有模块。所有 HTTP 路由 SHALL 挂载在 `/api/v1` 前缀下，并使用原生支持 HTTP/2 与流式响应的 ASGI 组合（例如 Quart + Hypercorn）。

#### Scenario: 单独启动 HTTP 服务
- **Given** 仓库中尚未对 `src/kimi_cli/` 下的代码做任何更改
- **When** 开发者运行 `python -m kimi_http.server --host 0.0.0.0 --port 9000`
- **Then** 服务器 MUST 启动监听端口，日志中应显示服务地址
- **AND** 该实现 MUST 完全位于 `src/kimi_http/` 下的新模块中，复用项目已有的配置加载、Session、Agent 逻辑
- **AND** 构建产物（依赖、入口点）不得要求修改 `src/kimi_cli` 的源码
- **AND** 服务器对外公开的 API MUST 一律带有 `/api/v1` 前缀（例如 `/api/v1/health`、`/api/v1/runs`）。

#### Scenario: HTTP/2 与流式传输
- **Given** 服务使用 Hypercorn + Quart（或等价的支持 HTTP/2 的 ASGI 实现）
- **When** 客户端使用 HTTP/2 协议访问 `/api/v1/runs`
- **Then** 响应 MUST 通过 HTTP/2 data frame/Chunked 方式逐条写出事件，不得在内存中缓冲到结束后一次性返回。

### Requirement: POST /runs SHALL 启动独立 Runtime 并流式输出
HTTP 服务 MUST 暴露 `POST /api/v1/runs` 接口，接收 JSON（包含 `work_dir`、`command`、`agent_file`、`model_name` 以及可选 `env`/`options`），并为每个请求即时创建 Session + Runtime。默认（`stream=true`）时，服务器 SHALL 直接流式推送 NDJSON 事件：`thread.started`、`turn.started`、聚合后的 `wire_event`、`turn.completed`、审批通知等，语义需对齐 Codex SDK 的事件式 streaming；每个 `wire_event` 的文本 payload MUST 是完整语句而非 token 分片。若指定 `stream=false`，则服务器 MUST 在本地聚合事件并一次性返回 `{run_id, conversation[], status}` JSON；当 `include_events=true` 时再附带事件数组。

#### Scenario: 请求触发独立执行
- **Given** 客户端向 `/api/v1/runs` 发送 `{ "work_dir": "/tmp/app", "command": "list files" }`
- **When** 服务器处理该请求
- **Then** 服务 MUST 创建一个新的 `Session` 与 `Runtime`（包含 `KimiSoul`）仅服务该请求
- **AND** 服务 MUST 将线程事件按发生顺序序列化为 JSON 行输出，包括 `thread.started`、`turn.started`、`item.*`、`turn.completed`、审批等结构化事件
- **AND** 响应最终 MUST 以一个终止事件或状态块告知成功、失败或超时。

#### Scenario: 环境变量与模型覆盖
- **Given** 请求 payload 中提供 `env`: `{ "KIMI_BASE_URL": "https://foo", "KIMI_API_KEY": "sk-..." }` 以及 `model_name`
- **When** Runtime 被创建
- **Then** 服务 MUST 将这些值注入进 `augment_provider_with_env_vars` 同等逻辑中，以确保无需修改 `~/.kimi/config.json` 即可完成调用。

-#### Scenario: 非流式模式一次性返回
- **Given** 客户端在请求体中设置 `"stream": false`
- **When** 运行完成
- **Then** 服务 MUST 聚合该 run 的所有事件并以单个 JSON 数组（或对象）返回，避免边生成边写；默认行为仍为流式输出。

### Requirement: 请求隔离与并行
服务 MUST 能够同时处理多个 `/api/v1/runs` 请求，每个请求使用独立的 Session/Runtime/工作目录，不得共享上下文或互相阻塞；同时提供取消/超时的能力以便在 HTTP 层终止正在运行的代理。

#### Scenario: 并发运行互不影响
- **Given** 客户端 A、B 同时向 `/api/v1/runs` 提交不同的 `work_dir` + 命令
- **When** 两个请求同时运行
- **Then** 服务 MUST 启动两个 Runtime 并保持它们的 wire 事件严格隔离，不可出现上下文或历史交叉
- **AND** 如果其中一个请求提前结束，另一个请求 MUST 继续运行且不重用第一个请求的 Session。

#### Scenario: HTTP 级别取消
- **Given** 某个 `/api/v1/runs` 请求在服务器端运行中
- **When** 客户端关闭连接或调用 `/api/v1/runs/{id}/cancel`
- **Then** 服务 MUST 触发对应 Runtime 的 `cancel_event`，向客户端输出取消状态事件，并确保后台任务被清理。

### Requirement: 审批与错误处理
服务 MUST 能够自动处理需要审批的工具调用（默认自动批准或通过单独的 API 反馈），并在响应流中清楚表达审批请求、通过/拒绝以及任何异常。

#### Scenario: 自动批准工具
- **Given** 某个运行触发需要审批的工具
- **When** HTTP 服务未配置外部审批回调
- **Then** 服务 MUST 自动批准该请求并在事件流中记录批准动作，避免 run 被阻塞。

#### Scenario: 错误可观测
- **Given** LLM 认证失败或 Runtime 初始化出错
- **When** `/api/v1/runs` 请求即刻失败
- **Then** 服务 MUST 返回 4xx/5xx 状态并输出 JSON 错误对象，同时在事件流中明确写出错误原因或失败码，便于调用方重试。

### Requirement: Docker Compose 部署示例
项目 MUST 在仓库根目录提供 `docker-compose.yml`，给出运行 HTTP 服务的参考部署方式，并通过环境变量传入 `KIMI_BASE_URL`、`KIMI_API_KEY`、`KIMI_MODEL_NAME` 以及其他必要配置。

#### Scenario: Compose 文件暴露配置
- **Given** 用户查看仓库提供的 `docker-compose.yml`
- **When** 他们执行 `docker compose up` 并在 `.env` 或环境中注入 `KIMI_BASE_URL`、`KIMI_API_KEY`、`KIMI_MODEL_NAME`
- **Then** Compose 服务 MUST 显式声明这些 env 并将其传递到容器内，从而让 HTTP 服务无需修改镜像即可使用外部 LLM。
- **AND** Compose 文件 MUST 在 README/文档中被引用，解释如何填写 env 与映射端口。

### Requirement: make build_http SHALL produce standalone binary
项目 MUST 在 `Makefile` 中新增 `build_http` 目标，使用 PyInstaller（或等价打包工具）把 `src/kimi_http` 服务打包为可直接执行的 `kimi_http` 二进制，不依赖系统 Python/venv 即可运行。

#### Scenario: 构建命令输出二进制
- **Given** 开发者在仓库根目录执行 `make build_http`
- **When** 构建成功
- **Then** `dist/kimi_http`（或对应平台可执行文件） MUST 生成并具备执行权限
- **AND** 运行 `./dist/kimi_http --help` 时不需要预装 Python 依赖，即可启动 HTTP 服务或显示帮助。
