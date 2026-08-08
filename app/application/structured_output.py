import json
from typing import Any

from app.core.exceptions import AgentValidationError


class StructuredOutputParser:
    @staticmethod
    def parse_object(raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1]).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise AgentValidationError("Agent returned invalid structured output.")
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise AgentValidationError("Agent returned invalid JSON output.") from exc
        if not isinstance(payload, dict):
            raise AgentValidationError("Agent output must be a JSON object.")
        return payload
