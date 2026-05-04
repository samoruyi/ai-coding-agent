# Architecture

## High-level flow

```mermaid
flowchart LR
    subgraph Slack["Slack Workspace"]
        U[User]
        SLK[Slack Events API]
    end

    subgraph EKS["AWS EKS Cluster (namespace: coding-agent)"]
        ALB[(ALB Ingress)]
        SG["slack-gateway<br/>(FastAPI + Bolt)"]
        TW["temporal-worker<br/>(Pydantic AI agent)"]
        TS["Temporal Server<br/>(or Temporal Cloud)"]
        PG[(Postgres<br/>persistence)]
    end

    subgraph AWS["AWS account"]
        ECR[(ECR repos)]
        SM[(Secrets Manager)]
        IAM[IRSA roles]
    end

    GH[(GitHub<br/>real or mock)]
    LLM[(LLM API<br/>OpenAI / Anthropic)]

    U -- "@bot fix bug" --> SLK
    SLK -- "POST /slack/events<br/>(HMAC verified)" --> ALB
    ALB --> SG
    SG -- "start_workflow / signal<br/>WorkflowID = slack-{team}-{ch}-{thread}" --> TS
    TS -- "task" --> TW
    TW -- "activities" --> GH
    TW -- "tool calls" --> LLM
    TW -- "post thread reply" --> SLK
    TS --- PG

    SG -. IRSA .-> SM
    TW -. IRSA .-> SM
    SG --- ECR
    TW --- ECR
    SG -. annotates SA .- IAM
    TW -. annotates SA .- IAM
```

## Per-request lifecycle

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Slack
    participant Gateway as slack-gateway
    participant Temporal
    participant Worker as temporal-worker
    participant LLM
    participant GitHub

    User->>Slack: @bot add tests for auth.py
    Slack->>Gateway: POST /slack/events (signed)
    Gateway->>Gateway: verify HMAC, parse event
    Gateway->>Temporal: start_workflow(CodingAgentWorkflow,<br/>id=slack-T1-C1-thread)
    Temporal->>Worker: schedule workflow task
    Worker->>Worker: setup_workspace activity
    Worker->>GitHub: clone repo (real or mock)
    Worker->>LLM: agent loop (read/write/run_shell tools)
    LLM-->>Worker: tool calls / final summary
    Worker->>Slack: progress reply (per iteration)
    Worker->>Temporal: wait 20s for follow_up signal
    alt user replies in same thread
        Slack->>Gateway: POST /slack/events
        Gateway->>Temporal: signal follow_up
        Temporal->>Worker: signal delivered
        Worker->>LLM: continue with new prompt
    else no follow-up
        Worker->>GitHub: commit + open PR
        Worker->>Slack: ":white_check_mark: PR opened ..."
    end
```

## Session isolation

The system isolates concurrent users via three independent boundaries:

| Boundary | Mechanism |
| --- | --- |
| **Per-thread workflow** | `workflow_id_for_thread()` derives a deterministic, unique Workflow ID from `(team_id, channel_id, thread_ts)`. Two Slack threads can never share workflow state. |
| **Per-workflow workspace** | Every workflow gets its own filesystem subtree under `AGENT_WORKSPACE_ROOT`. The `Workspace.resolve()` helper rejects path traversal so the agent's `read_file` / `write_file` tools can't escape. |
| **Per-pod IAM** | Each service has its own IRSA role with the *minimum* set of `secretsmanager:GetSecretValue` permissions. The gateway role can only read Slack tokens; the worker role only its own secrets. |

## Why Temporal

The agent loop is a long-running, multi-step process that benefits from:

* **Durability** - if a worker pod dies mid-run, Temporal replays the workflow on another pod up to the last successful activity.
* **Observability** - each activity (clone, agent run, commit, PR, slack reply) is a discrete step in the Temporal UI.
* **Retries** - transient failures (Slack rate limits, GitHub 5xx) retry with backoff without us writing a state machine.
* **Signals** - follow-up Slack messages on the same thread are delivered to the running workflow, enabling multi-turn conversations.

## Component map

| Component | Path | Purpose |
| --- | --- | --- |
| Shared types | `packages/shared/` | Pydantic models on the workflow contract. |
| Slack gateway | `apps/slack_gateway/` | FastAPI + Bolt, starts/signals workflows. |
| Temporal worker | `apps/temporal_worker/` | Hosts the agent + activities. |
| Pydantic AI agent | `apps/temporal_worker/src/temporal_worker/agent/` | LLM tool loop, system prompt, output schema. |
| GitHub integration | `apps/temporal_worker/src/temporal_worker/github_integration/` | `Protocol` + real and mock implementations. |
| Helm charts | `helm/` | Two service charts + an umbrella that pulls in the upstream Temporal chart. |
| Terraform | `terraform/envs/dev/` | VPC, EKS, ECR, Secrets Manager, IRSA. |
