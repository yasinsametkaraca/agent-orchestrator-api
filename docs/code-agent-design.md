# CodeAgent Design

## 1. Purpose

`CodeAgent` is responsible for **code-related tasks**, including:

- Writing new code snippets based on a request.
- Explaining or refactoring existing code.
- Suggesting patterns or best practices.

Scope is limited to **static code generation and explanation**. The backend does **not** execute arbitrary user code.

---

## 2. Input and Output

### 2.1. Input

Domain `Task` fields used by `CodeAgent`:

- `task_id`
- `input_text` – description of the desired code or request (e.g. “write Python code to read a file and write another”).
- Optional: code samples embedded in the task.
- Optional: programming language hints.

### 2.2. Output

`AgentOutput`:

- `agent_name = "CodeAgent"`
- `content` – formatted text containing:
  - Short explanation (what the code does).
  - Code snippet(s) in fenced blocks.
- `code_language` – a string identifying the language (e.g. `python`, `typescript`).
- `citations` – typically empty for code tasks, unless external references are included.

The backend stores:

- Full response in `tasks.result.raw_output`.
- `code_language` in `tasks.result.code_language`.
- Agent run metadata in `agent_runs`.

---

## 3. High-Level Processing Flow

1. **Task Interpretation**
   - Parse the user task to determine:
     - Target language (if specified explicitly).
     - Required behavior and constraints (e.g. error handling, input validation).
   - For existing code:
     - Extract the code block from `input_text`.

2. **Prompt Construction**
   - System instructions:
     - “Act as a senior software engineer.”
     - “Produce clean, production-oriented code.”
     - “Include minimal but clear explanation before the code.”
   - User instructions:
     - Directly from `input_text`.
   - Additional constraints:
     - Avoid external dependencies where not necessary.
     - Emphasize readability and robustness.

3. **LLM Invocation**
   - Call `LLM_CODE_MODEL`:
     - Use a reasoning-capable model (e.g. `o3-mini`).
     - Configure appropriate max tokens and temperature.
   - Encourage structured output:
     - Explanation + code snippet.

4. **Post-Processing**
   - Identify the dominant language (if not explicit) from the output.
   - Normalize `code_language` (e.g. `python`, `typescript`, `bash`).
   - Optionally:
     - Light validation of code format (e.g. presence of a fenced block).

5. **Persistence**
   - Save `AgentOutput` into `tasks` and `agent_runs`.
   - Store the generated code as-is; it is up to clients to execute or copy it safely.

---

## 4. Prompting Strategy (Conceptual)

`CodeAgent` prompts should encourage:

- Clear separation between explanation and code.
- Idiomatic style for the chosen language.
- Inclusion of basic error handling where relevant.

Example conceptual system guidelines:

- “Prefer explicit error checks, avoid overly clever one-liners.”
- “Use meaningful variable and function names.”
- “Assume modern, maintained versions of the language and common libraries.”

For refactor / explanation tasks:

- Ask the model to:
  - Rewrite the code with improvements.
  - Highlight what changed and why.

---

## 5. Error Handling

Common issues:

- **LLM errors (timeouts, rate limits):**
  - Handled at the LLM client layer with retries where appropriate.
- **Ambiguous language:**
  - If the user doesn’t specify the language and it’s genuinely unclear:
    - The agent may:
      - Choose a default (e.g. Python) and state this explicitly.
- **Oversized responses:**
  - For very large tasks, code may be truncated by token limits.
  - In these cases:
    - Encourage user to narrow the request or provide a smaller sample.

If CodeAgent cannot produce a meaningful result, the task is marked `failed` with a descriptive error message.

---

## 6. Extensibility

Future enhancements:

- Mode selection:
  - `mode = "write" | "explain" | "refactor" | "test"` (via metadata or explicit task hints).
- Multi-file or project-level guidance:
  - E.g., designing entire microservices or modules.
- Integration with static analysis tools (outside the LLM):
  - Linting or type-checking suggestions could be combined with model output.

When extending CodeAgent, ensure:

- PeerAgent routing prompt is updated if new code-related intents are covered.
- Logging and metrics distinguish between modes (e.g. `agent_mode: "refactor"`).

---

## 7. Non-Goals

`CodeAgent` does **not**:

- Execute untrusted code.
- Access production databases or internal services.
- Guarantee correctness or security of generated code.

All code produced is **advisory**; consumes must treat it as a starting point and review accordingly.
```

---

You can now:

* Create each file under your repo with the given path.
* Paste the corresponding block into it.
* Commit as a documentation/configuration update (e.g. `docs: add backend architecture and runbook`).

If you want, next step we can do the same level of treatment for **CI/CD YAML**, **appspec hooks description** (still without writing actual backend code), or we can refine any of these docs further.
