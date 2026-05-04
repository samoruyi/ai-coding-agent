"""Picks the GitHub backend based on env config."""

from __future__ import annotations

import logging

from ..config import get_settings
from .base import GitHubClient
from .mock import MockGitHubClient
from .real import RealGitHubClient

logger = logging.getLogger(__name__)


def build_client() -> GitHubClient:
    settings = get_settings()
    if settings.github_mode == "real":
        if not settings.github_token:
            raise RuntimeError(
                "GITHUB_MODE=real but GITHUB_TOKEN is not set. "
                "Set the token, or switch to GITHUB_MODE=mock."
            )
        logger.info("Using real GitHub client (api_base=%s)", settings.github_api_base)
        return RealGitHubClient(token=settings.github_token, api_base=settings.github_api_base)
    logger.info("Using mock GitHub client")
    return MockGitHubClient()
