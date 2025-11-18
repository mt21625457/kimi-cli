from __future__ import annotations

import json
from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field, SecretStr, ValidationError, field_serializer, model_validator

from kimi_cli.exception import ConfigError
from kimi_cli.llm import ModelCapability, ProviderType
from kimi_cli.share import get_share_dir
from kimi_cli.utils.logging import logger


class LLMProvider(BaseModel):
    """LLM provider configuration."""

    type: ProviderType
    """Provider type"""
    base_url: str
    """API base URL"""
    api_key: SecretStr
    """API key"""
    custom_headers: dict[str, str] | None = None
    """Custom headers to include in API requests"""

    @field_serializer("api_key", when_used="json")
    def dump_secret(self, v: SecretStr):
        return v.get_secret_value()


class LLMModel(BaseModel):
    """LLM model configuration."""

    provider: str
    """Provider name"""
    model: str
    """Model name"""
    max_context_size: int
    """Maximum context size (unit: tokens)"""
    capabilities: set[ModelCapability] | None = None
    """Model capabilities"""


class LoopControl(BaseModel):
    """Agent loop control configuration."""

    max_steps_per_run: int = 100
    """Maximum number of steps in one run"""
    max_retries_per_step: int = 3
    """Maximum number of retries in one step"""


class MoonshotSearchConfig(BaseModel):
    """Moonshot Search configuration."""

    base_url: str
    """Base URL for Moonshot Search service."""
    api_key: SecretStr
    """API key for Moonshot Search service."""
    custom_headers: dict[str, str] | None = None
    """Custom headers to include in API requests."""

    @field_serializer("api_key", when_used="json")
    def dump_secret(self, v: SecretStr):
        return v.get_secret_value()


class Services(BaseModel):
    """Services configuration."""

    moonshot_search: MoonshotSearchConfig | None = None
    """Moonshot Search configuration."""


def _default_scan_tool_patterns() -> list[str]:
    return [
        "scan",
        "rg --files",
        "openspec validate",
    ]


class CLIOutputConfig(BaseModel):
    """Preferences for CLI-printed command transcripts."""

    scan_tool_patterns: list[str] = Field(
        default_factory=_default_scan_tool_patterns,
        description="Command prefixes that should be annotated as scan tools.",
    )
    replace_grep_with_rg: bool = Field(
        default=True,
        description=(
            "Whether Bash commands containing GNU grep should be rewritten to ripgrep "
            "for better performance."
        ),
    )
    auto_install_ripgrep: bool = Field(
        default=False,
        description=(
            "Automatically install ripgrep without prompting when it is missing."
        ),
    )


DEFAULT_VISIBLE_TASK_SLOTS = 4
DEFAULT_BANNER_REFRESH_INTERVAL = 1.0


class TaskBannerConfig(BaseModel):
    """Shell task banner preferences."""

    visible_slots: int = Field(
        default=DEFAULT_VISIBLE_TASK_SLOTS,
        description="Maximum number of task heartbeat rows to display at once.",
    )
    refresh_interval: float = Field(
        default=DEFAULT_BANNER_REFRESH_INTERVAL,
        description="Seconds between automatic heartbeat refresh ticks.",
    )

    @model_validator(mode="after")
    def _clamp_values(self) -> "TaskBannerConfig":
        if self.visible_slots < 1:
            self.visible_slots = DEFAULT_VISIBLE_TASK_SLOTS
        if self.refresh_interval < 0.1:
            self.refresh_interval = DEFAULT_BANNER_REFRESH_INTERVAL
        return self


class ShellConfig(BaseModel):
    """Shell UI preferences."""

    task_banner: TaskBannerConfig = Field(
        default_factory=TaskBannerConfig, description="Heartbeat banner configuration."
    )


class Config(BaseModel):
    """Main configuration structure."""

    default_model: str = Field(default="", description="Default model to use")
    models: dict[str, LLMModel] = Field(default_factory=dict, description="List of LLM models")
    providers: dict[str, LLMProvider] = Field(
        default_factory=dict, description="List of LLM providers"
    )
    loop_control: LoopControl = Field(default_factory=LoopControl, description="Agent loop control")
    services: Services = Field(default_factory=Services, description="Services configuration")
    cli_output: CLIOutputConfig = Field(
        default_factory=CLIOutputConfig, description="CLI output preferences"
    )
    shell: ShellConfig = Field(default_factory=ShellConfig, description="Shell UI preferences")

    @model_validator(mode="after")
    def validate_model(self) -> Self:
        if self.default_model and self.default_model not in self.models:
            raise ValueError(f"Default model {self.default_model} not found in models")
        for model in self.models.values():
            if model.provider not in self.providers:
                raise ValueError(f"Provider {model.provider} not found in providers")
        return self


def get_config_file() -> Path:
    """Get the configuration file path."""
    return get_share_dir() / "config.json"


def get_default_config() -> Config:
    """Get the default configuration."""
    return Config(
        default_model="",
        models={},
        providers={},
        services=Services(),
    )


def load_config(config_file: Path | None = None) -> Config:
    """
    Load configuration from config file.
    If the config file does not exist, create it with default configuration.

    Args:
        config_file (Path | None): Path to the configuration file. If None, use default path.

    Returns:
        Validated Config object.

    Raises:
        ConfigError: If the configuration file is invalid.
    """
    config_file = config_file or get_config_file()
    logger.debug("Loading config from file: {file}", file=config_file)

    if not config_file.exists():
        config = get_default_config()
        logger.debug("No config file found, creating default config: {config}", config=config)
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(config.model_dump_json(indent=2, exclude_none=True))
        return config

    try:
        with open(config_file, encoding="utf-8") as f:
            data = json.load(f)
        return Config(**data)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in configuration file: {e}") from e
    except ValidationError as e:
        raise ConfigError(f"Invalid configuration file: {e}") from e


def save_config(config: Config, config_file: Path | None = None):
    """
    Save configuration to config file.

    Args:
        config (Config): Config object to save.
        config_file (Path | None): Path to the configuration file. If None, use default path.
    """
    config_file = config_file or get_config_file()
    logger.debug("Saving config to file: {file}", file=config_file)
    with open(config_file, "w", encoding="utf-8") as f:
        f.write(config.model_dump_json(indent=2, exclude_none=True))
