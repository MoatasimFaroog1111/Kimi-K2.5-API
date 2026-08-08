---
description: Validate browser JavaScript modules and static frontend structure
---

// turbo-all
1. Run JavaScript syntax checks for every file under `app/static`.
2. Verify the main HTML references the modular chat and agent entrypoints.
3. Reject duplicate critical DOM IDs used by the chat and agent controllers.
4. Report syntax or integration failures without modifying source files.
