"""Configuration for the LLM Council."""

import os
import json
from dotenv import load_dotenv
from pathlib import Path

# Load .env first (template/defaults), then .env.local (secrets) overrides
load_dotenv()
load_dotenv(".env.local")

# OpenRouter API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# OpenRouter API endpoint
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Data directory for conversation storage
DATA_DIR = "data/conversations"

# Config file path for persistent settings
CONFIG_PATH = "data/config.json"

# Default council configuration
DEFAULT_COUNCIL_MODELS = [
    "openai/gpt-5.1",
    "google/gemini-3-pro-preview",
    "anthropic/claude-sonnet-4.5",
    "x-ai/grok-4",
]

DEFAULT_CHAIRMAN_MODEL = "google/gemini-3-pro-preview"


def _ensure_data_dir():
    """Ensure the data directory exists."""
    Path("data").mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    """Load config from disk, falling back to defaults."""
    _ensure_data_dir()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {
        "council_models": DEFAULT_COUNCIL_MODELS,
        "chairman_model": DEFAULT_CHAIRMAN_MODEL,
    }


def save_config(config: dict) -> None:
    """Save config to disk atomically (temp file + fsync + rename)."""
    import tempfile
    _ensure_data_dir()
    tmp_path = CONFIG_PATH + ".tmp"
    try:
        with open(tmp_path, 'w') as f:
            json.dump(config, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, CONFIG_PATH)
    except BaseException:
        # Clean up temp file on any failure
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def get_council_models() -> list:
    """Get the current council models list.

    Priority: COUNCIL_MODELS env var > file config > defaults.
    The env var is set by mcp_server.py when --council-models is passed.
    """
    env_council = os.getenv("COUNCIL_MODELS")
    if env_council:
        return [m.strip() for m in env_council.split(",") if m.strip()]
    return load_config().get("council_models", DEFAULT_COUNCIL_MODELS)


def get_chairman_model() -> str:
    """Get the current chairman model.

    Priority: CHAIRMAN_MODEL env var > file config > defaults.
    The env var is set by mcp_server.py when --chairman-model is passed.
    """
    env_chairman = os.getenv("CHAIRMAN_MODEL")
    if env_chairman:
        return env_chairman
    return load_config().get("chairman_model", DEFAULT_CHAIRMAN_MODEL)


# Backward-compatible module-level constants (loaded once at import)
COUNCIL_MODELS = DEFAULT_COUNCIL_MODELS
CHAIRMAN_MODEL = DEFAULT_CHAIRMAN_MODEL
