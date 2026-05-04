"""Pydantic AI coding agent."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from .tools import ToolBinding, list_dir, read_file, run_shell, write_file

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
You are a senior software engineer working inside a sandboxed workspace.

Goals:
  * Understand the user's request, then make the smallest correct code change.
  * Use the provided tools (read_file, write_file, list_dir, run_shell) to
    explore the repository and apply edits.
  * Use `run_shell` to run tests / linters when the change warrants it.

Hard rules:
  * Never assume a file exists; list_dir or read_file first.
  * Keep edits minimal and targeted; do not reformat unrelated code.
  * If you are blocked or the request is ambiguous, stop and explain.
  * When you are done, return a JSON object describing what you did.
"""

DEFAULT_MAX_ITERATIONS: int = 20
DEFAULT_AGENT_RETRIES: int = 1


class CodingAgentResult(BaseModel):
    """Structured output the model is required to return."""

    summary: str = Field(description="One-paragraph summary of what was done.")
    changed_files: list[str] = Field(
        default_factory=list,
        description="Workspace-relative paths the agent modified.",
    )
    tests_run: bool = Field(default=False, description="True if the agent ran tests/linters.")
    notes: str | None = Field(default=None, description="Caveats or follow-up suggestions.")


@dataclass(frozen=True)
class _AgentDeps:
    binding: ToolBinding


class CodingAgent:
    """Wrapper around a Pydantic AI ``Agent`` with file/shell tools registered."""

    def __init__(
        self,
        model: str,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
    ) -> None:
        if not model:
            raise ValueError("model must be a non-empty Pydantic AI model spec")
        if max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")

        self._max_iterations = max_iterations
        self._agent: Agent[_AgentDeps, CodingAgentResult] = Agent(
            model,
            deps_type=_AgentDeps,
            output_type=CodingAgentResult,
            system_prompt=SYSTEM_PROMPT,
            retries=DEFAULT_AGENT_RETRIES,
        )
        self._register_tools()

    def _register_tools(self) -> None:
        @self._agent.tool
        async def read_file_tool(ctx: RunContext[_AgentDeps], path: str) -> str:
            """Read a UTF-8 text file relative to the workspace root."""
            return await read_file(ctx.deps.binding, path)

        @self._agent.tool
        async def write_file_tool(ctx: RunContext[_AgentDeps], path: str, content: str) -> str:
            """Create or overwrite a UTF-8 text file relative to the workspace root."""
            return await write_file(ctx.deps.binding, path, content)

        @self._agent.tool
        async def list_dir_tool(ctx: RunContext[_AgentDeps], path: str = ".") -> str:
            """List directory entries relative to the workspace root."""
            return await list_dir(ctx.deps.binding, path)

        @self._agent.tool
        async def run_shell_tool(ctx: RunContext[_AgentDeps], command: str) -> str:
            """Run a single allowlisted command (e.g. ``pytest -x``, ``git diff``)."""
            return await run_shell(ctx.deps.binding, command)

    async def run(self, prompt: str, binding: ToolBinding) -> CodingAgentResult:
        """Drive the LLM tool-call loop until a structured result is returned."""
        if not prompt.strip():
            raise ValueError("prompt must be non-empty")
        logger.info("running coding agent (max_iter=%d)", self._max_iterations)
        result = await self._agent.run(prompt, deps=_AgentDeps(binding=binding))
        return result.output
