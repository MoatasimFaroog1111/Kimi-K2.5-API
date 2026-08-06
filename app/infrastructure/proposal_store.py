from datetime import datetime, timedelta, timezone

from app.core.exceptions import ProposalNotFoundError
from app.domain.agent import ChangeProposal


class InMemoryProposalStore:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._items: dict[str, ChangeProposal] = {}

    def save(self, proposal: ChangeProposal) -> None:
        self._remove_expired()
        self._items[proposal.id] = proposal

    def get(self, proposal_id: str) -> ChangeProposal:
        self._remove_expired()
        proposal = self._items.get(proposal_id)
        if proposal is None:
            raise ProposalNotFoundError("Proposal was not found or has expired.")
        return proposal

    def _remove_expired(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [
            proposal_id
            for proposal_id, proposal in self._items.items()
            if now - proposal.created_at > self._ttl
        ]
        for proposal_id in expired:
            self._items.pop(proposal_id, None)
