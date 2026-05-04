"""GitHub integration with a swappable backend (real or mock)."""

from .base import CloneResult, GitHubClient, PullRequest, RepoRef
from .factory import build_client

__all__ = [
    "CloneResult",
    "GitHubClient",
    "PullRequest",
    "RepoRef",
    "build_client",
]
