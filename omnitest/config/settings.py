"""Central configuration, loaded from environment / .env (pydantic-settings)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_prefix="",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Claude ──────────────────────────────────────────
    anthropic_api_key: str = Field("", alias="ANTHROPIC_API_KEY")
    prompt_cache: bool = Field(True, alias="OMNI_PROMPT_CACHE")

    # ── Model routing: each tier -> (provider, model) ───
    # provider is 'anthropic' or 'ollama'. Point CHEAP at a local Ollama model
    # to run high-volume jobs for free; keep SMART on Claude for hard judgement.
    provider_cheap: str = Field("anthropic", alias="OMNI_PROVIDER_CHEAP")
    provider_balanced: str = Field("anthropic", alias="OMNI_PROVIDER_BALANCED")
    provider_smart: str = Field("anthropic", alias="OMNI_PROVIDER_SMART")
    model_cheap: str = Field("claude-haiku-4-5", alias="OMNI_MODEL_CHEAP")
    model_balanced: str = Field("claude-sonnet-5", alias="OMNI_MODEL_BALANCED")
    model_smart: str = Field("claude-opus-4-8", alias="OMNI_MODEL_SMART")

    # ── Local LLM (Ollama) ──────────────────────────────
    ollama_host: str = Field("http://localhost:11434", alias="OMNI_OLLAMA_HOST")

    # ── Alerting ────────────────────────────────────────
    slack_webhook_url: str = Field("", alias="OMNI_SLACK_WEBHOOK_URL")
    # Public base URL where the Allure report is published (CI/static host).
    # When set, Slack alerts include a clickable "Open Allure Report" button.
    report_base_url: str = Field("", alias="OMNI_REPORT_BASE_URL")

    # ── Prompt tracking (manager visibility) ────────────
    prompt_log_dir: Path = Field(Path("artifacts/prompts"), alias="OMNI_PROMPT_LOG_DIR")
    allure_results_dir: Path = Field(Path("artifacts/allure-results"), alias="OMNI_ALLURE_RESULTS_DIR")
    # Optional planned-story manifest (JSON) — the director dashboard joins it with
    # Allure results + prompt logs to show sprint throughput by story.
    stories_manifest: Path = Field(Path("docs/stories.json"), alias="OMNI_STORIES_MANIFEST")

    # ── App under test ──────────────────────────────────
    base_url: str = Field("https://example.com", alias="OMNI_BASE_URL")
    api_base_url: str = Field("https://api.example.com", alias="OMNI_API_BASE_URL")

    # ── Email ───────────────────────────────────────────
    email_backend: str = Field("smtp_imap", alias="OMNI_EMAIL_BACKEND")
    smtp_host: str = Field("smtp.gmail.com", alias="OMNI_SMTP_HOST")
    smtp_port: int = Field(587, alias="OMNI_SMTP_PORT")
    imap_host: str = Field("imap.gmail.com", alias="OMNI_IMAP_HOST")
    imap_port: int = Field(993, alias="OMNI_IMAP_PORT")
    email_user: str = Field("", alias="OMNI_EMAIL_USER")
    email_password: str = Field("", alias="OMNI_EMAIL_PASSWORD")
    gmail_credentials: Path = Field(Path("secrets/gmail_credentials.json"), alias="OMNI_GMAIL_CREDENTIALS")
    gmail_token: Path = Field(Path("secrets/gmail_token.json"), alias="OMNI_GMAIL_TOKEN")

    @property
    def abs_prompt_log_dir(self) -> Path:
        return self._abs(self.prompt_log_dir)

    @property
    def abs_allure_results_dir(self) -> Path:
        return self._abs(self.allure_results_dir)

    @property
    def abs_stories_manifest(self) -> Path:
        return self._abs(self.stories_manifest)

    @staticmethod
    def _abs(p: Path) -> Path:
        return p if p.is_absolute() else PROJECT_ROOT / p


@lru_cache
def _load() -> Settings:
    return Settings()


settings = _load()