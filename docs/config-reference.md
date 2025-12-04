# Configuration Reference – Agent Orchestrator Backend

This document lists **all configuration knobs** for the backend service, their purpose, and where they are stored (environment variables, SSM Parameter Store).

The backend follows **12-Factor App** guidelines: configuration is externalized and **never hard-coded**.

---

## 1. Environments

We distinguish the following environments:

- `local` – Developer machine / Docker Compose.
- `dev` – Shared development environment on AWS.
- `prod` – Production environment.

Runtime environment is controlled via:

- `ENVIRONMENT` – one of `local`, `dev`, `prod`.

---

## 2. Core Application Config

| Name                        | Type    | Example                        | Description                                          |
|-----------------------------|---------|--------------------------------|------------------------------------------------------|
| `APP_NAME`                  | String  | `agent-orchestrator-api`      | Logical application name.                           |
| `ENVIRONMENT`               | String  | `dev`                          | Runtime environment (`local`, `dev`, `prod`).       |
| `LOG_LEVEL`                 | String  | `INFO`                         | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`).|
| `API_RATE_LIMIT_PER_MINUTE` | Integer | `60`                           | Requests per minute per IP/API key.                 |
| `CORS_ORIGINS`              | String  | `https://dashboard.example`   | Comma-separated list of allowed origins.            |
| `API_KEYS`                  | String  | `key1,key2`                    | Optional list of API keys for simple auth.          |

**SSM Hierarchy Examples:**

- `/agent-orchestrator-api/dev/APP_NAME`
- `/agent-orchestrator-api/dev/ENVIRONMENT`
- `/agent-orchestrator-api/dev/LOG_LEVEL`
- `/agent-orchestrator-api/dev/API_RATE_LIMIT_PER_MINUTE`
- `/agent-orchestrator-api/dev/CORS_ORIGINS`

---

## 3. LLM Configuration

| Name               | Type         | Example            | Description                                   |
|--------------------|--------------|--------------------|-----------------------------------------------|
| `OPENAI_API_KEY`   | SecureString | `sk-...`           | OpenAI API key.                               |
| `LLM_PEER_MODEL`   | String       | `gpt-4.1-mini`     | Model for PeerAgent routing.                  |
| `LLM_CONTENT_MODEL`| String       | `gpt-4.1`          | Model for ContentAgent.                       |
| `LLM_CODE_MODEL`   | String       | `o3-mini`          | Model for CodeAgent.                          |
| `LLM_TIMEOUT_SEC`  | Integer      | `30`               | Global timeout for LLM calls.                 |
| `LLM_MAX_TOKENS`   | Integer      | `4096`             | Default max tokens per completion.            |

**SSM Examples:**

- `/agent-orchestrator-api/dev/OPENAI_API_KEY` (SecureString)
- `/agent-orchestrator-api/dev/LLM_PEER_MODEL`
- `/agent-orchestrator-api/dev/LLM_CONTENT_MODEL`
- `/agent-orchestrator-api/dev/LLM_CODE_MODEL`

---

## 4. Web Search / Tools

| Name                 | Type         | Example         | Description                                      |
|----------------------|--------------|-----------------|--------------------------------------------------|
| `WEB_SEARCH_PROVIDER`| String       | `tavily`        | Provider identifier (`tavily`, etc.).           |
| `TAVILY_API_KEY`     | SecureString | `tvly-...`      | Tavily (or equivalent) API key.                  |
| `WEB_SEARCH_MAX_RESULTS` | Integer | `5`             | Max number of search results per query.         |

**SSM Examples:**

- `/agent-orchestrator-api/dev/WEB_SEARCH_PROVIDER`
- `/agent-orchestrator-api/dev/TAVILY_API_KEY`
- `/agent-orchestrator-api/dev/WEB_SEARCH_MAX_RESULTS`

---

## 5. Database – MongoDB

| Name            | Type         | Example                       | Description                          |
|-----------------|--------------|-------------------------------|--------------------------------------|
| `MONGO_URI`     | SecureString | `mongodb+srv://...`          | Full MongoDB connection URI.        |
| `MONGO_DB_NAME` | String       | `agent_orchestrator`        | Database name.                       |

**SSM Examples:**

- `/agent-orchestrator-api/dev/MONGO_URI`
- `/agent-orchestrator-api/dev/MONGO_DB_NAME`

Connection string is obtained from MongoDB Atlas (or equivalent) and stored as a `SecureString`.

---

## 6. Redis / Queue / Rate Limiting

| Name                   | Type   | Example                                 | Description                                  |
|------------------------|--------|-----------------------------------------|----------------------------------------------|
| `REDIS_URL`            | String | `redis://host:6379/0`                  | Redis / Valkey endpoint for queue & cache.   |
| `CELERY_BROKER_URL`    | String | `redis://host:6379/0`                  | Celery broker URL (usually same as Redis).   |
| `CELERY_RESULT_BACKEND`| String | `redis://host:6379/1`                  | Celery result backend (optional).            |
| `RATE_LIMIT_REDIS_URL` | String | `redis://host:6379/2`                  | Optional separate Redis DB for rate limiting.|

**SSM Examples:**

- `/agent-orchestrator-api/dev/REDIS_URL`
- `/agent-orchestrator-api/dev/CELERY_BROKER_URL`
- `/agent-orchestrator-api/dev/CELERY_RESULT_BACKEND`

In production, these point to the ElastiCache Valkey primary endpoint.

---

## 7. Telemetry

| Name                         | Type   | Example                        | Description                              |
|------------------------------|--------|--------------------------------|------------------------------------------|
| `PROMETHEUS_ENABLED`         | Bool   | `true`                         | Whether `/metrics` endpoint is enabled.  |
| `OTEL_EXPORTER_OTLP_ENDPOINT`| String | `http://otel-collector:4317`   | OTLP endpoint if OpenTelemetry is used.  |

Telemetry config is optional and may be added as the system matures.

---

## 8. Environment-Specific Configuration Pattern

For each environment, values are stored under the corresponding SSM path:

- **dev:**
  - `/agent-orchestrator-api/dev/MONGO_URI`
  - `/agent-orchestrator-api/dev/REDIS_URL`
  - `/agent-orchestrator-api/dev/OPENAI_API_KEY`
  - `/agent-orchestrator-api/dev/LOG_LEVEL`
  - etc.

- **prod:**
  - `/agent-orchestrator-api/prod/MONGO_URI`
  - `/agent-orchestrator-api/prod/REDIS_URL`
  - `/agent-orchestrator-api/prod/OPENAI_API_KEY`
  - `/agent-orchestrator-api/prod/LOG_LEVEL`
  - etc.

EC2 IAM roles are granted **read** and **decrypt** permissions only for the relevant path (e.g. `/dev/*` for dev instances).

---

## 9. Local Development `.env` Example (Structure Only)

In local development, configuration is typically loaded from a `.env` file (not committed). Example keys:

```text
APP_NAME=agent-orchestrator-api
ENVIRONMENT=local
LOG_LEVEL=DEBUG

MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=agent_orchestrator

REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

OPENAI_API_KEY=...
LLM_PEER_MODEL=gpt-4.1-mini
LLM_CONTENT_MODEL=gpt-4.1
LLM_CODE_MODEL=o3-mini

WEB_SEARCH_PROVIDER=tavily
TAVILY_API_KEY=...

API_RATE_LIMIT_PER_MINUTE=60
CORS_ORIGINS=*
````

Values in `.env` **must never be committed** to version control.

---

This document should be kept up to date whenever new configuration options are introduced or existing ones are deprecated.
