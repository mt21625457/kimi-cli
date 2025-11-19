from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class RunOptions(BaseModel):
    """Optional toggles for each run."""

    yolo: bool = Field(default=True, description="Approve tools automatically")
    thinking: bool = Field(default=False, description="Enable thinking mode if available")


class RunRequest(BaseModel):
    """Incoming payload for POST /api/v1/runs."""

    command: str
    work_dir: Path
    agent_file: Path | None = None
    model_name: str | None = None
    config_file: Path | None = None
    env: dict[str, str | Any] = Field(default_factory=dict)
    options: RunOptions = Field(default_factory=RunOptions)
    stream: bool = Field(default=True)

    @field_validator("command")
    @classmethod
    def _validate_command(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("command cannot be empty")
        return value

    @model_validator(mode="after")
    def _normalize(self) -> "RunRequest":
        self.work_dir = self.work_dir.expanduser().resolve()
        if self.agent_file is not None:
            self.agent_file = Path(self.agent_file).expanduser().resolve()
        if self.config_file is not None:
            self.config_file = Path(self.config_file).expanduser().resolve()

        normalized_env: dict[str, str] = {}
        for key, value in (self.env or {}).items():
            if not key:
                continue
            normalized_env[key.upper()] = str(value)
        self.env = normalized_env
        return self


class CancelResponse(BaseModel):
    """Response body for cancel API."""

    run_id: str
    status: str


class HealthResponse(BaseModel):
    status: str
    version: str
