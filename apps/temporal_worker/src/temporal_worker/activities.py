"""Temporal activities: all I/O lives here, never in workflow code."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from coding_agent_shared import SlackContext
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from temporalio import activity

from .agent.coding_agent import CodingAgent, CodingAgentResult
from .agent.tools import ToolBinding
from .config import WorkerSettings, get_settings
from .github_integration import RepoRef, build_client
from .workspace import Workspace, WorkspaceManager

logger = logging.getLogger(__name__)


COMMIT_AUTHOR_NAME = "coding-agent-bot"
COMMIT_AUTHOR_EMAIL = "coding-agent-bot@users.noreply.github.com"
SLACK_PREVIEW_CHARS = 80


@dataclass
class SetupWorkspaceInput:
    workflow_id: str


@dataclass
class CloneRepoInput:
    workflow_id: str
    workspace_path: str
    repo_owner: str
    repo_name: str
    branch: str


@dataclass
class CloneRepoOutput:
    workspace_path: str
    head_sha: str


@dataclass
class RunAgentInput:
    workspace_path: str
    prompt: str


@dataclass
class CommitAndPrInput:
    workspace_path: str
    repo_owner: str
    repo_name: str
    base_branch: str
    new_branch: str
    pr_title: str
    pr_body: str
    commit_message: str


@dataclass
class CommitAndPrOutput:
    pr_url: str
    pr_number: int
    branch: str
    head_sha: str


@dataclass
class SlackPostInput:
    slack: SlackContext
    text: str


@dataclass
class CleanupWorkspaceInput:
    workspace_path: str


_workspace_manager: WorkspaceManager | None = None


def _get_workspace_manager(settings: WorkerSettings) -> WorkspaceManager:
    """Return the per-process workspace manager, creating it on first use."""
    global _workspace_manager
    if _workspace_manager is None:
        _workspace_manager = WorkspaceManager(settings.agent_workspace_root)
    return _workspace_manager


@activity.defn
async def setup_workspace(payload: SetupWorkspaceInput) -> str:
    """Create the per-workflow scratch directory and return its path."""
    workspace = _get_workspace_manager(get_settings()).create(payload.workflow_id)
    return str(workspace.root)


@activity.defn
async def clone_repo(payload: CloneRepoInput) -> CloneRepoOutput:
    """Clone the requested repo into ``<workspace>/repo``."""
    client = build_client()
    repo = RepoRef(owner=payload.repo_owner, name=payload.repo_name)
    dest = Path(payload.workspace_path) / "repo"
    result = await client.clone(repo, payload.branch, dest)
    logger.info("cloned %s @ %s -> %s", repo.slug, payload.branch, dest)
    return CloneRepoOutput(workspace_path=str(dest), head_sha=result.head_sha)


@activity.defn
async def run_agent(payload: RunAgentInput) -> CodingAgentResult:
    """Run the Pydantic AI coding agent inside ``payload.workspace_path``."""
    settings = get_settings()
    workspace = Workspace(
        workflow_id=activity.info().workflow_id,
        root=Path(payload.workspace_path),
    )
    binding = ToolBinding(workspace=workspace, shell_allowlist=settings.shell_allowlist)
    agent = CodingAgent(model=settings.agent_model, max_iterations=settings.agent_max_iterations)

    activity.heartbeat("agent starting")
    result = await agent.run(payload.prompt, binding=binding)
    activity.heartbeat("agent done")
    return result


@activity.defn
async def commit_and_open_pr(payload: CommitAndPrInput) -> CommitAndPrOutput:
    """Commit the agent's changes, push the branch, and open a pull request."""
    client = build_client()
    repo = RepoRef(owner=payload.repo_owner, name=payload.repo_name)

    sha = await client.commit_and_push(
        repo=repo,
        repo_path=Path(payload.workspace_path),
        branch=payload.new_branch,
        message=payload.commit_message,
        author_name=COMMIT_AUTHOR_NAME,
        author_email=COMMIT_AUTHOR_EMAIL,
    )
    pr = await client.open_pull_request(
        repo=repo,
        head_branch=payload.new_branch,
        base_branch=payload.base_branch,
        title=payload.pr_title,
        body=payload.pr_body,
    )
    return CommitAndPrOutput(pr_url=pr.url, pr_number=pr.number, branch=pr.branch, head_sha=sha)


@activity.defn
async def post_slack_message(payload: SlackPostInput) -> None:
    """Post a thread reply back to Slack."""
    settings = get_settings()
    if not settings.slack_bot_token:
        logger.warning(
            "SLACK_BOT_TOKEN not set; skipping Slack post: %s",
            payload.text[:SLACK_PREVIEW_CHARS],
        )
        return

    client = WebClient(token=settings.slack_bot_token)
    try:
        client.chat_postMessage(
            channel=payload.slack.channel_id,
            thread_ts=payload.slack.thread_ts,
            text=payload.text,
        )
    except SlackApiError as exc:
        logger.error("slack post failed: %s", exc.response.get("error"))
        raise


@activity.defn
async def cleanup_workspace(payload: CleanupWorkspaceInput) -> None:
    """Remove the per-workflow scratch directory if it still exists."""
    path = Path(payload.workspace_path)
    if not path.exists():
        return
    workspace = Workspace(workflow_id=activity.info().workflow_id, root=path)
    _get_workspace_manager(get_settings()).destroy(workspace)
