"""Tools exposed to the Pydantic AI agent.

All tools route through ``ToolBinding.workspace.resolve(...)`` so they
cannot read or write outside the per-workflow sandbox.
"""

from __future__ import annotations

import asyncio
import logging
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..workspace import Workspace

logger = logging.getLogger(__name__)


MAX_FILE_BYTES: int = 256 * 1024
MAX_LIST_ENTRIES: int = 200
SHELL_TIMEOUT_SECONDS: int = 60
SHELL_OUTPUT_TRUNCATION_MARKER: str = "\n... (output truncated)"
SUBPROCESS_PATH: str = "/usr/local/bin:/usr/bin:/bin"


@dataclass(frozen=True)
class ToolBinding:
    """Per-call inputs every tool needs."""

    workspace: Workspace
    shell_allowlist: frozenset[str]


def _resolve_or_error(binding: ToolBinding, path: str) -> Path | str:
    """Resolve ``path`` inside the workspace, or return an LLM-friendly error string."""
    try:
        return binding.workspace.resolve(path)
    except ValueError as exc:
        return f"ERROR: {exc}"


async def read_file(binding: ToolBinding, path: str) -> str:
    """Return the contents of a UTF-8 text file from the workspace."""
    if not path:
        return "ERROR: path is empty"
    resolved = _resolve_or_error(binding, path)
    if isinstance(resolved, str):
        return resolved
    if not resolved.exists():
        return f"ERROR: file not found: {path}"
    if not resolved.is_file():
        return f"ERROR: not a file: {path}"
    size = resolved.stat().st_size
    if size > MAX_FILE_BYTES:
        return f"ERROR: file too large ({size} bytes); max {MAX_FILE_BYTES}"
    try:
        return resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "ERROR: file is not valid UTF-8"


async def write_file(binding: ToolBinding, path: str, content: str) -> str:
    """Create or overwrite a UTF-8 text file inside the workspace."""
    if not path:
        return "ERROR: path is empty"
    encoded_size = len(content.encode("utf-8"))
    if encoded_size > MAX_FILE_BYTES:
        return f"ERROR: content too large ({encoded_size} bytes); max {MAX_FILE_BYTES}"
    resolved = _resolve_or_error(binding, path)
    if isinstance(resolved, str):
        return resolved
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    return f"OK: wrote {len(content)} chars to {path}"


async def list_dir(binding: ToolBinding, path: str = ".") -> str:
    """List directory entries (one per line) within the workspace."""
    resolved = _resolve_or_error(binding, path)
    if isinstance(resolved, str):
        return resolved
    if not resolved.exists():
        return f"ERROR: not found: {path}"
    if not resolved.is_dir():
        return f"ERROR: not a directory: {path}"

    entries: list[str] = []
    for index, entry in enumerate(sorted(resolved.iterdir())):
        if index >= MAX_LIST_ENTRIES:
            entries.append(f"... (truncated at {MAX_LIST_ENTRIES} entries)")
            break
        suffix = "/" if entry.is_dir() else ""
        entries.append(f"{entry.name}{suffix}")
    return "\n".join(entries) or "(empty)"


async def run_shell(binding: ToolBinding, command: str) -> str:
    """Run a single allowlisted command inside the workspace.

    The command is parsed with ``shlex.split``; the first token must
    appear in ``binding.shell_allowlist``. Shell metacharacters
    (``&&``, ``;``, pipes) are not honored.
    """
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return f"ERROR: could not parse command: {exc}"
    if not argv:
        return "ERROR: empty command"

    program = argv[0]
    if program not in binding.shell_allowlist:
        return (
            f"ERROR: program {program!r} is not in the allowlist. "
            f"Allowed: {sorted(binding.shell_allowlist)}"
        )

    logger.info("agent shell: %s", argv)
    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                *argv,
                cwd=str(binding.workspace.root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env={"PATH": SUBPROCESS_PATH},
            ),
            timeout=SHELL_TIMEOUT_SECONDS,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=SHELL_TIMEOUT_SECONDS)
    except TimeoutError:
        return f"ERROR: command timed out after {SHELL_TIMEOUT_SECONDS}s"

    text = stdout.decode("utf-8", errors="replace")
    if len(text) > MAX_FILE_BYTES:
        text = text[:MAX_FILE_BYTES] + SHELL_OUTPUT_TRUNCATION_MARKER
    return f"exit={proc.returncode}\n{text}"
