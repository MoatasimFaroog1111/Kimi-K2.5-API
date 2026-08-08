from app.domain.agent import ChangeProposal
from app.domain.agent_v3 import CiFeedback
from app.domain.ports import CiFeedbackPort


class CiFeedbackService:
    def __init__(self, provider: CiFeedbackPort) -> None:
        self._provider = provider

    async def feedback(self, proposal: ChangeProposal) -> CiFeedback:
        try:
            return await self._provider.feedback(proposal)
        except Exception:
            return CiFeedback(status="unavailable", conclusion=None)

    @staticmethod
    def serialize(feedback: CiFeedback) -> dict[str, object]:
        return {
            "status": feedback.status,
            "conclusion": feedback.conclusion,
            "checked_at": feedback.checked_at.isoformat(),
            "jobs": [
                {
                    "name": job.name,
                    "status": job.status,
                    "conclusion": job.conclusion,
                    "url": job.url,
                    "failed_steps": list(job.failed_steps),
                    "log_excerpt": job.log_excerpt,
                }
                for job in feedback.jobs
            ],
        }
