import re
from collections import defaultdict


class CodeSearchService:
    _TECH_HINTS = {
        "python": (".py",),
        "fastapi": (".py",),
        "javascript": (".js", ".mjs", ".cjs"),
        "frontend": (".js", ".css", ".html"),
        "css": (".css",),
        "html": (".html",),
        "test": ("test", "tests/", ".spec.", ".test."),
        "workflow": (".github/workflows/", ".agent/workflows/"),
        "security": ("security", "auth", "policy", "middleware"),
        "api": ("api/", "routes/", "schemas"),
        "database": ("db", "database", "repository", "store", "model"),
    }

    def rank_paths(
        self,
        query: str,
        paths: list[str],
        *,
        limit: int = 24,
    ) -> list[str]:
        terms = self._terms(query)
        scored: dict[str, int] = defaultdict(int)

        for path in paths:
            lowered = path.casefold()
            basename = lowered.rsplit("/", 1)[-1]
            for term in terms:
                if term in basename:
                    scored[path] += 8
                elif term in lowered:
                    scored[path] += 4

                for hint in self._TECH_HINTS.get(term, ()):
                    if hint in lowered:
                        scored[path] += 3

            if lowered.startswith("app/") or lowered.startswith("src/"):
                scored[path] += 1
            if "/test" in lowered or lowered.startswith("tests/"):
                scored[path] += 1

        ranked = sorted(
            paths,
            key=lambda path: (scored[path], -len(path), path),
            reverse=True,
        )
        positive = [path for path in ranked if scored[path] > 0]
        if positive:
            return positive[:limit]
        return ranked[:limit]

    @staticmethod
    def _terms(query: str) -> tuple[str, ...]:
        tokens = re.findall(r"[\w.-]{3,}", query.casefold(), flags=re.UNICODE)
        stopwords = {
            "this", "that", "with", "from", "into", "add", "make", "build",
            "create", "update", "change", "project", "feature", "please",
            "اريد", "أريد", "هذا", "هذه", "على", "الى", "إلى", "اضف", "أضف",
            "اجعل", "المشروع", "البرنامج",
        }
        return tuple(term for term in dict.fromkeys(tokens) if term not in stopwords)[:32]
