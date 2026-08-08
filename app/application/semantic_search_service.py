import json

from app.application.code_structure import CodeStructureExtractor
from app.application.prompts import AGENT_SEMANTIC_RANKER_SYSTEM_PROMPT
from app.application.structured_output import StructuredOutputParser
from app.domain.agent import WorkspaceFile
from app.domain.agent_v3 import SemanticCodeHit
from app.domain.ports import LanguageModelPort


class SemanticCodeIntelligence:
    def __init__(
        self,
        model: LanguageModelPort,
        extractor: CodeStructureExtractor,
    ) -> None:
        self._model = model
        self._extractor = extractor

    async def rank(
        self,
        *,
        task: str,
        files: list[WorkspaceFile],
        model: str,
        limit: int,
        sample_chars: int,
    ) -> list[SemanticCodeHit]:
        if not files:
            return []

        descriptors = [
            self._extractor.describe(file, sample_chars=sample_chars)
            for file in files
        ]
        path_map = {file.path: file for file in files}
        descriptor_map = {str(item["path"]): item for item in descriptors}

        try:
            raw = await self._model.complete(
                system_prompt=AGENT_SEMANTIC_RANKER_SYSTEM_PROMPT,
                user_prompt=json.dumps(
                    {
                        "task": task,
                        "limit": limit,
                        "candidates": descriptors,
                    },
                    ensure_ascii=False,
                ),
                model=model,
                max_tokens=1536,
            )
            payload = StructuredOutputParser.parse_object(raw)
            raw_hits = payload.get("hits") or []
        except Exception:
            raw_hits = []

        hits: list[SemanticCodeHit] = []
        seen: set[str] = set()
        for item in raw_hits:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip()
            if path not in path_map or path in seen:
                continue
            score = max(0, min(int(item.get("score") or 0), 100))
            descriptor = descriptor_map[path]
            hits.append(
                SemanticCodeHit(
                    path=path,
                    score=score,
                    rationale=str(item.get("rationale") or "").strip(),
                    symbols=tuple(descriptor.get("symbols") or ()),
                )
            )
            seen.add(path)
            if len(hits) >= limit:
                break

        if not hits:
            for index, file in enumerate(files[:limit]):
                descriptor = descriptor_map[file.path]
                hits.append(
                    SemanticCodeHit(
                        path=file.path,
                        score=max(10, 70 - index * 5),
                        rationale="Fallback candidate from deterministic repository search.",
                        symbols=tuple(descriptor.get("symbols") or ()),
                    )
                )

        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[:limit]

    @staticmethod
    def serialize(hits: list[SemanticCodeHit]) -> list[dict[str, object]]:
        return [
            {
                "path": hit.path,
                "score": hit.score,
                "rationale": hit.rationale,
                "symbols": list(hit.symbols),
            }
            for hit in hits
        ]
