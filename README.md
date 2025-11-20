# Kimi CLI

[![Commit Activity](https://img.shields.io/github/commit-activity/w/MoonshotAI/kimi-cli)](https://github.com/MoonshotAI/kimi-cli/graphs/commit-activity)
[![Checks](https://img.shields.io/github/check-runs/MoonshotAI/kimi-cli/main)](https://github.com/MoonshotAI/kimi-cli/actions)
[![Version](https://img.shields.io/pypi/v/kimi-cli)](https://pypi.org/project/kimi-cli/)
[![Downloads](https://img.shields.io/pypi/dw/kimi-cli)](https://pypistats.org/packages/kimi-cli)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/MoonshotAI/kimi-cli)

[中文](https://www.kimi.com/coding/docs/kimi-cli.html)

Kimi CLI is a new CLI agent that can help you with your software development tasks and terminal operations.

> [!IMPORTANT]
> Kimi CLI is currently in technical preview.

## Key features

- Shell-like UI and shell command execution
- Zsh integration
- [Agent Client Protocol] support
- MCP support
- And more to come...

[Agent Client Protocol]: https://github.com/agentclientprotocol/agent-client-protocol

## Installation

Kimi CLI is published as a Python package on PyPI. We highly recommend installing it with [uv](https://docs.astral.sh/uv/). If you have not installed uv yet, please follow the instructions [here](https://docs.astral.sh/uv/getting-started/installation/) to install it first.

Once uv is installed, you can install Kimi CLI with:

```sh
uv tool install --python 3.13 kimi-cli
```

Run `kimi --help` to check if Kimi CLI is installed successfully.

> [!IMPORTANT]
> Due to the security checks on macOS, the first time you run `kimi` command may take 10 seconds or more depending on your system environment.

## Upgrading

Upgrade Kimi CLI to the latest version with:

```sh
uv tool upgrade kimi-cli --no-cache
```

## Usage

Run `kimi` command in the directory you want to work on, then send `/setup` to setup Kimi CLI:

![](./docs/images/setup.png)

After setup, Kimi CLI will be ready to use. You can send `/help` to get more information.

## Features

### Shell mode

Kimi CLI is not only a coding agent, but also a shell. You can switch the mode by pressing `Ctrl-X`. In shell mode, you can directly run shell commands without leaving Kimi CLI.

> [!NOTE]
> Built-in shell commands like `cd` are not supported yet.

Agent commands now run through a background queue: the prompt becomes available immediately so you can keep typing. Use `/tasks` to inspect progress, `/cancel <id>` to stop a job, and `/approvals` + `/approve`/`/reject` to respond to tool approval requests.

### Structured command transcripts

Every Bash tool invocation emits a short, auditable transcript:

```
• Ran git status
  │ On branch dev
  │ … +12 lines
  └ (exit 0, output truncated)
```

Lines beginning with `│` contain the merged stdout/stderr preview (capped at 20 lines). The footer
reports the exit status plus whether output was truncated or missing. If the command prefix matches
`cli_output.scan_tool_patterns` in `~/.kimi/config.json`, the header gains a `(scan)` tag so
security-focused operations are easy to spot. Customize the patterns with, e.g.:

```json
{
  "cli_output": {
    "scan_tool_patterns": ["scan", "openspec validate", "yarn audit"],
    "replace_grep_with_rg": true,
    "auto_install_ripgrep": false
  }
}
```

When `replace_grep_with_rg` is enabled, the Bash tool rewrites safe `grep`/`egrep`/`fgrep`
segments into ripgrep (`rg`) so pipelines finish faster and produce consistent logs. The transcript
shows the rewritten command with an `(auto-rewritten)` tag plus the original command on the next
line for auditing. Set the option to `false` when you need the command to run exactly as typed.

When ripgrep is missing, the CLI searches `~/.kimi/bin`, bundled deps, then your `PATH`; if it is
still missing, it downloads the official archive from the Kimi CDN, verifies the SHA-256 checksum,
and installs it into `~/.kimi/bin`. Users are prompted unless `auto_install_ripgrep` is `true`. On
failure, the CLI prints manual installation instructions so you can install `rg` yourself.

### Zsh integration

You can use Kimi CLI together with Zsh, to empower your shell experience with AI agent capabilities.

Install the [zsh-kimi-cli](https://github.com/MoonshotAI/zsh-kimi-cli) plugin via:

```sh
git clone https://github.com/MoonshotAI/zsh-kimi-cli.git \
  ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/kimi-cli
```

> [!NOTE]
> If you are using a plugin manager other than Oh My Zsh, you may need to refer to the plugin's README for installation instructions.

Then add `kimi-cli` to your Zsh plugin list in `~/.zshrc`:

```sh
plugins=(... kimi-cli)
```

After restarting Zsh, you can switch to agent mode by pressing `Ctrl-X`.

### ACP support

Kimi CLI supports [Agent Client Protocol] out of the box. You can use it together with any ACP-compatible editor or IDE.

For example, to use Kimi CLI with [Zed](https://zed.dev/), add the following configuration to your `~/.config/zed/settings.json`:

```json
{
  "agent_servers": {
    "Kimi CLI": {
      "command": "kimi",
      "args": ["--acp"],
      "env": {}
    }
  }
}
```

Then you can create Kimi CLI threads in Zed's agent panel.

### Using MCP tools

Kimi CLI supports the well-established MCP config convention. For example:

```json
{
  "mcpServers": {
    "context7": {
      "url": "https://mcp.context7.com/mcp",
      "headers": {
        "CONTEXT7_API_KEY": "YOUR_API_KEY"
      }
    },
    "chrome-devtools": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest"]
    }
  }
}
```

Run `kimi` with `--mcp-config-file` option to connect to the specified MCP servers:

```sh
kimi --mcp-config-file /path/to/mcp.json
```

## HTTP 服务

`src/kimi_http/` 提供了一个基于 Quart + Hypercorn 的 HTTP/2 服务入口，所有 API 统一挂在 `/api/v1` 前缀下，并以 NDJSON 流式输出事件。

### 启动服务

```sh
python -m kimi_http.server --host 0.0.0.0 --port 9000
```

主要路由：

- `GET /api/v1/health`：返回 `{"status": "ok", "version": "..."}`。
- `POST /api/v1/runs`：请求体示例：
  ```json
  {
    "work_dir": "/workspace/project",
    "command": "scan the repo",
    "env": {
      "KIMI_BASE_URL": "https://api.moonshot.cn/v1",
      "KIMI_API_KEY": "sk-...",
      "KIMI_MODEL_NAME": "kimi-for-coding"
    },
    "options": {
      "yolo": true,
      "thinking": false
    }
  }
  ```
  响应为 `application/x-ndjson`，每行都是一个事件（wire 事件、审批、完成状态等）。
- `POST /api/v1/runs/<id>/cancel`：取消指定 run，并在流中返回 `cancelled` 状态。
- `/runs` 默认流式返回 NDJSON 事件（`thread.started`、`turn.started`、`item.completed`、`turn.completed` 等），每个事件都是单行 JSON，文本类项会在服务器端聚合成完整句子后再推送。若想在一次响应中得到 `{run_id, conversation[], status}` 聚合结果，可传 `"stream": false`；若想在聚合结果里附带事件数组，可再加 `"include_events": true`。

服务会为每个请求独立创建 `Session`、`Runtime`、`KimiSoul`，互不共享历史；审批默认自动通过。若需要 HTTP/2，可使用 `curl --http2` 或任意支持 HTTP/2 的客户端。

### Docker Compose 部署

仓库根目录提供了 `docker-compose.yml` 与 `Dockerfile.http`。准备好如下环境变量后即可运行：

```sh
export KIMI_BASE_URL="https://api.moonshot.cn/v1"
export KIMI_API_KEY="sk-..."
export KIMI_MODEL_NAME="kimi-for-coding"
docker compose up --build
```

服务会监听 `KIMI_HTTP_PORT`（默认 9000），所有必要的 LLM 配置通过环境变量传入容器，镜像入口即 `python -m kimi_http.server`。

### 打包独立二进制

使用 PyInstaller 生成无需额外依赖的可执行文件：

```sh
make build_http
./dist/kimi_http --host 0.0.0.0 --port 9000
```

## Development

To develop Kimi CLI, run:

```sh
git clone https://github.com/MoonshotAI/kimi-cli.git
cd kimi-cli

make prepare  # prepare the development environment
```

> [!NOTE]
> `make prepare` runs `uv sync --group dev`, so all development/test dependencies (including `pytest`) are available for `pytest`, `make test`, etc.

Then you can start working on Kimi CLI.

Refer to the following commands after you make changes:

```sh
uv run kimi  # run Kimi CLI

make format  # format code
make check  # run linting and type checking
make test  # run tests
make help  # show all make targets
```

## Contributing

We welcome contributions to Kimi CLI! Please refer to [CONTRIBUTING.md](./CONTRIBUTING.md) for more information.
