"""Per-workflow filesystem workspaces."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_SAFE_PATH_CHARS: frozenset[str] = frozenset("-_.")


@dataclass(frozen=True)
class Workspace:
    """A single per-workflow workspace rooted at ``root``."""

    workflow_id: str
    root: Path

    def resolve(self, relative_path: str) -> Path:
        """Resolve ``relative_path`` inside the workspace; raise on traversal."""
        if relative_path is None:
            raise ValueError("relative_path must not be None")
        cleaned = relative_path.lstrip("/")
        candidate = (self.root / cleaned).resolve()
        try:
            candidate.relative_to(self.root.resolve())
        except ValueError as exc:
            raise ValueError(
                f"Path {relative_path!r} resolves outside workspace {self.root}"
            ) from exc
        return candidate


class WorkspaceManager:
    """Creates and tears down per-workflow workspaces under a single root."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, workflow_id: str) -> Workspace:
        """Create a fresh workspace; the workflow id is sanitized for FS safety."""
        if not workflow_id:
            raise ValueError("workflow_id must be non-empty")
        safe = "".join(c if c.isalnum() or c in _SAFE_PATH_CHARS else "_" for c in workflow_id)
        path = self.root / safe
        path.mkdir(parents=True, exist_ok=True)
        logger.info("created workspace %s", path)
        return Workspace(workflow_id=workflow_id, root=path)

    def destroy(self, workspace: Workspace) -> None:
        """Remove the workspace from disk; log-and-swallow on failure."""
        try:
            shutil.rmtree(workspace.root, ignore_errors=True)
            logger.info("destroyed workspace %s", workspace.root)
        except OSError as exc:
            logger.warning("failed to clean workspace: %s", exc)
