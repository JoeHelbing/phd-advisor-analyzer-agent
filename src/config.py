import tomllib
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class SecretsConfig(BaseSettings):
    """API keys loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openrouter_api_key: str = ""
    google_search_api_key: str = ""
    google_search_engine_id: str = ""
    google_ai_studio_api_key: str = ""


class ModelConfig(BaseSettings):
    model: str
    temperature: float = 0.4
    max_output_tokens: int = 2048
    instructions_path: Path

    @property
    def instructions(self) -> str:
        return self.instructions_path.read_text()


class CrawlerSettings(BaseSettings):
    max_pages: int = 5
    request_timeout: int = 20


class RuntimeSettings(BaseSettings):
    professor_default_descriptor: str
    sop_path: Path
    db_path: Path
    log_file: Path | None = None


class ModelsConfig(BaseSettings):
    main_agent: ModelConfig
    recruiting_agent: ModelConfig
    downselector_agent: ModelConfig
    faculty_extractor_agent: ModelConfig
    scholar_finder_agent: ModelConfig
    paper_review_agent: ModelConfig


class AppConfig(BaseSettings):
    runtime: RuntimeSettings
    crawler: CrawlerSettings = CrawlerSettings()
    models: ModelsConfig
    secrets: SecretsConfig = SecretsConfig()

    @property
    def main_agent(self) -> ModelConfig:
        return self.models.main_agent

    @property
    def recruiting_agent(self) -> ModelConfig:
        return self.models.recruiting_agent

    @property
    def downselector_agent(self) -> ModelConfig:
        return self.models.downselector_agent

    @property
    def faculty_extractor_agent(self) -> ModelConfig:
        return self.models.faculty_extractor_agent

    @property
    def scholar_finder_agent(self) -> ModelConfig:
        return self.models.scholar_finder_agent

    @property
    def paper_review_agent(self) -> ModelConfig:
        return self.models.paper_review_agent

    @property
    def openrouter_api_key(self) -> str:
        return self.secrets.openrouter_api_key

    @property
    def google_api_key(self) -> str:
        return self.secrets.google_search_api_key

    @property
    def google_cse_id(self) -> str:
        return self.secrets.google_search_engine_id

    @property
    def google_ai_studio_api_key(self) -> str:
        return self.secrets.google_ai_studio_api_key


def _load_settings() -> AppConfig:
    """Load settings from default config path."""
    config_path = Path("config.toml")
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path.absolute()}")
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    return AppConfig.model_validate(data)


def load_config(path: Path) -> AppConfig:
    """Load config from a specific path."""
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return AppConfig.model_validate(data)


SETTINGS: AppConfig = _load_settings()
