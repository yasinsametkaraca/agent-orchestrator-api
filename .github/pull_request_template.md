## Summary

Explain the motivation and context.  
What problem does this PR solve? Why now?

## Type of Change

Select one (or more) that applies:

- [ ] feat (new feature)
- [ ] fix (bug fix)
- [ ] chore (maintenance / refactor / tooling)
- [ ] docs (documentation only)
- [ ] test (tests only)
- [ ] ci (CI/CD or pipeline changes)

## Scope

Which areas are affected?

- [ ] API (FastAPI routes, schemas, request/response layer)
- [ ] Agents (PeerAgent, ContentAgent, CodeAgent, registry)
- [ ] Worker / Celery
- [ ] Database / Repositories
- [ ] LLM / External integrations
- [ ] DevOps (Docker, GitHub Actions, AWS, CodeDeploy, etc.)
- [ ] Other (specify below)

Additional scope notes (if any):

```text
- ...
- ...
```

## Changes

Briefly list the main changes in this PR:

* …
* …
* …

If this PR introduces or changes external APIs (HTTP endpoints, payloads), document them here:

```text
Endpoint: GET /v1/...
Request:
- ...
Response:
- ...
Breaking? (yes/no):
- ...
```

## Testing

Describe how you tested your changes.

Automated tests:

* [ ] `pytest`
* [ ] `pytest -m "integration"`
* [ ] Other (specify):

```text
Command(s) run:
- ...
Result:
- ...
```

Manual tests:

```text
1. Step 1: ...
2. Step 2: ...
3. Expected: ...
4. Actual: ...
```

If you added or changed tests, list the key scenarios covered:

* [ ] Happy path
* [ ] Error / edge cases
* [ ] Regression for previously reported bug (if applicable)

## Risks & Impact

* Does this change introduce potential regressions?
* Any performance implications?
* Any operational impact (deploy, config, migrations)?

```text
Risks:
- ...

Mitigations:
- ...
```

## Breaking Changes

* [ ] Yes
* [ ] No

If **yes**, describe clearly:

* What breaks?
* Who is affected (API consumers, infra, other services)?
* Migration path / rollout plan:

```text
- Step 1:
- Step 2:
- Rollback strategy:
```

## Deployment / Rollout Notes

Is a special deployment or coordination needed?

* [ ] No, standard deployment
* [ ] Yes (describe below)

```text
- Requires DB migration? (yes/no)
- Requires new ENV variables? (yes/no)
- Infra changes (AWS, security groups, etc.): ...
```

## Screenshots / Logs (Optional)

If helpful, add screenshots (for metrics, dashboards, error UIs) or relevant log snippets.

```text
<attach or describe here>
```

## Checklist

Please confirm that your PR meets the following:

* [ ] Code follows project conventions (architecture, naming, folder structure).
* [ ] Public interfaces (API endpoints, models) are documented or unchanged.
* [ ] New/changed behavior is covered by tests.
* [ ] Logging is adequate and structured (no secrets in logs).
* [ ] Configuration is driven via environment variables (no hard-coded secrets).
* [ ] No sensitive data is printed to logs or errors.
* [ ] Docs/README/architecture diagrams are updated if needed.
* [ ] Linked related issue(s) (e.g. `Closes #123`).
