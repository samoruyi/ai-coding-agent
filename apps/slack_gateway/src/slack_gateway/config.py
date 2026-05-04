"""Slack gateway configuration loaded from environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    """Strongly-typed gateway configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    slack_gateway_port: int = Field(default=8080, ge=1, le=65535)
    log_level: str = "INFO"

    slack_bot_token: str = Field(default="", description="xoxb-... bot token")
    slack_signing_secret: str = Field(default="", description="App signing secret")
    slack_socket_mode: bool = False
    slack_app_token: str | None = None

    temporal_address: str = "temporal:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "coding-agent"
    temporal_tls: bool = False

    github_default_owner: str | None = None
    github_default_repo: str | None = None


_settings: GatewaySettings | None = None


def get_settings() -> GatewaySettings:
    """Return the process-wide gateway settings singleton."""
    global _settings
    if _settings is None:
        _settings = GatewaySettings()
    return _settings


def reset_settings() -> None:
    """Drop the cached singleton; only useful in tests."""
    global _settings
    _settings = None
