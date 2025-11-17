from __future__ import annotations

from inline_snapshot import snapshot

from kimi_cli.config import (
    CLIOutputConfig,
    Config,
    Services,
    ShellConfig,
    TaskBannerConfig,
    get_default_config,
)


def test_default_config():
    config = get_default_config()
    assert config == snapshot(
        Config(
            default_model="",
            models={},
            providers={},
            services=Services(),
            cli_output=CLIOutputConfig(),
        )
    )


def test_default_config_dump():
    config = get_default_config()
    assert config.model_dump_json(indent=2, exclude_none=True) == snapshot(
        """\
{
  "default_model": "",
  "models": {},
  "providers": {},
  "loop_control": {
    "max_steps_per_run": 100,
    "max_retries_per_step": 3
  },
  "services": {},
  "cli_output": {
    "scan_tool_patterns": [
      "scan",
      "rg --files",
      "openspec validate"
    ]
  },
  "shell": {
    "task_banner": {
      "visible_slots": 4,
      "refresh_interval": 1.0
    }
  }
}\
"""
    )


def test_task_banner_config_invalid_values_fallback():
    config = Config(
        shell=ShellConfig(
            task_banner=TaskBannerConfig(
                visible_slots=0,
                refresh_interval=0.05,
            )
        )
    )
    assert config.shell.task_banner.visible_slots == 4
    assert config.shell.task_banner.refresh_interval == 1.0
