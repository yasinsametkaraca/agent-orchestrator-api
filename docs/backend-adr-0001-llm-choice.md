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
