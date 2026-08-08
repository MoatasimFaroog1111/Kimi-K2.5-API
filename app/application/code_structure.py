import ast
import re
from pathlib import PurePosixPath

from app.domain.agent import WorkspaceFile


class CodeStructureExtractor:
    _JS_SYMBOL_RE = re.compile(
        r"(?:export\s+)?(?:async\s+)?(?:function|class)\s+([A-Za-z_$][\w$]*)|"
        r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"
    )
    _IMPORT_RE = re.compile(r"(?:from\s+['\"]([^'\"]+)['\"]|import\s+[^'\"]*['\"]([^'\"]+)['\"])")

    def describe(self, file: WorkspaceFile, *, sample_chars: int) -> dict[str, object]:
        suffix = PurePosixPath(file.path).suffix.lower()
        symbols: list[str] = []
        imports: list[str] = []
        summary = ""

        if suffix == ".py":
            symbols, imports, summary = self._python_structure(file.content)
        elif suffix in {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}:
            symbols, imports = self._javascript_structure(file.content)
        elif suffix in {".html", ".htm"}:
            symbols = re.findall(r"\bid=[\"']([^\"']+)[\"']", file.content)[:30]
        elif suffix in {".css", ".scss"}:
            symbols = re.findall(r"\.([A-Za-z_-][\w-]*)", file.content)[:30]

        sample = self._compact_sample(file.content, sample_chars)
        return {
            "path": file.path,
            "symbols": tuple(dict.fromkeys(symbols))[:40],
            "imports": tuple(dict.fromkeys(imports))[:30],
            "summary": summary,
            "sample": sample,
        }

    @staticmethod
    def _python_structure(content: str) -> tuple[list[str], list[str], str]:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return [], [], ""

        symbols: list[str] = []
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(f"function:{node.name}")
            elif isinstance(node, ast.ClassDef):
                symbols.append(f"class:{node.name}")
            elif isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.append(module)
        return symbols, imports, ast.get_docstring(tree) or ""

    def _javascript_structure(self, content: str) -> tuple[list[str], list[str]]:
        symbols: list[str] = []
        for match in self._JS_SYMBOL_RE.finditer(content):
            symbol = match.group(1) or match.group(2)
            if symbol:
                symbols.append(symbol)
        imports = [
            match.group(1) or match.group(2)
            for match in self._IMPORT_RE.finditer(content)
            if match.group(1) or match.group(2)
        ]
        return symbols, imports

    @staticmethod
    def _compact_sample(content: str, limit: int) -> str:
        lines = [line.rstrip() for line in content.splitlines()]
        meaningful = [line for line in lines if line.strip()][:120]
        sample = "\n".join(meaningful)
        return sample[:limit]
