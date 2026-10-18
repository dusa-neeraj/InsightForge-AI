from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    app_name: str = "AI Data Analyst Agent"
    max_upload_mb: int = 10
    allowed_origins: str = "http://localhost:5173"
    upload_dir: Path = BASE_DIR / "uploads"
    openai_api_key: str = ""  # used from Step 8 onwards
    openai_model: str = "gpt-4o-mini"
    rate_limit_enabled: bool = True
    rate_upload_per_min: int = 10
    rate_chat_per_min: int = 30
    rate_report_per_min: int = 6
    trust_proxy_headers: bool = False  # only turn on behind a proxy you control
    retention_hours: int = 168  # 0 keeps datasets forever
    llm_timeout_seconds: int = 30

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]
    


settings = Settings()