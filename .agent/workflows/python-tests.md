---
description: Validate Python syntax and repository tests safely
---

// turbo-all
1. Compile the Python application with `python -m compileall app`.
2. Run repository unit tests with `python -m unittest discover -s tests -v`.
3. Fail the validation if either command exits non-zero.
4. Report the failing module or test without modifying source files.
