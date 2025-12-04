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
