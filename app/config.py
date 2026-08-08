import json

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    kimi_api_key: str
    kimi_base_url: str = "https://api.moonshot.ai/v1"
    kimi_model: str = "kimi-k2.7-code"
    gateway_api_key: str = ""

    agent_github_repository: str = ""
    agent_github_branch: str = "main"
    agent_github_token: str = ""
    agent_write_enabled: bool = False
    agent_allowed_path_prefixes: str = ""
    agent_max_tree_files: int = Field(default=500, ge=20, le=5000)
    agent_max_read_files: int = Field(default=12, ge=1, le=40)
    agent_max_change_files: int = Field(default=6, ge=1, le=20)
    agent_max_file_bytes: int = Field(default=120_000, ge=1_000, le=1_000_000)
    agent_max_context_bytes: int = Field(default=300_000, ge=10_000, le=2_000_000)
    agent_max_output_tokens: int = Field(default=8192, ge=512, le=32768)
    agent_proposal_ttl_seconds: int = Field(default=3600, ge=300, le=86400)

    agent_v2_enabled: bool = True
    agent_state_db_path: str = ".runtime/kimi-agent-v2.db"
    agent_knowledge_enabled: bool = True
    agent_knowledge_limit: int = Field(default=5, ge=0, le=20)
    agent_review_repair_attempts: int = Field(default=1, ge=0, le=2)
    agent_workflow_prefix: str = ".agent/workflows"
    agent_audit_limit: int = Field(default=200, ge=20, le=2000)
    agent_browser_verification_enabled: bool = True
    agent_safe_runner_mode: str = "github-actions"

    agent_v3_enabled: bool = True
    agent_semantic_search_enabled: bool = True
    agent_semantic_candidate_files: int = Field(default=12, ge=4, le=24)
    agent_semantic_top_k: int = Field(default=8, ge=2, le=16)
    agent_semantic_sample_chars: int = Field(default=1800, ge=500, le=5000)
    agent_preapproval_validation_enabled: bool = True
    agent_validation_repair_attempts: int = Field(default=2, ge=0, le=3)
    agent_validation_timeout_seconds: int = Field(default=90, ge=10, le=300)
    agent_validation_log_chars: int = Field(default=8000, ge=1000, le=20000)
    agent_snapshot_max_download_bytes: int = Field(default=25_000_000, ge=1_000_000, le=100_000_000)
    agent_ci_feedback_enabled: bool = True
    agent_ci_log_chars: int = Field(default=8000, ge=1000, le=20000)

    agent_v4_enabled: bool = True
    agent_model_router_enabled: bool = True
    agent_model_router_default: str = "kimi-k2.7-code"
    agent_model_router_fast: str = "kimi-k2.7-code-highspeed"
    agent_model_router_deep: str = "kimi-k3"
    agent_context_target_chars: int = Field(default=180_000, ge=20_000, le=800_000)
    agent_context_history_chars: int = Field(default=18_000, ge=2_000, le=100_000)
    agent_context_knowledge_chars: int = Field(default=12_000, ge=1_000, le=100_000)
    agent_run_token_budget: int = Field(default=60_000, ge=5_000, le=500_000)
    agent_run_cost_budget_usd: float = Field(default=0.0, ge=0.0, le=1000.0)
    agent_model_pricing_json: str = ""
    agent_run_retention_days: int = Field(default=30, ge=1, le=365)
    agent_recent_runs_limit: int = Field(default=50, ge=5, le=200)
    agent_per_file_approval_enabled: bool = True
    agent_ci_repair_enabled: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def allowed_path_prefixes(self) -> tuple[str, ...]:
        return tuple(
            value.strip().strip("/")
            for value in self.agent_allowed_path_prefixes.split(",")
            if value.strip()
        )

    @property
    def model_pricing(self) -> dict[str, dict[str, float]]:
        if not self.agent_model_pricing_json.strip():
            return {}
        try:
            payload = json.loads(self.agent_model_pricing_json)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}
        result: dict[str, dict[str, float]] = {}
        for model, rates in payload.items():
            if not isinstance(model, str) or not isinstance(rates, dict):
                continue
            try:
                input_rate = float(rates.get("input", 0.0))
                output_rate = float(rates.get("output", 0.0))
            except (TypeError, ValueError):
                continue
            if input_rate < 0 or output_rate < 0:
                continue
            result[model] = {"input": input_rate, "output": output_rate}
        return result


settings = Settings()
