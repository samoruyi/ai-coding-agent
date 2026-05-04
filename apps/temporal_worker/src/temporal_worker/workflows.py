"""Temporal workflow definitions."""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from coding_agent_shared import (
        AgentRequest,
        AgentResponse,
        AgentStatus,
        FollowUpSignal,
    )

    from .activities import (
        CleanupWorkspaceInput,
        CloneRepoInput,
        CloneRepoOutput,
        CommitAndPrInput,
        CommitAndPrOutput,
        RunAgentInput,
        SetupWorkspaceInput,
        SlackPostInput,
        cleanup_workspace,
        clone_repo,
        commit_and_open_pr,
        post_slack_message,
        run_agent,
        setup_workspace,
    )


SETUP_WORKSPACE_TIMEOUT = timedelta(seconds=30)
CLONE_REPO_TIMEOUT = timedelta(minutes=5)
COMMIT_AND_PR_TIMEOUT = timedelta(minutes=5)
CLEANUP_TIMEOUT = timedelta(seconds=30)
SLACK_POST_TIMEOUT = timedelta(seconds=15)
AGENT_RUN_TIMEOUT = timedelta(minutes=15)
AGENT_HEARTBEAT_TIMEOUT = timedelta(seconds=120)
FOLLOWUP_WAIT = timedelta(seconds=20)

PROMPT_TITLE_CHARS = 60
PROMPT_COMMIT_CHARS = 72
WORKFLOW_ID_TAIL_CHARS = 8
BRANCH_SLUG_MAX_CHARS = 40

DEFAULT_REPO_OWNER = "_default_"
DEFAULT_REPO_NAME = "_default_"

_DEFAULT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=3,
)
# LLM calls cost money; user re-triggers explicitly instead of automatic retries.
_AGENT_RETRY = RetryPolicy(maximum_attempts=1)
_BEST_EFFORT_RETRY = RetryPolicy(maximum_attempts=2)


@workflow.defn(name="CodingAgentWorkflow")
class CodingAgentWorkflow:
    """One workflow per Slack thread.

    State machine: ``pending -> running -> awaiting_followup* -> succeeded``.
    On unhandled exception the workflow transitions to ``failed`` and posts
    the error to Slack before returning.
    """

    def __init__(self) -> None:
        self._status: AgentStatus = AgentStatus.PENDING
        self._followups: list[FollowUpSignal] = []
        self._latest_summary: str = ""

    @workflow.signal(name="follow_up")
    async def on_followup(self, signal: FollowUpSignal) -> None:
        """Queue a follow-up message for the next agent iteration."""
        self._followups.append(signal)

    @workflow.query(name="status")
    def get_status(self) -> str:
        """Return the workflow's current ``AgentStatus`` as a string."""
        return self._status.value

    @workflow.query(name="summary")
    def get_summary(self) -> str:
        """Return the latest agent summary."""
        return self._latest_summary

    @workflow.run
    async def run(self, request: AgentRequest) -> AgentResponse:
        self._status = AgentStatus.RUNNING
        wf_id = workflow.info().workflow_id

        await self._post(request, f":robot_face: Working on: _{request.prompt}_")

        workspace_path: str | None = None
        repo_path: str | None = None
        iterations = 0
        try:
            workspace_path = await workflow.execute_activity(
                setup_workspace,
                SetupWorkspaceInput(workflow_id=wf_id),
                start_to_close_timeout=SETUP_WORKSPACE_TIMEOUT,
                retry_policy=_DEFAULT_RETRY,
            )

            repo_owner = request.repo_owner or DEFAULT_REPO_OWNER
            repo_name = request.repo_name or DEFAULT_REPO_NAME
            clone_out: CloneRepoOutput = await workflow.execute_activity(
                clone_repo,
                CloneRepoInput(
                    workflow_id=wf_id,
                    workspace_path=workspace_path,
                    repo_owner=repo_owner,
                    repo_name=repo_name,
                    branch=request.base_branch,
                ),
                start_to_close_timeout=CLONE_REPO_TIMEOUT,
                retry_policy=_DEFAULT_RETRY,
            )
            repo_path = clone_out.workspace_path
            await self._post(
                request,
                f":inbox_tray: Cloned `{repo_owner}/{repo_name}@{request.base_branch}`",
            )

            current_prompt = request.prompt
            while True:
                iterations += 1
                await self._post(request, f":hammer_and_wrench: Iteration {iterations} starting")

                agent_result = await workflow.execute_activity(
                    run_agent,
                    RunAgentInput(workspace_path=repo_path, prompt=current_prompt),
                    start_to_close_timeout=AGENT_RUN_TIMEOUT,
                    heartbeat_timeout=AGENT_HEARTBEAT_TIMEOUT,
                    retry_policy=_AGENT_RETRY,
                )
                self._latest_summary = agent_result.summary

                self._status = AgentStatus.AWAITING_FOLLOWUP
                await self._post(
                    request,
                    f":memo: *Iteration {iterations} summary:*\n{agent_result.summary}",
                )
                got_followup = await self._await_followup()
                self._status = AgentStatus.RUNNING
                if not got_followup:
                    break
                current_prompt = self._followups.pop(0).message

            new_branch = f"agent/{_branch_slug(request.prompt)}-{wf_id[-WORKFLOW_ID_TAIL_CHARS:]}"
            pr_title = f"agent: {request.prompt[:PROMPT_TITLE_CHARS]}"
            pr_body = (
                f"Automated change by the coding agent.\n\n"
                f"**Original request:** {request.prompt}\n\n"
                f"**Summary:**\n{self._latest_summary}\n\n"
                f"_Workflow:_ `{wf_id}`"
            )
            commit_message = f"agent: {request.prompt[:PROMPT_COMMIT_CHARS]}"

            pr_out: CommitAndPrOutput = await workflow.execute_activity(
                commit_and_open_pr,
                CommitAndPrInput(
                    workspace_path=repo_path,
                    repo_owner=repo_owner,
                    repo_name=repo_name,
                    base_branch=request.base_branch,
                    new_branch=new_branch,
                    pr_title=pr_title,
                    pr_body=pr_body,
                    commit_message=commit_message,
                ),
                start_to_close_timeout=COMMIT_AND_PR_TIMEOUT,
                retry_policy=_DEFAULT_RETRY,
            )
            await self._post(
                request,
                f":white_check_mark: Opened PR <{pr_out.pr_url}|#{pr_out.pr_number}> "
                f"on branch `{pr_out.branch}`",
            )

            self._status = AgentStatus.SUCCEEDED
            return AgentResponse(
                status=AgentStatus.SUCCEEDED,
                summary=self._latest_summary,
                pr_url=pr_out.pr_url,
                branch=pr_out.branch,
                iterations=iterations,
            )

        except Exception as exc:  # noqa: BLE001
            self._status = AgentStatus.FAILED
            await self._post(request, f":x: Workflow failed: `{type(exc).__name__}: {exc}`")
            return AgentResponse(
                status=AgentStatus.FAILED,
                summary=self._latest_summary,
                iterations=iterations,
                error=f"{type(exc).__name__}: {exc}",
            )
        finally:
            if workspace_path:
                await self._cleanup(workspace_path)

    async def _await_followup(self) -> bool:
        """Wait briefly for a follow-up signal; True if one arrived."""
        try:
            await workflow.wait_condition(
                lambda: len(self._followups) > 0,
                timeout=FOLLOWUP_WAIT,
            )
            return True
        except TimeoutError:
            return False

    async def _post(self, request: AgentRequest, text: str) -> None:
        """Post a thread reply via the ``post_slack_message`` activity."""
        try:
            await workflow.execute_activity(
                post_slack_message,
                SlackPostInput(slack=request.slack, text=text),
                start_to_close_timeout=SLACK_POST_TIMEOUT,
                retry_policy=_BEST_EFFORT_RETRY,
            )
        except Exception:  # noqa: BLE001
            workflow.logger.warning("slack post failed; continuing")

    async def _cleanup(self, workspace_path: str) -> None:
        """Best-effort workspace cleanup."""
        try:
            await workflow.execute_activity(
                cleanup_workspace,
                CleanupWorkspaceInput(workspace_path=workspace_path),
                start_to_close_timeout=CLEANUP_TIMEOUT,
                retry_policy=_BEST_EFFORT_RETRY,
            )
        except Exception:  # noqa: BLE001
            workflow.logger.warning("workspace cleanup failed; ignoring")


def _branch_slug(text: str) -> str:
    """Deterministic slug builder; safe to call from workflow code."""
    out: list[str] = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    slug = "".join(out).strip("-")
    return slug[:BRANCH_SLUG_MAX_CHARS] or "task"
