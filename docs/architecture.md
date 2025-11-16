
# Kimi CLI 架构解析

本文系统梳理 Kimi CLI 的代码结构、核心运行流程以及各模块的职责，便于在现有基础上扩展新能力（如文档生成、仓库扫描或 IDE 集成）。

## 1. 端到端执行流程

1. **CLI 入口**：`src/kimi_cli/cli.py` 暴露 `kimi` 命令，解析 UI 模式（shell/print/acp/wire）、工作目录、Agent 配置与模型参数。
2. **应用启动**：CLI 调用 `src/kimi_cli/app.py` 中的 `KimiCLI.create`，依次完成配置加载、LLM 初始化、`Session` 打开/创建、`Runtime` 构建、Agent 解析、上下文恢复，并实例化 `KimiSoul`。
3. **UI 驱动**：`KimiCLI.run_shell_mode/run_print_mode/run_acp_server/run_wire_server`（位于 `src/kimi_cli/ui/*`）根据模式负责事件循环与渲染，真实的推理与工具调用交由 soul 完成。
4. **Soul 循环**：`src/kimi_cli/soul/kimisoul.py` 接收用户输入，写入上下文，执行主循环，可调用工具、发起审批、运行子代理、进行上下文压缩，并通过 wire 层持续输出状态。
5. **工具层**：`src/kimi_cli/tools/` 下的工具实现文件操作、Shell 命令、Web 搜索、MCP 调用等副作用，并将结果封装成聊天消息返回给 soul。

## 2. 模块全景

| 模块区域 | 关键路径 | 主要职责 |
| --- | --- | --- |
| CLI 与启动 | `cli.py`, `app.py`, `Makefile` | 解析命令行、配置日志、选择 UI 模式、创建 `KimiCLI` 实例，提供构建/测试入口。 |
| 配置与 LLM | `config.py`, `llm.py`, `constant.py`, `exception.py` | 读取/校验 `~/.kimi/config.json`，定义 Provider/Model，创建 LLM 客户端（kosong/OpenAI/Anthropic 等），暴露版本信息与专用异常。 |
| 会话与元数据 | `session.py`, `metadata.py`, `share.py` | 维护目录级 Session 和历史记录，跟踪最近一次会话与 thinking 状态，统一管理 `~/.kimi` 共享目录。 |
| Agent 规格 | `agentspec.py`, `agents/`, `prompts/` | 加载/继承 YAML Agent 配置，解析系统提示与子代理，提供默认 Prompt 模板（初始化、压缩等）。 |
| Soul 运行时 | `soul/`（agent、kimisoul、context、runtime、toolset、approval 等） | 实现主循环、上下文管理、检查点、审批、状态事件、工具装配、子代理执行。 |
| 工具体系 | `tools/` | 按模块提供 Bash、文件操作、Web、MCP、Task、Todo、Think、DMail、测试等工具，实现权限校验与 IO 规则。 |
| UI 实现 | `ui/`（shell、print、acp、wire） | Shell TUI、脚本模式、ACP 服务、实验性 wire server，负责输入输出、快捷键与 soul 的桥接。 |
| Shell 任务调度 | `ui/shell/task_manager.py` | 管理命令队列、后台执行器、任务状态存储、审批请求路由与日志。 |
| Wire 协议 | `wire/` | 定义 Step/Status/Approval 等消息，供 soul 与 UI 进行实时通信。 |
| 工具库 | `utils/`, `share.py`, `utils/rich/`, `utils/aiohttp.py` 等 | 提供日志、HTTP、终端、剪贴板、路径旋转、字符串处理、PyInstaller 辅助等通用能力。 |
| 测试与资源 | `tests/`, `tests_ai/`, `docs/images/`, `src/kimi_cli/deps/` | Pytest 测试、AI 集成测试、文档图片、外部依赖/Makefile。 |

## 3. 核心模块解析

### 3.1 CLI 与应用引导

- `src/kimi_cli/cli.py` 基于 Typer 实现命令行，校验互斥模式，配置日志文件（`~/.kimi/logs/kimi.log`），并通过 `Session.create`/`continue_` 启动或恢复会话。
- `src/kimi_cli/app.py` 集中处理启动逻辑：加载配置、应用环境变量覆盖（例如 `KIMI_BASE_URL`）、调用 `llm.create_llm` 初始化模型、构建 `Runtime`、加载 Agent、恢复 `Context` 并创建 `KimiSoul`。提供运行各 UI 模式的封装，包含临时 `chdir` 和 stderr 重定向。

### 3.2 配置、LLM 与 Session

- `config.py` 定义 `LLMProvider`、`LLMModel`、`LoopControl`、`Services` 等 pydantic 模型，并提供 `load_config/save_config/get_default_config`。
- `llm.py` 支持 Kimi/OpenAI/Anthropic/Chaos Provider，附带能力推断（如是否支持 Thinking），同时读取环境变量以覆盖配置。
- `session.py`、`metadata.py` 负责 `~/.kimi/kimi.json` 元数据和 `~/.kimi/sessions/<hash>/<session>.jsonl` 历史文件，为不同工作目录提供独立上下文。
- `soul/runtime.py` 在上述基础上构建不可变 `Runtime`，包含系统提示内置变量（时间/目录/AGENTS.md）、`DenwaRenji`、`Approval` 管理器等。

### 3.3 Agent 配置与 Prompt

- `agentspec.py` 解析 YAML，支持 `extend` 机制、系统提示参数合并、工具包含/排除以及子代理路径解析，最终生成 `ResolvedAgentSpec`。
- 默认 Agent 位于 `agents/default/`，包含 `agent.yaml`（工具列表、子代理）、`sub.yaml`（子代理附加提示）、`system.md`（系统指令）。
- `prompts/` 保存 `init.md`、`compact.md` 等模板，Soul 在初始化或上下文压缩时引用。

### 3.4 Soul 运行时

- `soul/kimisoul.py` 是执行核心：管理检查点、调用 tenacity 进行重试、预留 Token 并触发上下文压缩、发起审批、调度工具、通过 wire 推送 Step/Status 事件，直至满足结束条件或触达 `max_steps`。
- `soul/context.py` 维护消息历史、检查点与回滚，支撑 “BackToTheFuture” 与压缩流程。
- `soul/agent.py` 加载 Agent Spec，构建工具集合（`toolset.py`），并解析子代理供 Task 工具调用。
- `soul/approval.py` 用队列管理审批请求；`soul/denwarenji.py` 负责工具通信；`soul/message.py` 校验消息能力并将工具结果转成聊天片段。

### 3.5 工具体系

所有工具继承自 kosong 的 `CallableTool/CallableTool2`，通过依赖注入获得 `Runtime` 或审批对象。

- **Bash** (`tools/bash`)：带超时的命令执行，流式输出 stdout/stderr，默认需审批。
- **文件工具** (`tools/file`)：包含 Read/G​lob/Grep/Write/StrReplace/Patch 等，严格要求绝对路径与工作目录内写入，带行/字节上限、防目录遍历。
- **Web 工具** (`tools/web`)：Moonshot Search、FetchURL，自动附加 User-Agent、Tool-Call ID。
- **Task** (`tools/task`)：运行子代理，独立上下文与历史文件，并把审批事件回传父 wire。
- **Todo/Think/DMail/Test**：任务管理、自我思考、时间信、AI 测试等辅助工具。
- **MCP** (`tools/mcp.py`)：动态包装 MCP 工具，转换图文/音频内容，统一审批流程。
- **工具共用函数** (`tools/utils.py`)：描述模板、输出截断、拒绝处理等。

### 3.6 UI 与 Wire

- **Shell UI** (`ui/shell/`)：基于 prompt-toolkit 的终端界面，包含控制台渲染、快捷键（Ctrl-X）、元命令、可视化/调试等组件。2024/xx 起新增 `ShellTaskManager`，通过命令队列 + 后台执行器维持非阻塞交互：用户输入立即返回提示符，任务状态/日志通过 `task_manager.py` 统一打印，审批请求可用 `/approve`、`/reject`、`/approvals` 等命令管理。
- **Print 模式** (`ui/print`)：非交互脚本模式，支持 text / stream-json 输入输出，自动启用 YOLO，适合 CI/CD。
- **ACP Server** (`ui/acp`)：实现 Agent Client Protocol，可供 Zed 等 IDE 作为远程 Agent。
- **Wire Server** (`ui/wire`)：实验性接口，供外部客户端订阅消息流。
- `wire/message.py` 定义 StepBegin/StatusUpdate/ApprovalRequest/SubagentEvent 等结构，使 UI 与 soul 之间保持松耦合。

### 3.7 通用工具

- `utils/logging.py` 基于 Loguru，提供 `StreamToLogger` 将第三方 stderr 重定向到日志。
- `utils/aiohttp.py` 提供统一的 HTTP Session 创建；`utils/path.py`、`utils/string.py`、`utils/message.py` 等封装常用逻辑。
- `utils/clipboard.py`、`utils/signals.py`、`utils/term.py` 处理平台差异与终端能力；`utils/pyinstaller.py` 辅助二进制打包。
- `share.py`、`metadata.py`、`session.py`（前文已述）确保文件结构一致。

## 4. 扩展与实践建议

1. **自定义 Agent**：在 `src/kimi_cli/agents/` 或外部 YAML 中定义新 persona（如“文档生成器”、“仓库扫描器”），调整工具列表与系统提示。
2. **新增工具**：在 `tools/` 下创建模块，定义参数 Schema 与 `__call__` 实现，再在 Agent Spec 中注册。
3. **自动化运行**：使用 `--print` 或 `--wire` 结合 `--command`/`--yolo` 实现无头模式，或通过 ACP 接入 IDE。
4. **分发**：开发阶段用 `uv sync`；需要单文件分发时运行 `make build`（PyInstaller）。Go 或其他语言可在外围做编排，无需重写核心逻辑。
5. **测试保障**：通过 `make test`、`make check` 以及 `tests_ai` 目录中的 Kimi CLI 自测脚本，确保新增功能不会破坏既有行为。

掌握上述模块关系后，可以从 CLI 入口一路追踪到工具副作用与 UI 呈现，快速定位扩展点并评估变更影响。***
