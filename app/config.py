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


settings = Settings()
