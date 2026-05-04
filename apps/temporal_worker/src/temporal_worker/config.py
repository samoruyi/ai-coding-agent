"""Worker settings loaded from environment variables."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    """Strongly-typed worker configuration."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    agent_model: str = Field(
        default="anthropic:claude-opus-4-7",
        description="Pydantic AI model spec, e.g. 'anthropic:claude-opus-4-7'.",
    )
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    temporal_address: str = "temporal:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "coding-agent"
    temporal_tls: bool = False
    temporal_tls_cert_path: Path | None = None
    temporal_tls_key_path: Path | None = None

    worker_max_concurrent_activities: int = Field(default=20, ge=1, le=500)
    worker_max_concurrent_workflow_tasks: int = Field(default=20, ge=1, le=500)

    slack_bot_token: str | None = None

    github_mode: Literal["mock", "real"] = "mock"
    github_token: str | None = None
    github_default_owner: str | None = None
    github_default_repo: str | None = None
    github_api_base: str = "https://api.github.com"

    log_level: str = "INFO"
    agent_workspace_root: Path = Path("/var/agent/workspaces")

    agent_max_iterations: int = Field(default=20, ge=1, le=100)
    agent_timeout_seconds: int = Field(default=900, ge=30, le=7200)
    agent_shell_allowlist: str = (
        "ls,cat,head,tail,wc,grep,rg,find,git,python,python3,pytest,node,npm,pnpm"
    )

    @field_validator("agent_shell_allowlist")
    @classmethod
    def _validate_allowlist(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("AGENT_SHELL_ALLOWLIST must not be empty")
        return value

    @property
    def shell_allowlist(self) -> frozenset[str]:
        """Parsed, deduplicated set of allowed shell program names."""
        return frozenset(c.strip() for c in self.agent_shell_allowlist.split(",") if c.strip())


_settings: WorkerSettings | None = None


def get_settings() -> WorkerSettings:
    """Return the process-wide settings singleton."""
    global _settings
    if _settings is None:
        _settings = WorkerSettings()
    return _settings


def reset_settings() -> None:
    """Drop the cached singleton; intended for tests."""
    global _settings
    _settings = None
