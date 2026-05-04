# Coding Agent Platform

An enterprise-grade Slack-driven coding assistant: a user `@mention`s the bot
in any thread, the request is durably orchestrated through a Temporal
workflow, a Pydantic AI agent applies code changes inside an isolated
sandbox, and the result is posted back as a GitHub PR.

| Layer | Tech |
| --- | --- |
| Agent | [Pydantic AI](https://ai.pydantic.dev/) (OpenAI / Anthropic via env) |
| Orchestration | [Temporal](https://temporal.io/) (Temporal Cloud, official Helm chart, or docker-compose locally) |
| Inbound | Slack Events API (HMAC verified, Bolt async) |
| Compute | AWS EKS, Kubernetes 1.30 |
| Packaging | Helm 3 (umbrella + per-service charts) |
| Infra | Terraform (VPC, EKS, ECR, Secrets Manager, IRSA) |
| Code host | GitHub (real PAT or in-memory mock; selectable via env) |

See [`docs/architecture.md`](./docs/architecture.md) for the architecture
diagram (Mermaid) and per-request lifecycle, and [`DESIGN.md`](./DESIGN.md)
for design notes, trade-offs, and limitations.

---

## Repository layout

```
.
├── pyproject.toml         # uv workspace root (binds the three sub-packages)
├── uv.lock                # Pinned dependency graph (committed; reproducible builds)
├── apps/
│   ├── slack_gateway/     # FastAPI + Slack Bolt; starts/signals workflows
│   └── temporal_worker/   # Pydantic AI agent + activities + workflow
├── packages/
│   └── shared/            # Pydantic models on the workflow contract
├── helm/
│   ├── slack-gateway/     # Per-service chart
│   ├── temporal-worker/   # Per-service chart
│   └── platform/          # Umbrella chart (depends on the two above)
├── terraform/
│   ├── envs/dev/          # Deployable environment
│   └── modules/           # ecr, secrets
├── scripts/               # bootstrap, build_images, deploy, cleanup
├── docs/                  # architecture diagram + lifecycle
├── docker-compose.yml     # Local dev stack (Temporal + worker + gateway)
├── Makefile
├── DESIGN.md
└── README.md
```

---

## 1. Local install + run (no AWS required)

The fastest path to a working system. Brings up Temporal + Postgres + the
worker + the gateway in `docker compose`.

### Prerequisites

* Docker (Compose v2)
* [`uv`](https://docs.astral.sh/uv/) — used for both local dev and image builds
  (install: `curl -LsSf https://astral.sh/uv/install.sh | sh`)
* An LLM API key (`OPENAI_API_KEY` *or* `ANTHROPIC_API_KEY`)

### Steps

```bash
# 1. Provision the workspace venv (Python 3.12 + all deps via uv)
./scripts/bootstrap.sh

# 2. Configure environment
cp .env.example .env
# Edit .env and set OPENAI_API_KEY (or ANTHROPIC_API_KEY).
# Slack tokens are optional in mock/dev: leave empty to drive the workflow
# from the Temporal UI directly.

# 3. Bring up the stack
docker compose up --build

# 4. Visit
#    http://localhost:8233          - Temporal UI (workflows, signals, history)
#    http://localhost:8080/healthz  - Slack gateway health
```

To run a service from your IDE instead of in Docker:

```bash
uv run --package temporal-worker python -m temporal_worker
uv run --package slack-gateway python -m slack_gateway
```

### Trigger a workflow without Slack

If you didn't configure Slack credentials, you can start a workflow
directly via the Temporal CLI (or UI) using the worker's task queue:

```bash
docker compose exec temporal tctl --address temporal:7233 workflow start \
  --taskqueue coding-agent \
  --workflow_type CodingAgentWorkflow \
  --workflow_id slack-LOCAL-DEV-1.0 \
  --input '{
    "prompt": "Add a one-line CONTRIBUTING.md describing how to run tests.",
    "base_branch": "main",
    "slack": {
      "team_id": "LOCAL",
      "channel_id": "DEV",
      "thread_ts": "1.0",
      "user_id": "U_LOCAL"
    }
  }'
```

The mock GitHub backend (`GITHUB_MODE=mock`) seeds a tiny repo on disk;
the agent will read/write/commit, then return a fake PR URL.

### Trigger via Slack

1. Create a Slack App at <https://api.slack.com/apps> in any free workspace.
2. Add the **Bot Token Scopes**: `app_mentions:read`, `chat:write`,
   `chat:write.public`, `channels:history`.
3. Subscribe to the `app_mention` event.
4. Set `SLACK_BOT_TOKEN` (xoxb-...) and `SLACK_SIGNING_SECRET` in `.env`.
5. Expose the gateway publicly (e.g. via `cloudflared tunnel --url
   http://localhost:8080`) and point the Slack Events Request URL at
   `https://<tunnel>/slack/events`.
6. In Slack: `@your-bot Add a CONTRIBUTING.md to the repo`.

---

## 2. Deploy to AWS EKS

End-to-end deploy: Terraform provisions the cluster + supporting AWS
resources, then Helm installs the umbrella chart.

### Prerequisites

* AWS CLI with credentials (`aws sts get-caller-identity` works)
* Terraform >= 1.6
* `kubectl` and Helm 3
* Docker (for image build + push to ECR)

### Steps

```bash
# 1. Provision AWS infra
cd terraform/envs/dev
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
# (~15-20 min for the EKS control plane)

# 2. Configure your kubeconfig
$(terraform output -raw kubeconfig_command)
cd ../../..

# 3. Pick a Temporal backend
#    Easiest:  Temporal Cloud (set temporalAddress + temporalTLS in values.eks.yaml)
#    Or:       helm repo add temporalio https://go.temporal.io/helm-charts
#              helm install temporal temporalio/temporal -n temporal --create-namespace
#                # see Temporal docs for production-grade persistence config

# 4. Populate secrets in AWS Secrets Manager
#    Use the AWS console or CLI to fill in:
#      - <name>-slack-gateway: SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET
#      - <name>-temporal-worker: OPENAI_API_KEY (or ANTHROPIC_API_KEY),
#                                SLACK_BOT_TOKEN, GITHUB_TOKEN
#    See DESIGN.md for the recommended ExternalSecrets Operator pattern.

# 5. Build, tag, and push images to ECR
make push-images IMAGE_TAG=0.1.0

# 6. Install the umbrella Helm chart
make deploy IMAGE_TAG=0.1.0

# 7. Find the public Slack Events URL
kubectl -n coding-agent get ingress
# Update your Slack App's Event Subscriptions Request URL accordingly.
```

### What's in the cluster after `make deploy`

```
namespace/coding-agent
├── deployment/agent-slack-gateway        (HPA 2..6, ALB ingress)
└── deployment/agent-temporal-worker      (HPA 2..10, emptyDir scratch)
```

Temporal lives in its own namespace (`temporal/`) when self-hosted, or off-cluster when using Temporal Cloud.

### Cleanup

```bash
make cleanup           # helm uninstall, then terraform destroy
```

This deletes all AWS resources created by Terraform (including the
empty-by-default Secrets Manager secrets, since
`recovery_window_in_days = 0` for dev). Bump that for prod environments
to retain the recovery window.

---

## 3. Configuration reference

All configuration is environment-driven; see `.env.example` for the
canonical list. Key knobs:

| Env var | Where | Purpose |
| --- | --- | --- |
| `AGENT_MODEL` | worker | Pydantic AI model spec; default `anthropic:claude-opus-4-7` |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | worker | LLM auth |
| `TEMPORAL_ADDRESS` | both | host:port (or Temporal Cloud endpoint) |
| `TEMPORAL_TLS` + cert/key paths | both | Required for Temporal Cloud |
| `GITHUB_MODE` | worker | `mock` (default) or `real` |
| `GITHUB_TOKEN` | worker | Required when `GITHUB_MODE=real` |
| `SLACK_BOT_TOKEN` / `SLACK_SIGNING_SECRET` | gateway | Slack auth |
| `AGENT_WORKSPACE_ROOT` | worker | Filesystem root for per-workflow scratch |
| `AGENT_SHELL_ALLOWLIST` | worker | Comma-separated `argv[0]` allowlist |
| `AGENT_MAX_ITERATIONS` | worker | Cap on agent loop iterations per turn |

---

## 4. Useful targets

```bash
make help            # list everything
make compose-up      # local dev stack
make compose-down
make build-images    # docker build slack-gateway:tag + temporal-worker:tag
make tf-apply        # provision AWS infra
make push-images     # build, tag, push to ECR
make deploy          # helm upgrade --install the umbrella chart
make cleanup         # helm uninstall + terraform destroy
make lint            # ruff + helm lint
make helm-template   # render the umbrella chart with values.dev.yaml
```

---

## 5. Submission checklist

- [x] Pydantic AI agent with sandboxed tools (`apps/temporal_worker/.../agent/`)
- [x] Slack Bolt app with HMAC verification (`apps/slack_gateway/.../slack_app.py`)
- [x] Temporal workflow + activities + signals + queries (`apps/temporal_worker/.../workflows.py`)
- [x] AWS EKS via Terraform (`terraform/envs/dev`)
- [x] Helm packaging: per-service + umbrella charts (`helm/`)
- [x] GitHub integration: real client + documented mock (`apps/temporal_worker/.../github_integration/`)
- [x] README with install / deploy / run / cleanup steps (this file)
- [x] Design notes (`DESIGN.md`)
- [x] Architecture diagram (`docs/architecture.md`, Mermaid)
