# syntax=docker/dockerfile:1.7
# -----------------------------------------------------------------------------
# Temporal worker image. Multi-stage; the final image runs as non-root.
# Build context must be the repo root (the uv workspace root):
#
#   docker build -f apps/temporal_worker/Dockerfile -t temporal-worker:dev .
#
# We use uv (https://docs.astral.sh/uv/) for installs - significantly
# faster than pip, deterministic via uv.lock, and a first-class
# workspace concept that fits this monorepo.
# -----------------------------------------------------------------------------

ARG PYTHON_VERSION=3.12-slim-bookworm
ARG UV_VERSION=0.5.13

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# --- Builder ----------------------------------------------------------------
FROM python:${PYTHON_VERSION} AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

COPY --from=uv /uv /usr/local/bin/uv

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Bring in metadata first so the dependency layer caches across code edits.
COPY pyproject.toml uv.lock ./
COPY packages/shared/pyproject.toml packages/shared/pyproject.toml
COPY apps/temporal_worker/pyproject.toml apps/temporal_worker/pyproject.toml
COPY apps/slack_gateway/pyproject.toml apps/slack_gateway/pyproject.toml

# Install just the worker's deps (no source yet) for caching.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --package temporal-worker

# Now the source.
COPY packages/shared/ packages/shared/
COPY apps/temporal_worker/ apps/temporal_worker/

# Install the package itself into the workspace .venv.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --package temporal-worker

# --- Runtime ---------------------------------------------------------------
FROM python:${PYTHON_VERSION} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/workspace/.venv/bin:${PATH}" \
    AGENT_WORKSPACE_ROOT=/var/agent/workspaces

# git is required at runtime: the agent's run_shell allowlist permits it
# and the real GitHub client clones/pushes via the CLI.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1001 agent \
    && useradd --system --uid 1001 --gid agent --create-home --home-dir /home/agent agent \
    && mkdir -p /var/agent/workspaces /workspace \
    && chown -R agent:agent /var/agent /workspace

COPY --from=builder --chown=agent:agent /workspace /workspace

USER agent
WORKDIR /home/agent

ENTRYPOINT ["python", "-m", "temporal_worker"]
