# Kimi Agent Mode

Agent Mode turns the existing chat gateway into a safe coding workflow that can
inspect a configured GitHub repository, create a verifiable plan, propose full
file replacements, show unified diffs, and open a pull request only after the
user explicitly approves the proposal.

## Safety model

- The browser never receives the GitHub token.
- Repository writes are disabled by default.
- The agent cannot execute arbitrary shell commands on Railway.
- Sensitive paths such as `.env`, private keys, virtual environments, generated
  dependencies, and build output are blocked.
- Existing files can only be changed after the agent has read their current
  content.
- Every write is made to a new `kimi-agent/<proposal-id>` branch.
- The protected branch is changed only through a GitHub pull request.
- The user can reject a proposal or close its pull request and delete the branch.

## Railway variables

Keep the existing variables and add these when repository analysis is needed:

```text
AGENT_GITHUB_REPOSITORY=owner/repository
AGENT_GITHUB_BRANCH=main
```

Public repositories can be analyzed in read-only mode without a token. To allow
approved pull requests, add:

```text
AGENT_GITHUB_TOKEN=<fine-grained GitHub token>
AGENT_WRITE_ENABLED=true
```

Recommended fine-grained token permissions for the selected repository:

- Contents: Read and write
- Pull requests: Read and write
- Metadata: Read

Optional limits:

```text
AGENT_ALLOWED_PATH_PREFIXES=app,tests,docs
AGENT_MAX_TREE_FILES=500
AGENT_MAX_READ_FILES=12
AGENT_MAX_CHANGE_FILES=6
AGENT_MAX_FILE_BYTES=120000
AGENT_MAX_CONTEXT_BYTES=300000
AGENT_MAX_OUTPUT_TOKENS=8192
AGENT_PROPOSAL_TTL_SECONDS=3600
```

## Architecture

The backend follows SOLID boundaries:

- `app/domain`: agent entities and dependency ports.
- `app/application`: chat and agent use cases plus prompts.
- `app/infrastructure`: GitHub workspace and proposal persistence adapters.
- `app/core`: policy and domain-level exceptions.
- `app/api`: authentication, routes, and HTTP error translation.
- `app/container.py`: application composition root.

The Agent frontend is component-based:

- `app/static/agent/api.js`: HTTP and NDJSON streaming adapter.
- `app/static/agent/store.js`: local Agent state and history.
- `app/static/agent/component.js`: accessible Agent workspace renderer.
- `app/static/agent/main.js`: orchestration and mode switching.
- `app/static/agent/agent.css`: isolated visual component styles.

## Agent lifecycle

1. Read workspace status and safe repository tree.
2. Ask Kimi for a structured, verifiable plan.
3. Read only the files selected by that plan.
4. Ask Kimi for structured complete-file proposals.
5. Validate paths, sizes, scope, and existing-file read requirements.
6. Show the plan, activity log, affected files, and unified diffs.
7. Wait for explicit approval.
8. Create a branch and pull request.
9. Let GitHub Actions validate the pull request.
10. Reject or undo by closing the pull request and deleting the branch.

## Persistence note

Conversations and Agent UI history are stored in the browser. Pending proposals
are held in memory on the Railway process and expire after the configured TTL.
A future production extension can replace `InMemoryProposalStore` with Redis or
a database without changing the application service.
