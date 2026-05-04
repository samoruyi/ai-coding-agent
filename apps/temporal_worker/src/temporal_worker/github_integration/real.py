"""Real GitHub client (REST via httpx + git CLI for code I/O)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx

from ._git import run_git
from .base import CloneResult, GitHubClient, PullRequest, RepoRef

logger = logging.getLogger(__name__)

DEFAULT_API_BASE: str = "https://api.github.com"
DEFAULT_TIMEOUT_SECONDS: float = 30.0
GITHUB_API_VERSION: str = "2022-11-28"


class RealGitHubClient(GitHubClient):
    """``GitHubClient`` implementation backed by api.github.com + git CLI."""

    def __init__(
        self,
        token: str,
        api_base: str = DEFAULT_API_BASE,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not token:
            raise ValueError("RealGitHubClient requires a non-empty token")
        self._token = token
        self._api_base = api_base.rstrip("/")
        self._timeout = timeout_seconds

    async def clone(self, repo: RepoRef, branch: str, dest: Path) -> CloneResult:
        """Shallow-clone ``repo`` at ``branch`` into ``dest``."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://x-access-token:{self._token}@github.com/{repo.slug}.git"
        await run_git(["clone", "--depth=1", "--branch", branch, url, str(dest)])
        head = (await run_git(["rev-parse", "HEAD"], cwd=dest)).strip()
        return CloneResult(path=dest, head_sha=head)

    async def create_branch(self, repo: RepoRef, base_branch: str, new_branch: str) -> str:
        """Create ``new_branch`` from ``base_branch`` via the Refs API.

        Status 422 is treated as success because it covers the
        "ref already exists" case from a previous activity attempt.
        """
        base_sha = await self._get_ref_sha(repo, base_branch)
        await self._post(
            f"/repos/{repo.slug}/git/refs",
            json={"ref": f"refs/heads/{new_branch}", "sha": base_sha},
            ok_statuses=(201, 422),
        )
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
        """Commit working-tree changes and push the branch."""
        await run_git(["checkout", "-B", branch], cwd=repo_path)
        await run_git(["add", "-A"], cwd=repo_path)
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
        await run_git(["push", "--force-with-lease", "origin", branch], cwd=repo_path)
        return (await run_git(["rev-parse", "HEAD"], cwd=repo_path)).strip()

    async def open_pull_request(
        self,
        repo: RepoRef,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> PullRequest:
        """Open a pull request; raises on API failure."""
        data = await self._post(
            f"/repos/{repo.slug}/pulls",
            json={"title": title, "head": head_branch, "base": base_branch, "body": body},
            ok_statuses=(201,),
        )
        return PullRequest(
            number=data["number"],
            url=data["html_url"],
            branch=head_branch,
            title=title,
        )

    async def _get_ref_sha(self, repo: RepoRef, branch: str) -> str:
        async with self._http() as client:
            resp = await client.get(f"/repos/{repo.slug}/git/ref/heads/{branch}")
            resp.raise_for_status()
            return resp.json()["object"]["sha"]

    async def _post(
        self,
        path: str,
        *,
        json: dict[str, Any],
        ok_statuses: tuple[int, ...] = (200, 201),
    ) -> dict[str, Any]:
        async with self._http() as client:
            resp = await client.post(path, json=json)
            if resp.status_code not in ok_statuses:
                resp.raise_for_status()
            try:
                return resp.json()
            except ValueError:
                return {}

    def _http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._api_base,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
            },
            timeout=self._timeout,
        )
