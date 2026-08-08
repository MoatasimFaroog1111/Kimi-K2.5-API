# Agent Runtime V4

Agent Runtime V4 extends Agent Intelligence V3 with persistent resumable execution, deterministic model routing, context budgeting, token/cost guards, per-file approval, historical run reopening, and separate CI repair proposals.

## Runtime pipeline

1. Create a persistent `AgentRun` in SQLite.
2. Route the task to an available Kimi model.
3. Bind model calls to the run token/cost budget.
4. Retrieve and compact conversation/project context.
5. Execute the V3 engineering pipeline using persistent safe checkpoints.
6. Honor pause/cancel requests at checkpoint boundaries.
7. Resume paused runs from the last persisted stage without rerunning completed stages.
8. Create a sandbox-validated proposal.
9. Require explicit file selection before any repository write.
10. Create a Pull Request containing only approved files.
11. Read CI feedback after approval.
12. If CI fails, create a new child repair run and a separate fix proposal based on the existing agent branch.

## SOLID and component boundaries

- `app/domain/agent_v4.py`: runtime value objects and state enums only.
- `app/domain/ports.py`: repository, snapshot, validation, CI, proposal, and run abstractions.
- `app/application/run_runtime_service.py`: run state transitions and checkpoint lifecycle.
- `app/application/model_router.py`: deterministic model selection policy.
- `app/application/context_manager.py`: history, memory, and whole-file context budgeting.
- `app/application/run_budget_service.py`: token/cost authorization and accounting.
- `app/application/budgeted_model.py`: model decorator that applies run budgets without coupling agents to persistence.
- `app/application/checkpoint_codec.py`: domain/checkpoint serialization boundary.
- `app/infrastructure/sqlite_run_store.py`: persistent run adapter.
- `app/infrastructure/github_workspace.py`: branch-aware read/snapshot/write/CI adapter.
- `app/application/agent_orchestrator.py`: stage coordination only.
- `app/container.py`: composition root and dependency injection.

## Pause, resume, and cancel

Pause and cancel are cooperative and checkpoint-safe. The system does not terminate an LLM HTTP call or subprocess halfway through a critical atomic operation. A request is persisted immediately, then applied at the next safe checkpoint between stages.

Persisted checkpoint stages include:

- discovery ready,
- plan ready,
- review ready,
- validation ready,
- sandbox ready,
- waiting approval.

A paused run can be reopened after browser refresh or Railway redeploy because both the runtime record and checkpoint live in the configured SQLite volume.

Cancellation is terminal. When a waiting-approval run is cancelled, its pending proposal is rejected so it cannot later be approved through another UI path.

## Model Router

Auto routing is deterministic and validates all selections against the models actually returned by the account:

- narrow/simple latency-sensitive work prefers `kimi-k2.7-code-highspeed`,
- normal coding work prefers `kimi-k2.7-code`,
- architecture, security, migration, refactor, or other complex work prefers `kimi-k3`.

If the preferred model is unavailable, the router falls back only to models confirmed available for the account. Turning Auto Model Router off preserves the user's explicit model selection.

## Context Manager

The Context Manager reduces context pressure without truncating source files that the Coder is allowed to edit:

- recent conversation is bounded by a character budget,
- project knowledge summaries are bounded separately,
- source files are kept whole,
- lower-priority files are dropped when the whole-file budget is exceeded,
- a `ContextReport` records original size, prepared size, estimated tokens, and dropped paths.

This preserves syntactic integrity and makes context compression visible in the UI.

## Token and cost budget

Every agent-only completion is wrapped by `BudgetedLanguageModel`.

- token usage is estimated conservatively from input/output characters,
- the next model call is rejected before execution if its projected token allowance exceeds the run budget,
- usage is persisted after each model call,
- Chat mode is not charged against Agent run budgets.

Dollar-cost tracking is intentionally disabled unless model pricing is explicitly configured through `AGENT_MODEL_PRICING_JSON`. V4 does not hard-code or guess current provider prices. When pricing is configured, the same budget guard can enforce `AGENT_RUN_COST_BUDGET_USD`.

## Per-file approval

When per-file approval is enabled, a reviewed/sandboxed proposal starts with no approved files. The UI displays one checkbox per changed file. The selected path set is persisted before approval.

The GitHub adapter independently filters proposed changes against `approved_paths`; therefore an unchecked file cannot be written merely because it remains present in the original proposal object.

`applied_paths` records what was actually written, and project memory records only those applied files.

## CI repair proposals

V4 never silently edits a Pull Request after the user approved it.

When CI completes with failure:

1. failed jobs, failed steps, and bounded log excerpts are collected,
2. the user can start a CI repair run,
3. that run reads the existing agent PR branch as its base,
4. the full security/reviewer/tester/sandbox pipeline runs again,
5. a new child proposal references the parent proposal,
6. explicit per-file approval is required again,
7. approval creates a separate branch and Pull Request targeting the parent agent branch.

This keeps every post-approval code mutation independently reviewable and reversible.

## Persistence

Runtime state uses the same configured SQLite database as V2/V3. On Railway with the attached Volume this is:

`/data/kimi-agent-v2.db`

V4 adds the `agent_runs` table. Existing `proposals`, `knowledge_items`, and `audit_events` remain compatible. Default proposal retention was extended to 30 days so waiting approvals and reopened runs have aligned persistence windows.
