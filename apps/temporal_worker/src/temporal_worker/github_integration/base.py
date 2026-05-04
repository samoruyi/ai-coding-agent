"""Protocol + value types for the GitHub integration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class RepoRef:
    owner: str
    name: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"


@dataclass(frozen=True)
class CloneResult:
    """Result of a ``clone`` operation."""

    path: Path
    head_sha: str


@dataclass(frozen=True)
class PullRequest:
    number: int
    url: str
    branch: str
    title: str


class GitHubClient(Protocol):
    """Minimal GitHub surface used by the platform; both real and mock implement this."""

    async def clone(self, repo: RepoRef, branch: str, dest: Path) -> CloneResult: ...

    async def create_branch(self, repo: RepoRef, base_branch: str, new_branch: str) -> str: ...

    async def commit_and_push(
        self,
        repo: RepoRef,
        repo_path: Path,
        branch: str,
        message: str,
        author_name: str,
        author_email: str,
    ) -> str: ...

    async def open_pull_request(
        self,
        repo: RepoRef,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> PullRequest: ...
