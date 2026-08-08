import json
from typing import Any

from app.application.prompts import (
    AGENT_IMPLEMENTER_SYSTEM_PROMPT,
    AGENT_PLANNER_SYSTEM_PROMPT,
    AGENT_REVIEWER_SYSTEM_PROMPT,
    AGENT_TESTER_SYSTEM_PROMPT,
)
from app.application.structured_output import StructuredOutputParser
from app.core.exceptions import AgentValidationError
from app.domain.agent import AgentPlan, ProposedFileChange, WorkspaceFile
from app.domain.agent_v2 import KnowledgeItem, ReviewResult, RiskAssessment, ValidationPlan
from app.domain.ports import LanguageModelPort


class PlannerAgent:
    def __init__(self, model: LanguageModelPort) -> None:
        self._model = model

    async def plan(
        self,
        *,
        task: str,
        history: list[dict[str, str]],
        tree: list[str],
        search_candidates: list[str],
        knowledge: list[KnowledgeItem],
        model: str,
        max_read_files: int,
    ) -> AgentPlan:
        raw = await self._model.complete(
            system_prompt=AGENT_PLANNER_SYSTEM_PROMPT,
            user_prompt=json.dumps(
                {
                    "task": task,
                    "recent_conversation": history[-8:],
                    "repository_tree": tree,
                    "code_search_candidates": search_candidates,
                    "project_knowledge": _knowledge_payload(knowledge),
                    "max_read_files": max_read_files,
                },
                ensure_ascii=False,
            ),
            model=model,
            max_tokens=2048,
        )
        payload = StructuredOutputParser.parse_object(raw)
        summary = str(payload.get("summary") or "Implementation plan").strip()
        steps = tuple(
            str(step).strip()
            for step in payload.get("steps", [])[:8]
            if str(step).strip()
        )
        if not steps:
            raise AgentValidationError("The planner returned no actionable steps.")

        tree_set = set(tree)
        selected: list[str] = []
        for raw_path in payload.get("files_to_read", [])[:max_read_files]:
            path = str(raw_path).strip()
            if path in tree_set and path not in selected:
                selected.append(path)

        return AgentPlan(
            summary=summary,
            steps=steps,
            files_to_read=tuple(selected),
        )


class CoderAgent:
    def __init__(self, model: LanguageModelPort) -> None:
        self._model = model

    async def implement(
        self,
        *,
        task: str,
        plan: AgentPlan,
        tree: list[str],
        files: list[WorkspaceFile],
        knowledge: list[KnowledgeItem],
        review_feedback: tuple[str, ...],
        model: str,
        max_tokens: int,
    ) -> tuple[str, list[dict[str, Any]]]:
        raw = await self._model.complete(
            system_prompt=AGENT_IMPLEMENTER_SYSTEM_PROMPT,
            user_prompt=json.dumps(
                {
                    "task": task,
                    "plan": {
                        "summary": plan.summary,
                        "steps": list(plan.steps),
                    },
                    "repository_tree": tree,
                    "project_knowledge": _knowledge_payload(knowledge),
                    "review_feedback": list(review_feedback),
                    "files": [
                        {"path": file.path, "content": file.content}
                        for file in files
                    ],
                },
                ensure_ascii=False,
            ),
            model=model,
            max_tokens=max_tokens,
        )
        payload = StructuredOutputParser.parse_object(raw)
        message = str(payload.get("assistant_message") or "").strip()
        changes = payload.get("changes") or []
        if not isinstance(changes, list):
            raise AgentValidationError("Coder changes must be a list.")
        return message, [item for item in changes if isinstance(item, dict)]


class ReviewerAgent:
    def __init__(self, model: LanguageModelPort) -> None:
        self._model = model

    async def review(
        self,
        *,
        task: str,
        plan: AgentPlan,
        files: list[WorkspaceFile],
        changes: list[ProposedFileChange],
        risk: RiskAssessment,
        knowledge: list[KnowledgeItem],
        model: str,
    ) -> ReviewResult:
        raw = await self._model.complete(
            system_prompt=AGENT_REVIEWER_SYSTEM_PROMPT,
            user_prompt=json.dumps(
                {
                    "task": task,
                    "plan": {
                        "summary": plan.summary,
                        "steps": list(plan.steps),
                    },
                    "current_files": [
                        {"path": file.path, "content": file.content}
                        for file in files
                    ],
                    "proposed_changes": [
                        {
                            "path": change.path,
                            "reason": change.reason,
                            "diff": change.diff,
                        }
                        for change in changes
                    ],
                    "deterministic_risk": {
                        "level": risk.level.value,
                        "reasons": list(risk.reasons),
                        "blocked": risk.blocked,
                    },
                    "project_knowledge": _knowledge_payload(knowledge),
                },
                ensure_ascii=False,
            ),
            model=model,
            max_tokens=2048,
        )
        payload = StructuredOutputParser.parse_object(raw)
        score = int(payload.get("score") or 0)
        score = max(0, min(score, 100))
        findings = tuple(
            str(item).strip()
            for item in payload.get("findings", [])[:12]
            if str(item).strip()
        )
        required = tuple(
            str(item).strip()
            for item in payload.get("required_changes", [])[:8]
            if str(item).strip()
        )
        approved = bool(payload.get("approved")) and not risk.blocked
        return ReviewResult(
            approved=approved,
            score=score,
            findings=findings,
            required_changes=required,
        )


class TesterAgent:
    def __init__(self, model: LanguageModelPort) -> None:
        self._model = model

    async def validation_plan(
        self,
        *,
        task: str,
        changes: list[ProposedFileChange],
        review: ReviewResult,
        suggested_profiles: tuple[str, ...],
        model: str,
    ) -> ValidationPlan:
        raw = await self._model.complete(
            system_prompt=AGENT_TESTER_SYSTEM_PROMPT,
            user_prompt=json.dumps(
                {
                    "task": task,
                    "changed_paths": [change.path for change in changes],
                    "review": {
                        "approved": review.approved,
                        "score": review.score,
                        "findings": list(review.findings),
                    },
                    "deterministic_workflow_profiles": list(suggested_profiles),
                },
                ensure_ascii=False,
            ),
            model=model,
            max_tokens=1536,
        )
        payload = StructuredOutputParser.parse_object(raw)
        checks = tuple(
            str(item).strip()
            for item in payload.get("checks", [])[:16]
            if str(item).strip()
        )
        profiles = tuple(
            str(item).strip()
            for item in payload.get("workflow_profiles", [])[:8]
            if str(item).strip()
        )
        merged_profiles = tuple(dict.fromkeys([*suggested_profiles, *profiles]))
        browser_required = bool(payload.get("browser_required")) or "browser-smoke" in merged_profiles
        if not checks:
            checks = ("Run repository-native validation for all changed files.",)
        return ValidationPlan(
            checks=checks,
            workflow_profiles=merged_profiles,
            browser_required=browser_required,
        )


def _knowledge_payload(items: list[KnowledgeItem]) -> list[dict[str, object]]:
    return [
        {
            "id": item.id,
            "title": item.title,
            "summary": item.summary,
            "tags": list(item.tags),
            "paths": list(item.paths),
            "updated_at": item.updated_at.isoformat(),
        }
        for item in items
    ]
