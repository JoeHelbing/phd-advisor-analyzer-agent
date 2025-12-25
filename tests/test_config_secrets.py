import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.config import SecretsConfig


def test_secrets_accept_google_ai_studio_key(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("GOOGLE_AI_STUDIO_API_KEY=test-key\n", encoding="utf-8")
    monkeypatch.delenv("GOOGLE_AI_STUDIO_API_KEY", raising=False)

    secrets = SecretsConfig(_env_file=env_path)

    assert secrets.google_ai_studio_api_key == "test-key"
