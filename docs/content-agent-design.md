# ContentAgent Design

## 1. Purpose

`ContentAgent` is responsible for generating **high-quality, long-form content** such as blog posts, technical explanations, and narrative responses in natural language.

Key goals:

- Produce structured, readable content (e.g. headings, paragraphs, bullet lists).
- Use **web search** to ground answers and provide citations.
- Respect task intent and style (e.g. beginner-friendly vs. expert tone).
- Be modular so that different LLMs or search providers can be plugged in.

---

## 2. Input and Output

### 2.1. Input

Domain `Task` model fields used by `ContentAgent`:

- `task_id`
- `input_text` – user’s original request
- `session_id` – to optionally pull past context
- `metadata` – optional extra information (locale, user type, etc.)
- Optional: previous conversation messages from `messages` collection

### 2.2. Output

`AgentOutput`:

- `agent_name = "ContentAgent"`
- `content` – Markdown/HTML-safe text containing:
  - Title or heading
  - Introductory paragraph
  - Main sections with headings
  - Optional conclusion
- `code_language = null` (usually)
- `citations[]` – list of sources with:
  - `source` (e.g. `"tavily"`)
  - `title` (if known)
  - `url`

The backend persists:

- Full content in `tasks.result.raw_output`.
- Citations in `tasks.result.citations`.

---

## 3. High-Level Processing Flow

1. **Task Interpretation**
   - Normalize and lightly summarize `input_text`.
   - Optionally adjust prompt based on `session_id` (prior tasks).

2. **Web Search Phase**
   - Generate a concise search query from the user’s request.
   - Call the configured provider (e.g. Tavily):
     - Use `WEB_SEARCH_PROVIDER`, `TAVILY_API_KEY`.
     - Fetch top `WEB_SEARCH_MAX_RESULTS` results (3–5 typical).
   - Extract:
     - Title
     - URL
     - Short snippets or abstracts
   - Optionally discard low-quality or irrelevant results.

3. **Content Generation Phase**
   - Construct an LLM prompt including:
     - System instructions:
       - Write clearly.
       - Use headings and lists where appropriate.
       - Avoid hallucinating facts; rely on provided sources.
     - User request (`input_text`).
     - Web search results (titles, URLs, short snippets).
   - Call `LLM_CONTENT_MODEL` with:
     - Max tokens configured (e.g. `LLM_MAX_TOKENS`).
     - Temperature tuned for content (e.g. moderately creative).
   - Parse and validate output:
     - Ensure response is not empty.
     - Optionally validate presence of headings and sections.

4. **Citation Extraction**
   - Map references in the generated text back to search results.
   - Populate `citations[]` with `source = "tavily"`, `title`, `url`.

5. **Persistence**
   - Store `AgentOutput` in:
     - `tasks.result`
     - `agent_runs` (for the `ContentAgent` invocation)
     - `messages` (assistant message for future sessions)

---

## 4. Prompting Strategy (Conceptual)

The `ContentAgent` uses role-based prompting:

- **System role:**
  - Defines behavior:
    - “You are a content-generation agent that writes accurate, well-structured articles.”
    - “Use the provided web search results for facts.”
    - “Include a short summary, main body, and optional conclusion.”

- **User role:**
  - Carries the user’s original task.

- **Tool/context section:**
  - Lists the search results in a compact format:
    - e.g., `[#1] Title – URL – snippet`

Constraints:

- Do not copy from sources verbatim; synthesize.
- Include references to sources (e.g. “According to [1] …”) if stylistically acceptable.
- Ensure the final content is safe and non-harmful within constraints of the task.

---

## 5. Error Handling

Common error cases:

- **Web search failure:**
  - If search provider is down or returns errors:
    - Fallback to LLM-only generation.
    - Tag result as “uncited” in logs.
- **LLM failure (timeout, quota):**
  - Retry with backoff up to N times for transient errors.
  - On persistent failure:
    - Mark task as `failed`.
    - Record error type and message in `tasks.error`.

- **Insufficient content:**
  - If content is too short or empty:
    - Optionally run a second pass instructing the model to elaborate.

All failures should be reflected in logs and metrics.

---

## 6. Extensibility

`ContentAgent` should be easy to extend:

- Switch search provider:
  - Abstraction in `app/llm/tools/web_search` or similar.
- Introduce specialized content modes:
  - e.g. “SEO blog post”, “developer documentation”.
- Support multiple languages:
  - Use language tags in `metadata` and adapt prompts.

When adding new behaviors:

- Update `content-agent-design.md` accordingly.
- Ensure PeerAgent routing description mentions that `ContentAgent` covers these new content types if relevant.

---

## 7. Non-Goals

`ContentAgent` explicitly does **not**:

- Execute code or scripts.
- Access internal systems beyond allowed web search tools.
- Perform unsafe or disallowed actions (e.g. generating harmful content).

All content generation remains within the boundaries defined by policies and system prompts.
