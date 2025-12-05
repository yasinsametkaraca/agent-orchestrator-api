# Contributing to `agent-orchestrator-api`

First of all, thank you for taking the time to contribute to **Agent Orchestrator**.  
This document describes how we work in this repository and what we expect from contributions.

The goals of this project:

- Production-grade, 12-factor compliant backend
- Clear agent orchestration (Peer Agent + sub agents)
- Strong observability, testability, and maintainability

Please read this document before opening a pull request.

---

## 1. Repository Scope

This repository contains the **backend** for Agent Orchestrator:

- FastAPI application (HTTP API)
- Peer Agent + sub agents (ContentAgent, CodeAgent, etc.)
- Celery worker and queue integration
- MongoDB, Redis and LLM integrations
- DevOps tooling (Docker, GitHub Actions, CodeDeploy scripts)

The frontend lives in a separate repo: `agent-orchestrator-dashboard`.

---

## 2. Getting Started (Local Development)

1. **Clone the repository**

   ```bash
   git clone https://github.com/<your-username>/agent-orchestrator-api.git
   cd agent-orchestrator-api
    ```

2. **Create and activate a virtualenv**

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**

   ```bash
   pip install -U pip
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

4. **Run services via Docker Compose (Mongo + Redis)**

   ```bash
   docker compose up -d mongo redis
   ```

5. **Run the API**

   ```bash
   uvicorn app.main:app --reload
   ```

6. **Run the worker**

   ```bash
   celery -A app.worker.celery_app worker -l info
   ```

7. **Run the tests**

   ```bash
   pytest
   ```

> All configuration must be provided via environment variables.
> See `.env.example` (if present) and `core/config.py` for details.

---

## 3. Branching Strategy

We use a **feature branch** workflow on top of the `main` branch.

* `main` – always green, always deployable.
* Feature branches follow this convention:

  ```text
  feature/<ticket-id>-short-description
  bugfix/<ticket-id>-short-description
  chore/<ticket-id>-short-description
  ```

  Examples:

  * `feature/SD-2-peer-agent-routing`
  * `bugfix/SD-7-fix-celery-timeout`
  * `chore/SD-10-update-dependencies`

### 3.1. Branch Protection

The `main` branch is protected:

* All changes must go through a **Pull Request**.
* CI **must pass** before merging.
* Merge commits are disallowed; we require a **linear history** (squash or rebase).

Never commit directly to `main`.

---

## 4. Commit Message Convention

We follow a simplified **Conventional Commits** style:

```text
<type>(<scope>): <short summary>

[optional body]

[optional footer(s)]
```

**Types** we use:

* `feat` – new feature
* `fix` – bug fix
* `chore` – tooling, maintenance, refactors without behavior change
* `docs` – documentation changes
* `test` – adding or updating tests
* `ci` – GitHub Actions / pipeline changes

**Examples:**

* `feat(api): add /v1/agent/execute endpoint`
* `fix(worker): handle unknown task type error`
* `chore(devops): add docker compose for local stack`
* `test(agents): cover peer agent routing`

---

## 5. Issues

Before starting work:

1. **Search existing issues** to avoid duplicates.
2. If there is no issue:

   * Open a new one using the **Feature Request** or **Bug Report** template.
3. Provide:

   * Clear description and motivation
   * Acceptance criteria
   * Context and relevant logs if applicable

Link your PR to the corresponding issue (e.g. `Closes #12`).

---

## 6. Pull Request Process

1. Create a feature branch from `main`.

2. Implement your changes, keeping commits logically grouped.

3. Ensure:

   ```bash
   ruff check app tests
   pytest
   ```

   are **green** locally.

4. Open a Pull Request:

   * Use the **PR template** provided.
   * Fill in the **Summary**, **Changes**, and **Testing** sections.
   * Attach screenshots or logs when relevant (e.g. for observability changes).

5. PR guidelines:

   * Keep PRs **small and focused** (ideally < 400 LOC effective changes).
   * Separate refactors from behavior changes when possible.
   * Update documentation (`README`, `docs/architecture.md`, etc.) if behavior or architecture changes.
   * If you touch infrastructure (Docker, CI, deployment scripts), explicitly describe impact.

6. After review comments:

   * Address feedback with follow-up commits.
   * Respond to comments where clarification is needed.

7. Once CI passes and approvals are in place, the PR can be merged using **“Squash and merge”**.

---

## 7. Coding Standards

### 7.1. Python (FastAPI, Celery, Agents)

* Python: **3.12**

* Type hints are **mandatory** for all new code.

* Follow **PEP 8** and use tools:

  * `ruff` for linting
  * `black` (if configured) for formatting
  * `mypy` (if enabled) for static typing

* Keep boundaries clear:

  * `app/api` – HTTP layer (FastAPI routes, request/response models)
  * `app/services` – business logic, orchestration
  * `app/agents` – PeerAgent, ContentAgent, CodeAgent, agent registry
  * `app/db/repositories` – data access only, no business logic
  * `app/llm` – LLM client abstractions and tools
  * `app/core` – config, logging, rate limiting, error handling

* No direct DB calls from routes; always go through a service + repository.

### 7.2. Agent Design

When adding or updating agents:

* Implement the `BaseAgent` protocol.
* Do not hardcode routing logic outside the **PeerAgent** graph.
* Register the new agent in `agents/registry.py`.
* Ensure that:

  * The agent prompt is clear, deterministic and focused.
  * The agent returns an `AgentOutput` with consistent structure.
  * Token usage and duration are tracked via `AGENT_RUN` records.

---

## 8. Testing

* All new code must be covered by **unit tests** or **integration tests**:

  * Services, repositories, and agents should have unit tests.
  * API endpoints should have integration tests using FastAPI TestClient and/or `httpx`.

* Place tests under `tests/` mirroring the app structure:

  ```text
  tests/
    api/
    services/
    agents/
    worker/
  ```

* Prefer **pytest** fixtures for shared setup (e.g. Mongo/Redis test clients).

* External services (OpenAI, Tavily, etc.) must be **mocked** in tests.

**Before opening a PR:**

```bash
ruff check app tests
pytest
```

All tests must pass.

---

## 9. Architecture & Design Principles

* Follow **12-Factor App** principles:

  * Configuration via environment variables.
  * Stateless API and worker processes.
  * Logs written to **stdout** in structured JSON (CloudWatch in production).

* Respect the **layered architecture**:

  * Do not mix API, service, persistence, and infrastructure concerns.
  * Keep side-effects (network calls, DB operations) close to the edge.

* Peer Agent & agents must remain **extensible**:

  * Adding a new agent should require only:

    * New agent class
    * Registry update
    * Minor prompt update in PeerAgent (if necessary)
  * No changes in API routes or worker task signature.

* Database model:

  * Use the defined Mongo collections (`tasks`, `agent_runs`, `messages`, `sessions`, `logs`, `system_metrics`).
  * Maintain consistency with the ER diagram in `docs/architecture.md`.

---

## 10. Security and Secrets

* **Never commit secrets** (API keys, passwords, tokens, etc.).
* Use environment variables and, in production, AWS SSM Parameter Store / Secrets Manager.
* If you see a secret accidentally committed:

  * Rotate the secret immediately.
  * Open a security-related issue and describe remediation steps.

---

## 11. CI/CD

* GitHub Actions workflows must:

  * Run lint and tests on every push and PR to `main`.
  * Build Docker images on merges to `main`.
  * Push images to ECR when configured.

* When modifying workflows:

  * Keep them small and readable.
  * Describe changes clearly in the PR.
  * Ensure backward compatibility when possible.

---

## 12. Documentation

* Keep **README.md** up to date after any major change (API surface, setup steps, etc.).
* Architectural decisions should be captured as **ADR** files under `docs/adr/`.
* Update or add diagrams (system, ER, sequence) when architecture changes in a meaningful way.

---

## 13. Questions & Support

If something is unclear:

* Check existing docs under `docs/`.
* Check open and closed issues.
* If you still have questions, open an issue with the label `question`.

Thank you for helping improve **Agent Orchestrator** and keeping the codebase clean, modular, and production-ready.
