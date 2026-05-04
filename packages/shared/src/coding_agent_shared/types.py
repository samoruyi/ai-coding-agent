"""Workflow contract: types shared by the gateway and worker."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TASK_QUEUE_DEFAULT = "coding-agent"


class SlackContext(BaseModel):
    """Slack identifiers used to route replies and isolate sessions."""

    model_config = ConfigDict(frozen=True)

    team_id: str
    channel_id: str
    thread_ts: str = Field(description="Slack thread timestamp; the root message ts.")
    user_id: str = Field(description="Slack user who triggered the request.")
    response_url: str | None = Field(default=None)


class AgentRequest(BaseModel):
    """Input payload for ``CodingAgentWorkflow``."""

    prompt: str = Field(description="Natural-language coding request.")
    repo_owner: str | None = Field(default=None)
    repo_name: str | None = Field(default=None)
    base_branch: str = "main"
    slack: SlackContext

    @property
    def repo_slug(self) -> str:
        return f"{self.repo_owner or '<default>'}/{self.repo_name or '<default>'}"


class AgentStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_FOLLOWUP = "awaiting_followup"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProgressUpdate(BaseModel):
    """Streaming progress emitted by the workflow to Slack."""

    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    kind: Literal["log", "tool_call", "thinking", "error"] = "log"
    message: str


class FollowUpSignal(BaseModel):
    """Signal payload for follow-up messages in the same Slack thread."""

    message: str
    user_id: str


class AgentResponse(BaseModel):
    """Final result returned by ``CodingAgentWorkflow``."""

    status: AgentStatus
    summary: str = ""
    pr_url: str | None = None
    branch: str | None = None
    iterations: int = 0
    error: str | None = None


def workflow_id_for_thread(slack: SlackContext) -> str:
    """Deterministic workflow id per Slack thread; the basis of session isolation."""
    return f"slack-{slack.team_id}-{slack.channel_id}-{slack.thread_ts}"
