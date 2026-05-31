"""Test fixtures for bot tests."""
import os
import sys
import unittest.mock
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("BOT_TOKEN", "123456:TEST-FAKE-TOKEN")
os.environ.setdefault("API_BASE_URL", "http://localhost:3000")

# Mock aiogram before any test module imports it
aiogram_mock = unittest.mock.MagicMock()
aiogram_mock.Bot = unittest.mock.AsyncMock
sys.modules["aiogram"] = aiogram_mock
sys.modules["aiogram.types"] = unittest.mock.MagicMock()
