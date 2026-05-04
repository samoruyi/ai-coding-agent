# Design Notes

A short tour of the choices that shaped this implementation, the trade-offs
behind them, and what I would tackle next given more time.

## Goals (in priority order)

1. **Correct session isolation under concurrency** - two Slack threads
   doing different things at the same time must never see each other's
   files, prompts, or partial state.
2. **Durable orchestration** - if a worker pod dies in the middle of an
   agent run, the workflow continues elsewhere; if Slack is down, the
   user-facing message gets retried.
3. **Operable on Day 1** - a reviewer can run the whole thing locally in
   `docker compose` without an AWS account, and deploy to EKS via a
   handful of `make` targets.
4. **Clear extension points** - swapping the LLM provider, the GitHub
   backend, or Temporal Cloud should each be a config change, not a
   rewrite.

## Key decisions

### Workflow ID = Slack thread

`coding_agent_shared.workflow_id_for_thread()` derives a Temporal Workflow
ID from `(team_id, channel_id, thread_ts)`. This is the load-bearing
piece of session isolation:

* Two threads in the same channel get different IDs, so their state
  never mixes.
* `start_or_signal` in the gateway uses this stable ID to decide whether
  to *start* a new workflow or *signal* an existing one. The result is
  that follow-up replies in the same thread go to the same workflow run,
  feeding back into the agent loop.

### Per-workflow workspaces

Activities don't share filesystem state. Each workflow gets a directory
under `AGENT_WORKSPACE_ROOT/<sanitized_workflow_id>/`. The agent's tool
implementations (`read_file`, `write_file`, `list_dir`, `run_shell`) all
go through `Workspace.resolve()`, which canonicalizes the path and
rejects anything outside the workspace root. This prevents the agent
from reading `/etc/passwd` or another tenant's scratch directory even
if a prompt-injection attack tries.

The default workspace volume is `emptyDir`. That is correct for a single
worker pod handling the workflow end-to-end, which is the common case.
For workflows that span pods (e.g. an activity retrying on a different
worker), you'd switch to a PVC backed by EFS - the chart already supports
this via `workspaceVolume.type=pvc`. The trade-off is that EFS adds latency
and cost; we keep it opt-in.

### Two services, one task queue

The gateway is a stateless HTTP receiver; workers do all the heavy lifting.
Splitting them lets the gateway autoscale on Slack QPS while workers
autoscale on agent CPU/memory. They share a single Temporal task queue
(`coding-agent`). For multi-tenant prod you would partition queues per
tenant or per priority tier and pin worker pools to each.

### GitHub integration via `Protocol`

`github_integration.base.GitHubClient` is a `typing.Protocol`. The mock
and real implementations both satisfy it; activities never see the
concrete class. This is what lets `GITHUB_MODE=mock` boot the entire
platform end-to-end without touching the network and `GITHUB_MODE=real`
flip the switch with no code change.

The mock is intentionally not a no-op: it materializes a tiny git repo on
disk so the agent has a working tree to manipulate. That gives reviewers
a realistic flow to watch in the Temporal UI.

### Pydantic AI for the agent

* Native structured output (`CodingAgentResult`) means we don't parse
  free-form text to extract the summary / changed files / notes.
* Tools are plain async functions registered with `@agent.tool`; their
  signatures become the JSON schema sent to the LLM.
* `deps_type=_AgentDeps` lets us inject the per-workflow `Workspace` and
  shell allowlist into every tool call without globals.

### Activities own all I/O

Workflow code (`workflows.py`) never touches the network, the filesystem,
or the wall clock. Slack posts, GitHub calls, and the LLM are *all*
activities. That keeps the workflow deterministic - the prerequisite for
Temporal's replay-based durability - and makes failures retriable with
backoff via `RetryPolicy` instead of bespoke logic.

The agent activity uses `RetryPolicy(maximum_attempts=1)`. LLM calls
cost money, so we'd rather surface a failure to the user and let them
re-trigger explicitly than burn budget retrying.

### Helm: two charts + umbrella

* `helm/slack-gateway/` and `helm/temporal-worker/` are independently
  installable. Useful when Temporal lives in another cluster (e.g.
  Temporal Cloud).
* `helm/platform/` is an umbrella that depends on both, plus the official
  `temporalio/temporal` chart for self-hosted Temporal.
* `values.dev.yaml` and `values.eks.yaml` capture the two main
  environments; new envs are a one-file change.

### Terraform layout

We split deployable environments (`envs/dev`) from reusable building
blocks (`modules/`), and use the upstream `terraform-aws-modules/vpc/aws`
and `terraform-aws-modules/eks/aws` rather than reinvent them. IRSA
roles bind specific KSAs (`agent-slack-gateway`, `agent-temporal-worker`)
to scoped Secrets Manager read permissions - no AWS keys ever live on
the cluster.

### Secrets

Production pattern (documented in chart values):

1. Terraform provisions Secrets Manager secrets with empty placeholder
   keys.
2. An operator populates them via the AWS console or a CD pipeline.
3. External Secrets Operator syncs them to Kubernetes Secrets.
4. Helm references the synced secret by name (`secrets.externalSecretName`).

For the take-home we also support inline secrets via
`secrets.values.<KEY>` in Helm values. That's fine for a single reviewer,
not fine for prod.

## Limitations

* **No persistent multi-replica workspace.** With `emptyDir`, a worker pod
  crash mid-run loses the working tree. The workflow will replay, the
  workspace will be recreated, and the clone will run again - safe, but
  redundant. Switching to EFS via the existing PVC option fixes this at
  the cost of latency.
* **No per-user GitHub auth.** All workers share one PAT (or one App
  installation). For a multi-tenant deployment you'd map the Slack
  `user_id` to a stored OAuth token via a small sidecar service.
* **No streaming Slack updates.** We post discrete progress messages
  rather than updating one message in place. Slack supports `chat.update`;
  it would be a small follow-up to take the latest `ts` from
  `chat.postMessage` and edit instead of append.
* **Mock PR URLs are unreachable.** `https://example.invalid/...` is a
  reserved TLD; it makes it obvious in Slack that the link is from the
  mock backend, but you can't click through.
* **Single namespace.** The workload runs in `coding-agent` only;
  multi-tenancy via namespace partitioning is left as future work.
* **Tests.** I prioritized end-to-end correctness over coverage. The
  shapes of the units (Workspace, GitHub Protocol, agent tools) are all
  trivial to unit-test; that's the next addition.

## What I'd do next

1. **Real ExternalSecrets wiring** - the chart already supports it; just
   add a `templates/externalsecret.yaml` plus a default `SecretStore`
   pointing at AWS Secrets Manager.
2. **Per-user GitHub OAuth** - persist a user-token map in Postgres, look
   it up at `clone_repo` time, and surface "click here to install the
   GitHub App" as the first reply when no token is found.
3. **Streaming progress** - capture `chat.postMessage`'s returned `ts`
   and use `chat.update` for the live "Iteration N..." message; keep
   final results as separate posts.
4. **Activity-level OpenTelemetry** - a single `instrumentor` module
   wired through both services and Temporal client. Forward to AMP /
   X-Ray.
5. **Cost guardrails** - track `usage` from Pydantic AI's `RunResult`
   and short-circuit at a per-thread token budget.
6. **CI pipeline** - GitHub Actions: lint, helm lint, terraform fmt+validate,
   build images, push to ECR on tag, then `helm upgrade --install`.
7. **End-to-end tests** - spin up the docker-compose stack in CI,
   simulate a Slack event with a signed payload, assert a PR was
   "opened" via the mock backend.
