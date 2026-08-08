from uuid import uuid4

from app.domain.agent_v2 import AuditEvent
from app.domain.ports import AuditLogPort


class AgentAuditService:
    def __init__(self, repository: AuditLogPort) -> None:
        self._repository = repository

    def record(
        self,
        *,
        run_id: str,
        event_type: str,
        message: str,
        metadata: dict[str, object] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            id=f"audit-{uuid4().hex[:16]}",
            run_id=run_id,
            event_type=event_type,
            message=message,
            metadata=metadata or {},
        )
        self._repository.record(event)
        return event

    def recent(self, *, limit: int = 100) -> list[dict[str, object]]:
        return [
            {
                "id": event.id,
                "run_id": event.run_id,
                "event_type": event.event_type,
                "message": event.message,
                "metadata": event.metadata,
                "created_at": event.created_at.isoformat(),
            }
            for event in self._repository.recent(limit=limit)
        ]
