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
