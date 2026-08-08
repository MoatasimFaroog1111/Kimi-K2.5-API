# Agent Intelligence V3

Agent Intelligence V3 extends Agent Core V2 with semantic code understanding, real pre-approval execution checks, bounded automatic repair, and post-approval GitHub CI feedback while preserving approval-first repository writes.

## Pipeline

1. Persistent project memory retrieval.
2. Deterministic repository path search.
3. Semantic Code Intelligence over a bounded candidate set.
4. Planner selects verified files and implementation steps.
5. Coder proposes focused complete-file changes.
6. Deterministic security gate.
7. Independent Reviewer.
8. Tester selects repository-native validation profiles.
9. Pre-Approval Sandbox materializes a temporary repository snapshot and applies proposed changes only inside it.
10. Fixed allowlisted validation commands execute without a shell.
11. On validation failure, bounded log excerpts are returned to Coder for automatic root-cause repair.
12. Repaired changes pass through validation, security, Reviewer, Tester, and Sandbox again.
13. The user receives an approval action only after the required gates pass.
14. Explicit user approval creates a dedicated GitHub branch and Pull Request.
15. GitHub CI feedback is read back into the proposal and UI when repository permissions allow it.

## SOLID and component boundaries

- `app/domain/agent_v3.py` contains V3 domain value objects only.
- `app/domain/ports.py` defines snapshot, validation-runner, and CI-feedback ports.
- `app/application/code_structure.py` extracts local structural metadata from source files.
- `app/application/semantic_search_service.py` performs bounded semantic reranking behind an application component.
- `app/application/preapproval_validation_service.py` translates sandbox results into application-level validation and repair feedback.
- `app/application/ci_feedback_service.py` isolates post-approval CI feedback behavior.
- `app/infrastructure/isolated_validation_runner.py` is the execution adapter.
- `app/infrastructure/github_workspace.py` remains the GitHub/snapshot/CI infrastructure adapter.
- `app/application/agent_orchestrator.py` coordinates the pipeline but does not implement GitHub, SQLite, subprocess, or browser details.
- `app/container.py` is the composition root and injects all dependencies.

## Semantic Code Intelligence

V3 uses a hybrid bounded strategy rather than sending the full repository to a model:

1. Deterministic path search narrows the repository tree.
2. Only a configured number of candidate files are read.
3. `CodeStructureExtractor` extracts Python AST symbols/imports/docstrings and bounded structural metadata for JS/TS, HTML, and CSS.
4. Kimi semantically reranks those supplied candidates against the user's task.
5. Exact-path validation prevents the semantic component from inventing repository files.
6. A deterministic fallback remains available if semantic reranking fails.

This is semantic reranking, not a persistent vector database. A vector index can be introduced later behind the same search boundary without changing the Planner contract.

## Pre-Approval Sandbox

The sandbox deliberately does not expose an arbitrary terminal tool to the model.

- Repository state is downloaded into a Python `TemporaryDirectory`.
- Archive paths pass through `WorkspacePolicy` and path-traversal checks.
- Proposed edits are applied only inside the temporary snapshot.
- Validation uses `asyncio.create_subprocess_exec`, never `shell=True`.
- Commands are selected by application code, not by user/model text.
- Current local checks include Python compilation, Python unittest discovery, and JavaScript syntax checks when Node is available.
- Browser smoke is intentionally deferred to isolated GitHub Actions.
- Each process has a timeout and bounded captured output.

## Automatic validation repair

If a pre-approval check fails:

1. Failed check names and bounded output excerpts are converted to repair feedback.
2. Coder receives that feedback and proposes a corrected implementation.
3. Security and independent Reviewer run again.
4. Tester recalculates validation profiles.
5. The Sandbox reruns.
6. The number of automatic repair attempts is bounded by `AGENT_VALIDATION_REPAIR_ATTEMPTS`.
7. If failures remain, no approval proposal is created.

This preserves human approval while allowing the agent to repair ordinary compile/test failures before asking the user to review a change.

## GitHub CI feedback

After explicit approval creates a Pull Request, V3 can query GitHub Actions for the agent branch and report:

- workflow/job status,
- job conclusion,
- failed step names,
- bounded failed-job log excerpts when permitted,
- GitHub job links.

CI feedback is deliberately non-blocking after Pull Request creation. If the configured fine-grained GitHub token lacks Actions read permission, the UI reports CI as unavailable rather than failing the approved repository write.

## Persistence

The existing SQLite state store remains schema-compatible. V3 serializes Sandbox and CI state into the proposal JSON, so proposals, audit events, memory, validation results, and CI feedback continue to use the configured persistent database path, including `/data/kimi-agent-v2.db` on the attached Railway Volume.

## Validation evidence

V3 was validated using a temporary `kimi-agent/validate-intelligence-v3` Pull Request created only to trigger isolated checks. The PR was closed without merging. The following completed successfully:

- Python compilation,
- V2/V3 unit tests,
- real subprocess-based Sandbox tests,
- JavaScript syntax checks,
- modular frontend checks,
- FastAPI startup,
- real Chromium browser smoke verification,
- browser evidence artifact upload.

Railway also reported the V3 application deployment successful before the temporary validation PR was created.
