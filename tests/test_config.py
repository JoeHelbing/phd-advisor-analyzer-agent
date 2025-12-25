"""Tests for config loading."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.config import SETTINGS


def test_faculty_extractor_agent_config_exists():
    assert hasattr(SETTINGS, "faculty_extractor_agent")
    assert SETTINGS.faculty_extractor_agent.model != ""
    assert SETTINGS.faculty_extractor_agent.instructions_path.exists()


def test_faculty_extractor_agent_instructions_loadable():
    instructions = SETTINGS.faculty_extractor_agent.instructions
    assert "faculty" in instructions.lower() or "extract" in instructions.lower()
