# Operational Runbook – Agent Orchestrator Backend

This runbook describes **how to operate and troubleshoot** the `agent-orchestrator-api` backend in production.

It is intended for on-call engineers and anyone performing operational tasks (deployments, incident response, maintenance).

---

## 1. Service Overview

- **Service name:** Agent Orchestrator – Backend (`agent-orchestrator-api`)
- **Primary responsibilities:**
  - Accept tasks via HTTP API.
  - Route them through PeerAgent and sub-agents.
  - Persist task and agent run data.
- **Core components:**
  - API service (FastAPI)
  - Celery worker
  - MongoDB Atlas
  - ElastiCache Valkey (Redis)
  - OpenAI + web search provider (e.g. Tavily)
  - AWS EC2, ECR, CodeDeploy, CloudWatch, SSM Parameter Store

---

## 2. Health Checks

### 2.1. API Health

- **Endpoint:** `GET /health`
- **Expected response:**
  - Status code: 200
  - Body: minimal JSON (e.g. `{ "status": "ok" }`)
- **Checks performed:**
  - Lightweight process liveness.
  - Optionally basic dependencies (e.g. Mongo connectivity) depending on implementation.

If `/health` fails:

1. Check container status on EC2.
2. Check recent deployments (CodeDeploy).
3. Inspect logs for exceptions (see section 5).

### 2.2. System Metrics API

- **Endpoint:** `GET /v1/system/metrics`
- **Usage:**
  - Used by the frontend system monitor page.
  - Provides:
    - Queue length
    - Daily task counts
    - Tasks per agent
    - Basic dependency health

If this endpoint fails but `/health` is OK, the issue is likely in:

- MongoDB connectivity (metrics query).
- Redis connectivity (queue metrics).
- LLM or web provider health checks.

---

## 3. Deployment Procedures

### 3.1. Standard Deployment (via CI/CD)

1. Merge changes into `main` branch in GitHub.
2. GitHub Actions CI pipeline:
   - Runs linting and tests.
   - Builds Docker images (API + worker).
   - Pushes images to ECR.
   - Triggers CodeDeploy deployment for `agent-orchestrator-api` application and `agent-orchestrator-api-ec2` deployment group.
3. CodeDeploy executes:
   - `BeforeInstall` hook → `scripts/before_install.sh`
   - `ApplicationStop` hook → `scripts/stop_application.sh` (if configured)
   - `ApplicationStart` hook → `scripts/start_application.sh`

**Operator responsibilities:**

- Monitor CodeDeploy deployment status:
  - In AWS console: CodeDeploy → Deployments.
  - Check last deployment for failures.
- If deployment fails:
  - Review CodeDeploy logs on EC2:
    - `/opt/codedeploy-agent/deployment-root/.../logs/` (per deployment).
  - Review application logs in CloudWatch.

### 3.2. Manual Rollback

If a deployment introduces a critical issue:

1. In CodeDeploy:
   - Find the last **successful** deployment.
   - Redeploy that revision (if configured).
2. Alternatively:
   - Use GitHub Actions to trigger a deployment of a known good tag/commit.
3. Confirm:
   - `/health` and `/v1/system/metrics` are healthy.
   - Key flows (e.g. submitting and completing tasks) are working end-to-end.

Capture the incident and rollback decision in an incident record.

---

## 4. Common Incident Scenarios

### 4.1. Tasks Stuck in `queued` or `processing`

**Symptoms:**

- Multiple tasks remain in `queued` or `processing` for longer than expected.
- System monitor shows high queue length and low completion rate.

**Possible causes:**

- Celery workers not running.
- Redis unavailable or overloaded.
- LLM provider slow or failing.
- MongoDB connectivity problems.

**Checklist:**

1. **Check worker status:**
   - On EC2:
     - Confirm worker container is running (via Docker tooling).
   - Look at worker logs in CloudWatch (`/agent-orchestrator/worker`).
2. **Check Redis (Valkey):**
   - In AWS console:
     - ElastiCache → Redis → cluster status must be `available`.
   - CloudWatch metrics:
     - CPU, memory usage, connections, evictions.
3. **Check LLM provider:**
   - Look for error patterns in logs (timeouts, rate limit errors).
   - If external outage is suspected, reduce task submission and inform stakeholders.
4. **Check MongoDB Atlas:**
   - Status page.
   - Logs for connection timeouts.

**Mitigation:**

- Restart worker container(s) if they are unresponsive.
- Scale worker replicas horizontally if load is consistently high.
- For large backlogs:
  - Temporarily increase worker concurrency.
  - Consider pausing new task submissions (frontend messaging and/or rate limiting).

Document root cause and remediation in a post-incident note.

---

### 4.2. High Error Rate from LLM Provider

**Symptoms:**

- Many tasks end with `status = "failed"` and errors referencing LLM calls.
- Logs show repeated HTTP errors (429, 5xx) to LLM endpoints.

**Checklist:**

1. Verify status page of the LLM provider.
2. Inspect error messages:
   - `429` – rate limit exceeded.
   - `5xx` – provider internal error.
   - Connection/reset errors – network or TLS issues.
3. Check usage and quotas:
   - In the provider’s dashboard, verify monthly/daily limits.

**Mitigation:**

- For **rate limit** issues:
  - Lower concurrency or enforce stricter rate limiting.
  - Implement exponential backoff on retries (if not already).
- For provider outages:
  - Gracefully degrade:
    - Return a clear error message to the client.
    - Optionally disable new task submissions temporarily.
- Consider temporarily switching models (if configured) to an alternative.

Update `operational-runbook.md` after incidents to include patterns and resolutions.

---

### 4.3. MongoDB Connectivity Issues

**Symptoms:**

- API and worker logs show connection errors to MongoDB.
- `GET /v1/tasks` fails or is slow.

**Checklist:**

1. Check MongoDB Atlas:
   - Cluster status.
   - Recent maintenance or deployment events.
2. Verify network:
   - If Atlas is IP-whitelisted:
     - Confirm EC2 public IP or VPC Peering/VPC Private Endpoint is configured correctly.
3. Check connection string (`MONGO_URI`) in Parameter Store.

**Mitigation:**

- If an IP-based whitelist is used:
  - Update firewall rules / Atlas IP access list.
- If outage persists:
  - Treat as partial service degradation; document the period and behavior.

---

### 4.4. Redis / Valkey Issues

**Symptoms:**

- Queue operations fail; API may not be able to enqueue tasks.
- Worker logs show Redis connection errors.

**Checklist:**

1. AWS console:
   - ElastiCache → cluster status.
2. CloudWatch metrics:
   - CPU Utilization
   - Engine CPU
   - Memory usage
   - Connection count
3. Check Security Groups:
   - Ensure `sg-agent-orchestrator-ec2` still has permission to connect to `sg-agent-orchestrator-redis` on port 6379.

**Mitigation:**

- If memory pressure is high:
  - Reduce task rate.
  - Consider resizing the node or adding replicas.
- If cluster is unhealthy:
  - Follow AWS recommendations for failover or restoring from snapshot.

---

### 4.5. CodeDeploy Deployment Fails

**Symptoms:**

- CodeDeploy deployment status is `Failed`.
- New code is not running on EC2.

**Checklist:**

1. In CodeDeploy console:
   - Inspect deployment details and lifecycle events.
2. On EC2:
   - Check CodeDeploy logs:
     - Under `/opt/codedeploy-agent/deployment-root/` (path may vary).
3. Look at `BeforeInstall`, `ApplicationStart`, `ApplicationStop` logs:
   - Validate scripts exist and are executable.
   - Validate environment variables are available.

**Mitigation:**

- Fix the root cause (missing file, permission issue, failing script).
- Create a new deployment.
- If necessary, manually redeploy a known good revision.

Document the failure and fix in the repository (e.g., in a `CHANGELOG` or incident record).

---

## 5. Logs and Tracing

### 5.1. Where to Find Logs

- **Application logs:**
  - CloudWatch Log Groups:
    - `/agent-orchestrator/api`
    - `/agent-orchestrator/worker`
- **CodeDeploy logs:**
  - EC2 instance under CodeDeploy deployment root.
- **CloudWatch Agent logs:**
  - `amazon-cloudwatch-agent.log` on EC2 (if used).

Use filters on:

- `task_id`
- `request_id`
- `agent_name`
- `level` (`ERROR`, `WARN`)

to quickly narrow down relevant events.

---

## 6. Configuration and Secrets

### 6.1. Parameter Store Usage

- All sensitive configuration is stored under:

  - `/agent-orchestrator-api/dev/*`
  - `/agent-orchestrator-api/prod/*`

- Examples:
  - `MONGO_URI`
  - `REDIS_URL`
  - `OPENAI_API_KEY`
  - `TAVILY_API_KEY`

**Operational tasks:**

- Updating values:
  - Use AWS console or CLI to update parameters.
  - For `SecureString`, ensure correct KMS key is used.
- Rotating keys:
  - Update parameter in SSM.
  - Redeploy or restart services if necessary.

### 6.2. Verifying Access From EC2

On an EC2 instance:

- Use CLI to fetch dev parameters:

  ```text
  aws ssm get-parameters-by-path \
    --path "/agent-orchestrator-api/dev/" \
    --with-decryption \
    --region eu-central-1











Perfect, this is a great moment to “freeze” the architecture into real documentation.

Below I’ll give you **ready-to-paste content** for:

* `.editorconfig`
* `docs/architecture-overview.md`
* `docs/backend-adr-0001-llm-choice.md`
* `docs/backend-adr-0002-queue-architecture.md`
* `docs/operational-runbook.md`
* `docs/config-reference.md`
* `docs/content-agent-design.md`
* `docs/code-agent-design.md`

All in **English**, and all written to look like a serious, production-minded backend project.

You can copy each block into the corresponding file in your `agent-orchestrator-api` repo.

---

## 1. `.editorconfig`

```editorconfig
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true

indent_style = space
indent_size = 4

[*.md]
max_line_length = off
trim_trailing_whitespace = false

[*.yml]
indent_size = 2

[*.yaml]
indent_size = 2

[*.json]
indent_size = 2

[*.toml]
indent_size = 2

[*.sh]
indent_style = space
indent_size = 2

[Makefile]
indent_style = tab
```

---

## 2. `docs/architecture-overview.md`

````markdown
# Agent Orchestrator – Backend Architecture Overview

## 1. Context and Goals

**Agent Orchestrator** is a backend service that receives high-level natural-language tasks from clients and routes them through a peer agent to specialized sub-agents (e.g. `ContentAgent`, `CodeAgent`). The system must:

- Be **modular and extensible** (new agents easy to add).
- Follow **12-Factor App** principles.
- Be **production-ready** (observability, CI/CD, config management, security).
- Integrate with **LLMs** and **web search tools**.
- Expose a clean **HTTP API** (`/v1/agent/execute`) for the frontend dashboard.

This document describes the **high-level architecture** of the backend (`agent-orchestrator-api`), focusing on:

- Components & responsibilities
- Runtime topology on AWS
- Request/Task lifecycle
- Agentic orchestration design
- Observability & resilience
- Extensibility patterns

---

## 2. High-Level Component Diagram (Conceptual)

Textual view of the main components and interactions:

- **Client / Frontend**
  - Sends tasks via `POST /v1/agent/execute`
  - Polls `GET /v1/tasks/{task_id}` and `GET /v1/system/metrics`

- **API Service (FastAPI)**
  - Validates and accepts tasks
  - Persists tasks in MongoDB (`status = queued`)
  - Enqueues Celery task into Redis
  - Exposes task and metrics endpoints
  - Implements rate limiting, auth (optional), CORS

- **Worker Service (Celery Worker)**
  - Consumes tasks from Redis queue
  - Loads task and session context from MongoDB
  - Executes **PeerAgent (router)** via LangGraph
  - Invokes selected sub-agent (`ContentAgent`, `CodeAgent`, …)
  - Persists results, agent runs, and messages to MongoDB
  - Updates task status and timing fields

- **Agent Layer**
  - **PeerAgent**: LLM-based router deciding which agent to use.
  - **ContentAgent**: generates long-form content, uses web search tools.
  - **CodeAgent**: generates / explains / refactors code (no execution in backend).
  - **Agent Registry**: maps logical agent names to implementations.

- **Data Stores**
  - **MongoDB Atlas**:
    - `tasks` – task lifecycle
    - `agent_runs` – per-agent execution logs
    - `messages` – conversation and context history
    - `logs` – structured application events (optional)
    - `sessions` – session/memory (optional)
    - `system_metrics` – aggregated metrics (optional)
  - **Redis / Valkey (ElastiCache)**:
    - Celery broker & result backend
    - Application rate-limiting and optional caching

- **External Services**
  - **LLM Provider (OpenAI)** – model endpoints for router and agents.
  - **Web Search Provider (e.g. Tavily)** – search tool for `ContentAgent`.

- **Infrastructure / Platform**
  - **AWS EC2** – API + Worker containers
  - **AWS ECR** – container image registry
  - **AWS ElastiCache (Valkey)** – Redis compatible cache for Celery + rate limiting
  - **MongoDB Atlas** – managed Mongo database
  - **AWS VPC** – isolated network with public & private subnets
  - **AWS Systems Manager (SSM) Parameter Store** – configuration & secrets
  - **AWS CodeDeploy** – deployment orchestrator
  - **GitHub Actions** – CI/CD pipeline
  - **AWS CloudWatch** – logs, metrics, alarms, dashboards

---

## 3. Runtime Topology (AWS)

### 3.1. VPC and Networking

- Dedicated **VPC**: `agent-orchestrator-vpc`
  - CIDR block: `10.0.0.0/16` (example)
  - **Public subnets** (per AZ, e.g. `10.0.1.0/24`, `10.0.2.0/24`)
    - EC2 instance(s) hosting API + worker containers
    - NAT gateway (if used for private subnets)
  - **Private subnets** (optional)
    - ElastiCache (Valkey) and, in future, RDS or other DBs
- **Internet Gateway** attached to VPC.
- **Route tables**:
  - Public route table → `0.0.0.0/0` via Internet Gateway
  - Private route table(s) → `0.0.0.0/0` via NAT Gateway (if private subnets used)

### 3.2. Security Groups

- `sg-agent-orchestrator-ec2`
  - Inbound:
    - SSH (22) from admin IP only
    - HTTP/HTTPS (80/443) from allowed sources (initially 0.0.0.0/0, later ALB only)
  - Outbound:
    - Allow all (or restricted to Mongo Atlas, OpenAI, Tavily, etc.)

- `sg-agent-orchestrator-redis`
  - Inbound:
    - TCP 6379 from `sg-agent-orchestrator-ec2` only
  - Outbound: allow all (or restricted if needed)

This keeps Redis internal to the backend network and not exposed publicly.

---

## 4. Request & Task Lifecycle

### 4.1. `/v1/agent/execute` Flow

1. **Client → API**

   - Client sends:
     - `POST /v1/agent/execute`
     - Body: `{ "task": "<natural language task>", "session_id": "<optional>" }`
   - API layer:
     - Validates payload (non-empty `task`, optional `session_id`).
     - Applies rate limit (IP and/or API key).
     - Assigns a new `task_id` (UUID).

2. **Persist initial Task**

   - API persists a new document in `tasks` collection:
     - `status = "queued"`
     - Timestamps: `created_at`, `queued_at`
     - Metadata: IP, user agent, request_id, environment
     - `session_id` (if provided or auto-generated)
   - Optional initial `messages` entry capturing user task.

3. **Enqueue Work**

   - API enqueues a Celery task:
     - Name: `process_task`
     - Payload: `{ "task_id": "<uuid>" }`
     - Broker: Redis (`REDIS_URL`)

4. **API Response**

   - API returns immediately:
     ```json
     {
       "task_id": "<uuid>",
       "session_id": "<uuid-or-null>",
       "status": "queued",
       "queued_at": "<ISO8601>",
       "message": "Task accepted and queued.",
       "api_version": "v1"
     }
     ```

### 4.2. Worker Processing Flow

1. **Worker pulls from queue**

   - Celery worker listens on the `agent_tasks` queue.
   - On `process_task(task_id)`:
     - Loads task from MongoDB.
     - Updates `status = "processing"`, sets `started_at`.

2. **PeerAgent Routing (LangGraph)**

   - Worker invokes **PeerAgent graph** with context:
     - Task text
     - Session history (if used)
     - Metadata (e.g. previous tasks in same session)
   - LangGraph nodes:
     - `classify_task` (LLM call)
       - Outputs: `{ agent_name, confidence, reasoning }`
     - `route_to_agent`
       - Applies business rules (min confidence threshold).
   - Classification result persisted into:
     - `agent_runs` (router run)
     - `tasks.selected_agent`, `tasks.agent_type`, `tasks.peer_routing_reason`

   - If `agent_name = "Unknown"` or low confidence:
     - Worker marks task as `status = "failed"`, sets `error.type = "UNKNOWN_TASK_TYPE"`.

3. **Agent Execution**

   - Worker retrieves agent instance from the **Agent Registry** by name.
   - Calls agent with a domain `Task` model.
   - Agent returns `AgentOutput`:
     - `agent_name`
     - `content`
     - Optional: `code_language`
     - Optional: `citations[]`
   - Agent run is logged to `agent_runs`, intermediate messages to `messages`.

4. **Persist Result & Final Status**

   - Worker updates `tasks` document:
     - `status = "completed"` (or `failed` if exception)
     - `result.summary` (optional short summary)
     - `result.raw_output` (full agent response)
     - `result.code_language` (for CodeAgent)
     - `result.citations[]`
     - `completed_at`, `updated_at`
     - Token usage and cost estimates (if available)
   - On errors:
     - `status = "failed"`
     - `error.type`, `error.message`

### 4.3. Task Query & Monitoring

- `GET /v1/tasks/{task_id}`
  - Returns full task document including result & errors.
- `GET /v1/tasks`
  - Returns paginated task summaries with filters:
    - `status`, `agent_type`, date range.
- `GET /v1/system/metrics`
  - Returns aggregated stats:
    - Queue length, today’s task counts, agent distribution, health checks.

---

## 5. Agentic Architecture

### 5.1. BaseAgent and AgentOutput (Conceptual)

All agents implement a common interface (conceptually):

- `name`: canonical identifier (e.g. `"ContentAgent"`)
- `run(task) -> AgentOutput`

`AgentOutput` (domain model):

- `agent_name: str`
- `content: str`
- `code_language: Optional[str]`
- `citations: List[Citation]`

`Citation` contains:

- `source: str` (e.g. `"tavily"`)
- `title: Optional[str]`
- `url: Optional[str]`

### 5.2. Agent Registry

The registry is a central mapping of agent names to implementations. Conceptually:

- `ContentAgent`
- `CodeAgent`
- Future agents (e.g. `RefactorAgent`, `TestAgent`)

Adding a new agent requires:

1. Implementing the agent in `app/agents/`.
2. Registering it in `app/agents/registry`.
3. Updating PeerAgent’s documentation/prompt so the router knows when to select it.

### 5.3. PeerAgent (Router) via LangGraph

PeerAgent is implemented as a LangGraph graph, not a single prompt:

- Node `classify_task`:
  - LLM call with a system prompt describing available agents and their responsibilities.
  - Returns structured output: `agent_name`, `confidence`, `reasoning`.
- Node `route_to_agent`:
  - Applies minimal business logic (e.g. minimum confidence).
  - Either selects agent or yields an error state.

The router is intentionally **data-driven**, avoiding brittle keyword rules.

---

## 6. Configuration Management

### 6.1. Environment Variables and SSM Parameter Store

The service adheres to **12-Factor** configuration guidelines:

- All runtime config comes from **environment variables**.
- Env variables are sourced from:
  - Local `.env` in development (not committed).
  - **SSM Parameter Store** in dev/prod EC2 environments.

Recommended parameter hierarchy:

- `/agent-orchestrator-api/dev/...`
- `/agent-orchestrator-api/prod/...`

Examples (see `config-reference.md` for full list):

- `MONGO_URI`
- `MONGO_DB_NAME`
- `REDIS_URL`
- `OPENAI_API_KEY`
- `TAVILY_API_KEY`
- `LLM_PEER_MODEL`
- `LLM_CONTENT_MODEL`
- `LLM_CODE_MODEL`
- `LOG_LEVEL`
- `API_RATE_LIMIT_PER_MINUTE`
- `CORS_ORIGINS`

---

## 7. Observability

### 7.1. Logging

- Application logs are structured JSON written to **stdout**.
- CloudWatch Agent forwards container logs to:
  - `/agent-orchestrator/api` (API logs)
  - `/agent-orchestrator/worker` (worker logs)
- Logs include:
  - `timestamp`, `level`, `message`
  - `request_id`
  - `task_id`, `session_id`
  - `agent_name`
  - `endpoint`, `status_code`
  - `duration_ms`

Important lifecycle events (task status changes, routing decisions, errors) can additionally be persisted into the `logs` MongoDB collection for long-term analysis.

### 7.2. Metrics

Planned metrics (either via Prometheus endpoint or CloudWatch custom metrics):

- HTTP:
  - Request count and latency per endpoint
  - Error rate per endpoint
- Tasks:
  - Tasks per status (`queued`, `processing`, `completed`, `failed`)
  - Tasks per agent (`ContentAgent`, `CodeAgent`, …)
  - Task latency (avg, p95)
- Queue:
  - Queue length over time
  - Worker throughput
- LLM:
  - Calls per model
  - Token usage (if reported by LLM)

`GET /v1/system/metrics` surfaces a summarized view for the frontend dashboard.

### 7.3. Alarms and Dashboards

CloudWatch Alarms (examples):

- High CPU on EC2 instance
- High error rate on API
- Long task latency (p95 above threshold)
- Queue backlog above threshold for N minutes

CloudWatch Dashboard:

- EC2 CPU, network
- ElastiCache metrics
- Custom metrics: task counts and latency

---

## 8. Extensibility and Versioning

### 8.1. Adding a New Agent

To add a new agent (e.g. `RefactorAgent`):

1. Implement agent in `app/agents/refactor_agent.*`.
2. Add it to the **Agent Registry**.
3. Update PeerAgent router specification so LLM can choose it.
4. Update documentation:
   - `content-agent-design.md` or `code-agent-design.md` if relevant.
   - `architecture-overview.md` – list new agent under Agent Layer.

No changes should be required in API or worker orchestration logic beyond configuration.

### 8.2. API Versioning Strategy

Current API prefix: `/v1`.

- Breaking changes:
  - Introduce `/v2` alongside `/v1`.
  - Keep `/v1` until consumers are migrated.
- Non-breaking additive changes:
  - Extend existing responses with new optional fields.
  - Add new endpoints under `/v1`.

API version is also returned in responses as `api_version` for explicitness.

---

## 9. Production Hardening (Summary)

Key practices that make this backend production-aligned:

- Isolated **VPC** with fine-grained **security groups**.
- **SSM Parameter Store** for config and secrets.
- **Structured logging** with CloudWatch integration.
- CI/CD pipeline using **GitHub Actions + CodeDeploy + ECR + EC2**.
- **Celery + Redis** queue for async processing.
- **MongoDB Atlas** for resilient data storage.
- Clear **runbooks** for operations (see `operational-runbook.md`).
- Path to **horizontal scaling** (multiple workers, multiple API instances).
````

---

## 3. `docs/backend-adr-0001-llm-choice.md`

```markdown
# ADR-0001 – LLM Provider and Model Selection

- **Status:** Accepted  
- **Date:** 2025-12-xx  
- **Owner:** Backend / AI Architecture

## 1. Context

The Agent Orchestrator relies heavily on LLMs:

- **PeerAgent (router):** classify tasks and select the appropriate sub-agent.
- **ContentAgent:** synthesize high-quality blog-style and explanatory content.
- **CodeAgent:** generate, explain, and refactor code.

Key requirements:

- Reasonable **latency** for interactive use.
- **High-quality reasoning** for routing and code generation.
- **Cost efficiency** for continuous operation in dev/prod.
- Stable and well-supported API, with strong ecosystem libraries.

The system should also make it straightforward to swap or add providers later without deep rewrites.

## 2. Decision

We will use **OpenAI** as the initial LLM provider and the following models:

- **PeerAgent Router:**
  - Model: `gpt-4.1-mini` (or similar “mini” 4.x model)
  - Rationale:
    - Good quality for classification/routing tasks.
    - Lower cost and latency than full `gpt-4.1`.
- **ContentAgent:**
  - Model: `gpt-4.1` (or `gpt-4o` depending on availability and pricing).
  - Rationale:
    - Higher-quality long-form generation needed for blog-like outputs.
    - Better coherence and factuality compared to lighter models.
- **CodeAgent:**
  - Model: `o3-mini` (or best available high-reasoning code-capable model).
  - Rationale:
    - Strong reasoning performance for complex code tasks.
    - Explicitly tuned for analytical/code workloads.

Configuration will be **externalized** via environment variables and SSM parameters:

- `LLM_PEER_MODEL` – default `gpt-4.1-mini`
- `LLM_CONTENT_MODEL` – default `gpt-4.1`
- `LLM_CODE_MODEL` – default `o3-mini`
- `OPENAI_API_KEY` – provider secret

All LLM calls will be routed through a small internal abstraction layer in `app/llm/` so the rest of the codebase is provider-agnostic.

## 3. Alternatives Considered

### 3.1. Single Model for All Use Cases

Using one high-end model (e.g. `gpt-4.1`) for router, content, and code:

- **Pros:**
  - Simpler configuration.
  - Homogeneous behaviour across different tasks.
- **Cons:**
  - Inefficient cost-wise (routing does not need full 4.x capabilities).
  - Higher latency for router and lightweight tasks.
  - No ability to tailor the model to task type.

**Reason for rejection:** Poor cost/performance balance, especially when routing is called for every task.

### 3.2. Alternative Providers (e.g. Anthropic, local models)

- **Pros:**
  - Possible cost benefits or specific strengths.
  - Local models could reduce vendor lock-in.
- **Cons:**
  - Increased initial integration work.
  - Less mature ecosystem (SDKs, tooling) in our current stack.
  - Local models require additional infra (GPU/accelerator, scaling, maintenance).

**Reason for deferral:** Out of scope for initial implementation. The architecture remains flexible to add support later via the `app/llm/` abstraction.

### 3.3. No Router LLM (keyword-based routing)

- **Pros:**
  - No cost for routing.
  - Very simple implementation.
- **Cons:**
  - Fragile keyword logic; easy to misroute.
  - Hard to extend as more agents are added.
  - Fails the “LLM-based agentic routing” requirement.

**Reason for rejection:** Explicitly against test requirements and long-term modular goals.

## 4. Consequences

### Positive

- Clear separation of responsibilities:
  - Lightweight model for routing.
  - High-quality model for content.
  - Reasoning-strong model for code.
- Cost and latency can be tuned **per task type** via configuration.
- LLM details are contained within a dedicated `llm` module, making it easier to:
  - Adjust models.
  - Switch providers.
  - Add new capabilities (e.g. tools, structured outputs).

### Negative / Risks

- Tight coupling to a single provider (OpenAI) initially:
  - Outage or policy changes could impact availability.
- Multiple models increases:
  - Configuration complexity.
  - Monitoring overhead (per-model usage/quotas).
- Requires careful error handling:
  - Timeouts, rate limits, quota exceeded.

## 5. Follow-up Actions

- Implement a thin LLM client in `app/llm/`:
  - Standardized interface (e.g. `complete`, `chat`, `with_tools`, etc.).
  - Built-in retry/backoff and error normalization.
- Add metrics:
  - Calls per model.
  - Token usage per model.
  - Error rate per model.
- Document procedures for:
  - Rotating `OPENAI_API_KEY`.
  - Switching to backup models if a primary model is unavailable.
```

---

## 4. `docs/backend-adr-0002-queue-architecture.md`

```markdown
# ADR-0002 – Queue and Worker Architecture

- **Status:** Accepted  
- **Date:** 2025-12-xx  
- **Owner:** Backend / Platform

## 1. Context

The Agent Orchestrator must process user tasks asynchronously:

- `POST /v1/agent/execute` should return quickly after queueing work.
- Long-running LLM calls and web search should not block the HTTP request.
- We need:
  - Reliable background task processing.
  - Support for retries and backoff.
  - Ability to scale workers independently of the API.

Candidate technologies included:

- Celery + Redis / RabbitMQ
- AWS SQS + custom worker
- AWS Step Functions
- Kafka + custom consumer
- Simple in-process background tasks

## 2. Decision

We will use **Celery** as the worker framework with **Redis (Valkey)** as the broker and result backend.

### Rationale

- Celery is a mature, widely used choice in Python ecosystems for:
  - Task queues
  - Scheduling
  - Retries and routing
- Redis (via Valkey on AWS ElastiCache) provides:
  - Low latency
  - Compatibility with Celery’s Redis transport
  - Shared infrastructure with rate limiting and caching concerns
- This combination fits both:
  - **Local development** (single Docker-based Redis).
  - **Production** (managed ElastiCache cluster).

## 3. Architecture Overview

### 3.1. Components

- **Celery Worker**
  - Runs in a dedicated container next to the API.
  - Consumes from a named queue, e.g. `agent_tasks`.
  - Executes tasks like `process_task(task_id)`.

- **Broker / Backend – Redis (Valkey)**
  - Hosted on AWS ElastiCache in the same VPC as EC2.
  - Single primary + optional replica for high availability.
  - Used for:
    - Celery broker
    - Celery result backend (optionally)
    - Application-level rate limiting

- **Task Payload**
  - Minimal payload: `task_id` (UUID).
  - All rich context is fetched from MongoDB, ensuring idempotence and avoiding payload bloat.

### 3.2. Task Lifecycle (Queue Perspective)

1. API enqueues `process_task(task_id)` onto `agent_tasks` queue.
2. Celery worker pulls message, sets task `status = "processing"`.
3. Worker executes:
   - PeerAgent routing via LangGraph.
   - Selected agent (ContentAgent, CodeAgent, etc.).
   - Writes results to MongoDB; updates `status`.
4. On success: Task marked `completed`.
5. On failure:
   - Worker logs error details.
   - Depending on error type, may retry with backoff or mark `failed`.

---

## 4. Celery Configuration (Conceptual)

Key configuration choices:

- **Broker URL:** `redis://<redis-host>:6379/0`
- **Result backend:** same Redis instance (different database index or same DB).
- **Queue name:** `agent_tasks`
- **Task acks late:** enabled
  - Ensures messages are only acked after successful processing.
- **Worker prefetch multiplier:** `1`
  - Prevents a single worker from reserving too many tasks and improves fairness.
- **Retry policy:**
  - Transient errors (network issues, LLM timeouts) → exponential backoff retries.
  - Permanent errors (validation, unknown task type) → no retries; mark as failed.

This configuration is designed to be **explicitly documented** and kept in a dedicated config module, controlled via environment variables.

---

## 5. Alternatives Considered

### 5.1. AWS SQS + Custom Worker

- **Pros:**
  - Fully managed, highly scalable queue.
  - Native integration with AWS.
- **Cons:**
  - Would require custom retry/backoff logic.
  - No out-of-the-box task semantics like Celery (acks, result handling, task routing).
  - Additional code needed to manage concurrency and worker lifecycle.

**Reason for deferral:** More boilerplate to reach same functionality Celery already provides. Could be revisited if Celery becomes a limitation.

### 5.2. AWS Step Functions

- **Pros:**
  - Visual workflows, excellent for complex multi-step orchestrations.
  - Built-in retries, error handling, and integration with other AWS services.
- **Cons:**
  - Overkill at this stage; our tasks are mostly linear.
  - Tighter coupling to AWS; less portable.
  - More complex to integrate with external LLMs and MongoDB in a flexible way.

**Reason for deferral:** Too heavy for the current problem. The orchestration logic fits better inside our Python/LangGraph layer.

### 5.3. Kafka

- **Pros:**
  - High throughput, durable event streaming.
  - Good for event-driven architectures at scale.
- **Cons:**
  - Infra overhead (brokers, ZooKeeper replacement, etc.).
  - Celery’s Kafka support is less common; would require more maintenance.
  - Current workload does not justify full Kafka complexity.

**Reason for rejection:** Not necessary at current scale; higher operational cost.

### 5.4. In-process Background Tasks (e.g. threads)

- **Pros:**
  - Very simple to implement.
  - No extra infrastructure.
- **Cons:**
  - Tied to API process lifecycle; no resilience.
  - Hard to scale independently.
  - Limited observability and retry semantics.

**Reason for rejection:** Not acceptable for a production-grade, decoupled architecture.

---

## 6. Consequences

### Positive

- Well understood, widely adopted pattern (Celery + Redis).
- Clear separation of concerns:
  - API handles HTTP and persistence.
  - Worker handles CPU/IO heavy agent work.
- Easy horizontal scaling:
  - Add more worker containers to consume tasks faster.
- Redis can serve multiple roles (queue, rate limiting, caching).

### Negative / Risks

- Additional moving parts (Celery processes, Redis cluster) must be monitored.
- Redis outages directly impact:
  - Task queueing
  - Rate limiting
- Requires tuning to avoid:
  - Overloaded workers
  - Memory issues in Redis

---

## 7. Follow-up Actions

- Define Celery configuration via environment variables (`CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, queue names).
- Add metrics:
  - Number of tasks queued/completed/failed per minute.
  - Queue length and worker concurrency.
- Document operational procedures for:
  - Scaling workers.
  - Handling large backlogs (see `operational-runbook.md`).
```

---

## 5. `docs/operational-runbook.md`

````markdown
# Operational Runbook – Agent Orchestrator Backend

This runbook describes **how to operate and troubleshoot** the `agent-orchestrator-api` backend in production.

It is intended for on-call engineers and anyone performing operational tasks (deployments, incident response, maintenance).

---

## 1. Service Overview

- **Service name:** Agent Orchestrator – Backend (`agent-orchestrator-api`)
- **Primary responsibilities:**
  - Accept tasks via HTTP API.
  - Route them through PeerAgent and sub-agents.
  - Persist task and agent run data.
- **Core components:**
  - API service (FastAPI)
  - Celery worker
  - MongoDB Atlas
  - ElastiCache Valkey (Redis)
  - OpenAI + web search provider (e.g. Tavily)
  - AWS EC2, ECR, CodeDeploy, CloudWatch, SSM Parameter Store

---

## 2. Health Checks

### 2.1. API Health

- **Endpoint:** `GET /health`
- **Expected response:**
  - Status code: 200
  - Body: minimal JSON (e.g. `{ "status": "ok" }`)
- **Checks performed:**
  - Lightweight process liveness.
  - Optionally basic dependencies (e.g. Mongo connectivity) depending on implementation.

If `/health` fails:

1. Check container status on EC2.
2. Check recent deployments (CodeDeploy).
3. Inspect logs for exceptions (see section 5).

### 2.2. System Metrics API

- **Endpoint:** `GET /v1/system/metrics`
- **Usage:**
  - Used by the frontend system monitor page.
  - Provides:
    - Queue length
    - Daily task counts
    - Tasks per agent
    - Basic dependency health

If this endpoint fails but `/health` is OK, the issue is likely in:

- MongoDB connectivity (metrics query).
- Redis connectivity (queue metrics).
- LLM or web provider health checks.

---

## 3. Deployment Procedures

### 3.1. Standard Deployment (via CI/CD)

1. Merge changes into `main` branch in GitHub.
2. GitHub Actions CI pipeline:
   - Runs linting and tests.
   - Builds Docker images (API + worker).
   - Pushes images to ECR.
   - Triggers CodeDeploy deployment for `agent-orchestrator-api` application and `agent-orchestrator-api-ec2` deployment group.
3. CodeDeploy executes:
   - `BeforeInstall` hook → `scripts/before_install.sh`
   - `ApplicationStop` hook → `scripts/stop_application.sh` (if configured)
   - `ApplicationStart` hook → `scripts/start_application.sh`

**Operator responsibilities:**

- Monitor CodeDeploy deployment status:
  - In AWS console: CodeDeploy → Deployments.
  - Check last deployment for failures.
- If deployment fails:
  - Review CodeDeploy logs on EC2:
    - `/opt/codedeploy-agent/deployment-root/.../logs/` (per deployment).
  - Review application logs in CloudWatch.

### 3.2. Manual Rollback

If a deployment introduces a critical issue:

1. In CodeDeploy:
   - Find the last **successful** deployment.
   - Redeploy that revision (if configured).
2. Alternatively:
   - Use GitHub Actions to trigger a deployment of a known good tag/commit.
3. Confirm:
   - `/health` and `/v1/system/metrics` are healthy.
   - Key flows (e.g. submitting and completing tasks) are working end-to-end.

Capture the incident and rollback decision in an incident record.

---

## 4. Common Incident Scenarios

### 4.1. Tasks Stuck in `queued` or `processing`

**Symptoms:**

- Multiple tasks remain in `queued` or `processing` for longer than expected.
- System monitor shows high queue length and low completion rate.

**Possible causes:**

- Celery workers not running.
- Redis unavailable or overloaded.
- LLM provider slow or failing.
- MongoDB connectivity problems.

**Checklist:**

1. **Check worker status:**
   - On EC2:
     - Confirm worker container is running (via Docker tooling).
   - Look at worker logs in CloudWatch (`/agent-orchestrator/worker`).
2. **Check Redis (Valkey):**
   - In AWS console:
     - ElastiCache → Redis → cluster status must be `available`.
   - CloudWatch metrics:
     - CPU, memory usage, connections, evictions.
3. **Check LLM provider:**
   - Look for error patterns in logs (timeouts, rate limit errors).
   - If external outage is suspected, reduce task submission and inform stakeholders.
4. **Check MongoDB Atlas:**
   - Status page.
   - Logs for connection timeouts.

**Mitigation:**

- Restart worker container(s) if they are unresponsive.
- Scale worker replicas horizontally if load is consistently high.
- For large backlogs:
  - Temporarily increase worker concurrency.
  - Consider pausing new task submissions (frontend messaging and/or rate limiting).

Document root cause and remediation in a post-incident note.

---

### 4.2. High Error Rate from LLM Provider

**Symptoms:**

- Many tasks end with `status = "failed"` and errors referencing LLM calls.
- Logs show repeated HTTP errors (429, 5xx) to LLM endpoints.

**Checklist:**

1. Verify status page of the LLM provider.
2. Inspect error messages:
   - `429` – rate limit exceeded.
   - `5xx` – provider internal error.
   - Connection/reset errors – network or TLS issues.
3. Check usage and quotas:
   - In the provider’s dashboard, verify monthly/daily limits.

**Mitigation:**

- For **rate limit** issues:
  - Lower concurrency or enforce stricter rate limiting.
  - Implement exponential backoff on retries (if not already).
- For provider outages:
  - Gracefully degrade:
    - Return a clear error message to the client.
    - Optionally disable new task submissions temporarily.
- Consider temporarily switching models (if configured) to an alternative.

Update `operational-runbook.md` after incidents to include patterns and resolutions.

---

### 4.3. MongoDB Connectivity Issues

**Symptoms:**

- API and worker logs show connection errors to MongoDB.
- `GET /v1/tasks` fails or is slow.

**Checklist:**

1. Check MongoDB Atlas:
   - Cluster status.
   - Recent maintenance or deployment events.
2. Verify network:
   - If Atlas is IP-whitelisted:
     - Confirm EC2 public IP or VPC Peering/VPC Private Endpoint is configured correctly.
3. Check connection string (`MONGO_URI`) in Parameter Store.

**Mitigation:**

- If an IP-based whitelist is used:
  - Update firewall rules / Atlas IP access list.
- If outage persists:
  - Treat as partial service degradation; document the period and behavior.

---

### 4.4. Redis / Valkey Issues

**Symptoms:**

- Queue operations fail; API may not be able to enqueue tasks.
- Worker logs show Redis connection errors.

**Checklist:**

1. AWS console:
   - ElastiCache → cluster status.
2. CloudWatch metrics:
   - CPU Utilization
   - Engine CPU
   - Memory usage
   - Connection count
3. Check Security Groups:
   - Ensure `sg-agent-orchestrator-ec2` still has permission to connect to `sg-agent-orchestrator-redis` on port 6379.

**Mitigation:**

- If memory pressure is high:
  - Reduce task rate.
  - Consider resizing the node or adding replicas.
- If cluster is unhealthy:
  - Follow AWS recommendations for failover or restoring from snapshot.

---

### 4.5. CodeDeploy Deployment Fails

**Symptoms:**

- CodeDeploy deployment status is `Failed`.
- New code is not running on EC2.

**Checklist:**

1. In CodeDeploy console:
   - Inspect deployment details and lifecycle events.
2. On EC2:
   - Check CodeDeploy logs:
     - Under `/opt/codedeploy-agent/deployment-root/` (path may vary).
3. Look at `BeforeInstall`, `ApplicationStart`, `ApplicationStop` logs:
   - Validate scripts exist and are executable.
   - Validate environment variables are available.

**Mitigation:**

- Fix the root cause (missing file, permission issue, failing script).
- Create a new deployment.
- If necessary, manually redeploy a known good revision.

Document the failure and fix in the repository (e.g., in a `CHANGELOG` or incident record).

---

## 5. Logs and Tracing

### 5.1. Where to Find Logs

- **Application logs:**
  - CloudWatch Log Groups:
    - `/agent-orchestrator/api`
    - `/agent-orchestrator/worker`
- **CodeDeploy logs:**
  - EC2 instance under CodeDeploy deployment root.
- **CloudWatch Agent logs:**
  - `amazon-cloudwatch-agent.log` on EC2 (if used).

Use filters on:

- `task_id`
- `request_id`
- `agent_name`
- `level` (`ERROR`, `WARN`)

to quickly narrow down relevant events.

---

## 6. Configuration and Secrets

### 6.1. Parameter Store Usage

- All sensitive configuration is stored under:

  - `/agent-orchestrator-api/dev/*`
  - `/agent-orchestrator-api/prod/*`

- Examples:
  - `MONGO_URI`
  - `REDIS_URL`
  - `OPENAI_API_KEY`
  - `TAVILY_API_KEY`

**Operational tasks:**

- Updating values:
  - Use AWS console or CLI to update parameters.
  - For `SecureString`, ensure correct KMS key is used.
- Rotating keys:
  - Update parameter in SSM.
  - Redeploy or restart services if necessary.

### 6.2. Verifying Access From EC2

On an EC2 instance:

- Use CLI to fetch dev parameters:

  ```text
  aws ssm get-parameters-by-path \
    --path "/agent-orchestrator-api/dev/" \
    --with-decryption \
    --region eu-central-1
````

If access denied, review IAM role policies.

---

## 7. Capacity Planning and Scaling

### 7.1. Scaling Workers

* If queue length remains high and latency grows:

  * Add more worker containers on the same EC2 instance (if resources allow).
  * Or scale horizontally by adding more EC2 instances with worker containers.
* Monitor:

  * CPU usage on worker hosts.
  * Redis performance.
  * LLM error rates (rate limit).

### 7.2. Scaling API

* If API latency or error rate increases under load:

  * Scale up EC2 instance type (more CPU/RAM).
  * Long term: introduce an Auto Scaling Group behind an ALB.

Document any scaling changes and update capacity assumptions.

---

## 8. On-Call Checklist

When paged:

1. Check service health:

   * `/health` and `/v1/system/metrics`.
2. Check logs:

   * CloudWatch log groups for recent errors.
3. Check dependencies:

   * MongoDB Atlas, ElastiCache, LLM provider status pages.
4. Decide:

   * Is this a **user-visible incident**? If yes, communicate to stakeholders.
5. Mitigate and stabilize:

   * Rollback if necessary.
   * Scale up or down.
   * Temporarily limit new tasks if needed.
6. Document:

   * Timeline, root cause, resolution, and follow-ups.

---

This runbook should evolve as the system grows. After any significant incident, update this file with new patterns, commands, and learnings.


