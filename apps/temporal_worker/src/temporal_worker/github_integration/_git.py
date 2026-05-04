"""Async git CLI wrapper shared by the real and mock GitHub clients."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path


class GitCommandError(RuntimeError):
    """Raised when a ``git`` invocation exits non-zero."""

    def __init__(self, args: list[str], returncode: int, stderr: str) -> None:
        self.args = args
        self.returncode = returncode
        self.stderr = stderr.strip()
        super().__init__(f"git {' '.join(args)} failed ({returncode}): {self.stderr}")


async def run_git(args: list[str], *, cwd: Path | None = None) -> str:
    """Run ``git <args>`` and return stdout; raise ``GitCommandError`` on non-zero exit."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise GitCommandError(args, proc.returncode or -1, stderr.decode())
    return stdout.decode()
