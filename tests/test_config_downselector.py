import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.config import SETTINGS  # noqa: E402


def test_downselector_model_config_present():
    assert SETTINGS.models.downselector_agent.model
