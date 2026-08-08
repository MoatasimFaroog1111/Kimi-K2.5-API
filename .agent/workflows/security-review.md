---
description: Validate sensitive paths, secrets, and approval boundaries
---

1. Review changed paths for authentication, deployment, workflow, dependency, and security-sensitive surfaces.
2. Scan changed text for embedded tokens, private keys, passwords, and API keys.
3. Verify `.env`, private-key files, generated dependencies, and vendor directories are not modified.
4. Confirm repository writes occur only through the approval-gated Pull Request path.
5. Escalate high-risk findings for human review instead of auto-applying changes.
