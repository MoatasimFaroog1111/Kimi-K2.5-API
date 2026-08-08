import re
from datetime import datetime, timezone
from uuid import uuid4

from app.domain.agent import ChangeProposal
from app.domain.agent_v2 import KnowledgeItem, ReviewResult, ValidationPlan
from app.domain.ports import KnowledgeRepositoryPort


class ProjectKnowledgeService:
    def __init__(self, repository: KnowledgeRepositoryPort) -> None:
        self._repository = repository

    def retrieve(self, task: str, *, limit: int = 5) -> list[KnowledgeItem]:
        return self._repository.search(task, limit=limit)

    def recent(self, *, limit: int = 20) -> list[KnowledgeItem]:
        return self._repository.recent(limit=limit)

    def remember_proposal(
        self,
        proposal: ChangeProposal,
        *,
        review: ReviewResult | None = None,
        validation: ValidationPlan | None = None,
    ) -> KnowledgeItem:
        paths = tuple(change.path for change in proposal.changes)
        summary_parts = [proposal.summary.strip()]
        if review:
            summary_parts.append(
                f"Review score {review.score}/100; approved={review.approved}."
            )
            if review.findings:
                summary_parts.append("Review: " + "; ".join(review.findings[:4]))
        if validation and validation.workflow_profiles:
            summary_parts.append(
                "Validation profiles: " + ", ".join(validation.workflow_profiles)
            )
        now = datetime.now(timezone.utc)
        item = KnowledgeItem(
            id=f"ki-{uuid4().hex[:16]}",
            title=self._title(proposal.task),
            summary=" ".join(part for part in summary_parts if part),
            tags=self._tags(proposal.task, paths),
            paths=paths,
            source=f"proposal:{proposal.id}",
            created_at=now,
            updated_at=now,
        )
        self._repository.save(item)
        return item

    @staticmethod
    def serialize(items: list[KnowledgeItem]) -> list[dict[str, object]]:
        return [
            {
                "id": item.id,
                "title": item.title,
                "summary": item.summary,
                "tags": list(item.tags),
                "paths": list(item.paths),
                "source": item.source,
                "updated_at": item.updated_at.isoformat(),
            }
            for item in items
        ]

    @staticmethod
    def _title(task: str) -> str:
        compact = " ".join(task.split()).strip()
        return compact[:96] + ("…" if len(compact) > 96 else "")

    @staticmethod
    def _tags(task: str, paths: tuple[str, ...]) -> tuple[str, ...]:
        words = re.findall(r"[\w.-]{4,}", task.casefold(), flags=re.UNICODE)
        extensions = [
            path.rsplit(".", 1)[-1].casefold()
            for path in paths
            if "." in path.rsplit("/", 1)[-1]
        ]
        return tuple(dict.fromkeys([*words[:8], *extensions]))[:12]
