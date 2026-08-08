# Agent Core V2

Agent Core V2 turns the Kimi workspace into an approval-gated multi-agent coding system while preserving SOLID and component boundaries.

## Execution pipeline

1. **Memory** — retrieve relevant Knowledge Items from the project state store.
2. **Search** — rank repository paths against the current task.
3. **Planner** — produce a bounded implementation plan and explicit files to inspect.
4. **Coder** — propose complete-file replacements only for inspected files plus justified new files.
5. **Security** — run deterministic secret, sensitive-surface, and prompt-injection risk checks.
6. **Reviewer** — independently review correctness, SOLID boundaries, security, regressions, and testability.
7. **Repair** — allow a bounded coder repair cycle when the reviewer identifies blocking corrections.
8. **Tester** — produce explicit validation checks and reusable workflow profiles.
9. **Human approval** — no repository write occurs until the user approves the reviewed proposal.
10. **Pull Request** — write changes to a `kimi-agent/<proposal>` branch and open a PR.
11. **Knowledge update** — after explicit approval and PR creation, persist a Knowledge Item describing the accepted work.

## SOLID boundaries

- `app/domain` owns pure entities and ports.
- `app/application/agent_roles.py` contains independent Planner, Coder, Reviewer, and Tester components.
- `app/application/agent_orchestrator.py` coordinates roles without implementing persistence, GitHub, or UI logic.
- `app/application/agent_service.py` is the API-facing application facade for status, streaming, approval, memory, audit, workflows, and search.
- `app/application/change_validator.py` owns change validation and diff construction.
- `app/application/security_service.py` owns deterministic risk policy.
- `app/application/knowledge_service.py` owns project-memory behavior.
- `app/application/code_search_service.py` owns repository path ranking.
- `app/application/workflow_service.py` owns workflow discovery and profile selection.
- `app/infrastructure/sqlite_*` implements state persistence behind ports.
- `app/infrastructure/github_workspace.py` is the GitHub workspace adapter.
- `app/container.py` is the composition root and performs dependency injection.

## Persistent state

Agent memory, audit events, and pending proposals share the SQLite path configured by:

```text
AGENT_STATE_DB_PATH=.runtime/kimi-agent-v2.db
```

The default is persistent for the lifetime of the running Railway filesystem. To keep memory across Railway redeployments, mount a Railway Volume and point `AGENT_STATE_DB_PATH` to that volume, for example `/data/kimi-agent-v2.db`. No application-code change is required because persistence is injected through repository ports.

## Safe command runner

Agent Core V2 deliberately does **not** expose arbitrary shell execution from the Railway web process. Validation runs in GitHub Actions isolation.

Reusable workflow descriptions live in `.agent/workflows/`:

- `python-tests`
- `frontend-check`
- `security-review`
- `browser-smoke`
- `repository-smoke`

`.github/workflows/agent-validation.yml` runs Python compilation, unit tests, JavaScript syntax validation, a local FastAPI server, and real Chromium browser smoke checks. Browser screenshots are uploaded as workflow artifacts.

## Protected API capabilities

All Agent endpoints remain protected by `X-API-Key`:

- `GET /agent/status`
- `GET /agent/memory`
- `GET /agent/audit`
- `GET /agent/workflows`
- `GET /agent/search`
- `POST /agent/stream`
- `POST /agent/proposals/{id}/approve`
- `POST /agent/proposals/{id}/reject`
- `POST /agent/proposals/{id}/undo`

## Security invariants

- `.env`, private-key formats, generated dependencies, virtual environments, and build output are blocked by workspace policy.
- Existing files may not be modified unless the agent inspected their current contents.
- Real-looking embedded tokens and private keys block a proposal before approval.
- Security-sensitive surfaces are elevated to high risk.
- Independent reviewer approval is required before a proposal becomes user-approvable.
- GitHub writes occur only after explicit user approval and only through a dedicated branch + Pull Request.
- Audit events are written both to SQLite and structured application logs.

## Validation evidence

Agent Core V2 was validated through an isolated temporary `kimi-agent/...` Pull Request. Python compilation, unit tests, JavaScript syntax checks, FastAPI startup, and real Chromium desktop/mobile smoke tests completed successfully. The temporary validation PR was closed without merging.
