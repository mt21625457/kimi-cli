# Project Context

## Purpose
Kimi CLI delivers an interactive, AI-assisted coding agent for the terminal. The CLI focuses on
streamlining software engineering workflows through modular agents, tool orchestration, and
multiple UI modes suited for both interactive use and scripted automation.

## Tech Stack
- Python 3.13+ with asyncio-first design
- Typer CLI framework with uv_build packaging
- uv for dependency management and PyInstaller for binary builds
- kosong LLM integration layer with structured prompts
- Tooling: ruff (lint/format), pyright (type checks), pytest (tests), loguru (logging)

## Project Conventions

### Code Style
- Max line length 100; formatting enforced via `ruff format`
- Ruff rulesets (E, F, UP, B, SIM, I) keep imports sorted and code modernized
- Strict typing checked by pyright; prefer explicit annotations
- Structured logging through loguru; avoid bare prints in runtime paths

### Architecture Patterns
- Agent specs in YAML feed `KimiSoul`, which manages context, retries, and tool routing
- Tool layer is modular with dependency injection for bash, file, web, MCP, and task subagents
- UI split between Shell, Print, and ACP modes for interactive and headless workflows
- Configuration pulled from `~/.kimi/config.json`; secrets handled via `SecretStr`

### Testing Strategy
- pytest with asyncio fixtures for async components
- Heavy use of mocks for LLM providers and external tools to stabilize tests
- Integration tests cover agent loading, tool orchestration, and subagent behaviors
- CI expectation: `make test` plus `make check` (ruff + pyright) before merging

### Git Workflow
- Spec-driven development via OpenSpec: proposals are required for new capabilities or behavior
  changes; implementation starts only after approval
- Feature work occurs on topic branches that correspond to the change-id; merge when proposal,
  tasks, and validation are complete
- Semantic versioning governs releases; archival moves happen post-deployment

## Domain Context
The CLI targets professional software engineers who need an AI pair-programmer that can execute
shell commands, edit files, and coordinate subagents. Emphasis is on reliable automation,
configurability, and secure handling of user environments.

## Important Constraints
- File system and network access are sandboxed by default; tools must respect workspace limits
- API keys and credentials managed as secrets; never log sensitive values
- Shell execution paths must be explicit and well-audited to avoid destructive commands
- Prefer simple solutions (<100 lines) unless scale or performance data justifies complexity

## External Dependencies
- Kimi API / kosong models for LLM interactions
- Moonshot Search API for search-enabled agents
- PyPI and uv index for dependency resolution
