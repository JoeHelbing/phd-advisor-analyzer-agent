import os
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


def _resolve_paths(data: dict, base_dir: Path) -> dict:
    """Resolve all path fields relative to base_dir."""
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if (key.endswith("_path") or key.endswith("_file")) and isinstance(value, str):
                # Resolve path relative to base_dir
                result[key] = str(base_dir / value)
            elif isinstance(value, dict):
                result[key] = _resolve_paths(value, base_dir)
            else:
                result[key] = value
        return result
    return data


def _load_settings(config_path: Path | None = None) -> AppConfig:
    """Load settings from config path or default."""
    if config_path is None:
        # Default to config.toml in the same directory as this file (src/)
        config_path = Path(__file__).parent / "config.toml"
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path.absolute()}")

    # Resolve paths relative to config file location
    base_dir = config_path.parent.absolute()
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    data = _resolve_paths(data, base_dir)

    return AppConfig.model_validate(data)


def load_config(path: Path) -> AppConfig:
    """Load config from a specific path."""
    config_path = Path(path).absolute()
    base_dir = config_path.parent

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    data = _resolve_paths(data, base_dir)

    return AppConfig.model_validate(data)


# Allow override via environment variable or keep default
CONFIG_PATH = os.getenv("ANALYZER_CONFIG_PATH")
SETTINGS: AppConfig = _load_settings(
    Path(CONFIG_PATH) if CONFIG_PATH else None
)
