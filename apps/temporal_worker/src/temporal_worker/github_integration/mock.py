"""In-memory mock GitHub client for local development and tests."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from ._git import run_git
from .base import CloneResult, GitHubClient, PullRequest, RepoRef

logger = logging.getLogger(__name__)

_INITIAL_README = (
    "# Mock Repository\n\n"
    "Created by the mock GitHub backend. All edits are confined to the "
    "per-workflow workspace.\n"
)

_MOCK_AUTHOR_EMAIL = "bot@example.com"
_MOCK_AUTHOR_NAME = "Mock Bot"
_MOCK_PR_BASE_NUMBER = 1000
_MOCK_BASE_URL = "https://example.invalid"


class MockGitHubClient(GitHubClient):
    """Filesystem-only GitHubClient implementation for tests / demos."""

    def __init__(self) -> None:
        self._next_pr_number = _MOCK_PR_BASE_NUMBER
        self._lock = asyncio.Lock()

    async def clone(self, repo: RepoRef, branch: str, dest: Path) -> CloneResult:
        dest.mkdir(parents=True, exist_ok=True)
        await run_git(["init", "--initial-branch", branch], cwd=dest)
        readme = dest / "README.md"
        readme.write_text(_INITIAL_README)
        await run_git(["add", "README.md"], cwd=dest)
        await run_git(
            [
                "-c",
                f"user.email={_MOCK_AUTHOR_EMAIL}",
                "-c",
                f"user.name={_MOCK_AUTHOR_NAME}",
                "commit",
                "-m",
                "chore: seed mock repo",
            ],
            cwd=dest,
        )
        head = (await run_git(["rev-parse", "HEAD"], cwd=dest)).strip()
        logger.info("mock clone for %s @ %s -> %s", repo.slug, branch, dest)
        return CloneResult(path=dest, head_sha=head)

    async def create_branch(self, repo: RepoRef, base_branch: str, new_branch: str) -> str:
        logger.info("mock create branch %s from %s on %s", new_branch, base_branch, repo.slug)
        return new_branch

    async def commit_and_push(
        self,
        repo: RepoRef,
        repo_path: Path,
        branch: str,
        message: str,
        author_name: str,
        author_email: str,
    ) -> str:
        await run_git(["checkout", "-B", branch], cwd=repo_path)
        await run_git(["add", "-A"], cwd=repo_path)
        # --allow-empty keeps the workflow uniform when the agent makes no changes.
        await run_git(
            [
                "-c",
                f"user.email={author_email}",
                "-c",
                f"user.name={author_name}",
                "commit",
                "--allow-empty",
                "-m",
                message,
            ],
            cwd=repo_path,
        )
        sha = (await run_git(["rev-parse", "HEAD"], cwd=repo_path)).strip()
        logger.info("mock commit on %s@%s -> %s", repo.slug, branch, sha)
        return sha

    async def open_pull_request(
        self,
        repo: RepoRef,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> PullRequest:
        async with self._lock:
            self._next_pr_number += 1
            number = self._next_pr_number
        url = f"{_MOCK_BASE_URL}/{repo.slug}/pull/{number}"
        logger.info("mock PR opened: %s", url)
        return PullRequest(number=number, url=url, branch=head_branch, title=title)
