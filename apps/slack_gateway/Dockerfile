# syntax=docker/dockerfile:1.7
# -----------------------------------------------------------------------------
# Slack gateway image. Build context must be the repo root (uv workspace root):
#
#   docker build -f apps/slack_gateway/Dockerfile -t slack-gateway:dev .
#
# Uses uv (https://docs.astral.sh/uv/) for fast, deterministic installs.
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

WORKDIR /workspace

COPY pyproject.toml uv.lock ./
COPY packages/shared/pyproject.toml packages/shared/pyproject.toml
COPY apps/slack_gateway/pyproject.toml apps/slack_gateway/pyproject.toml
COPY apps/temporal_worker/pyproject.toml apps/temporal_worker/pyproject.toml

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --package slack-gateway

COPY packages/shared/ packages/shared/
COPY apps/slack_gateway/ apps/slack_gateway/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --package slack-gateway

# --- Runtime ---------------------------------------------------------------
FROM python:${PYTHON_VERSION} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/workspace/.venv/bin:${PATH}" \
    SLACK_GATEWAY_PORT=8080

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1001 gateway \
    && useradd --system --uid 1001 --gid gateway --create-home --home-dir /home/gateway gateway \
    && mkdir -p /workspace \
    && chown -R gateway:gateway /workspace

COPY --from=builder --chown=gateway:gateway /workspace /workspace

USER gateway
WORKDIR /home/gateway

EXPOSE 8080
ENTRYPOINT ["python", "-m", "slack_gateway"]
