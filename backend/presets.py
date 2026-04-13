"""JSON-based storage for model presets."""

import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

PRESETS_DIR = "data/presets"


def _ensure_dir():
    Path(PRESETS_DIR).mkdir(parents=True, exist_ok=True)


def _get_path(preset_id: str) -> str:
    return os.path.join(PRESETS_DIR, f"{preset_id}.json")


def list_presets() -> List[Dict[str, Any]]:
    """List all saved presets."""
    _ensure_dir()
    presets = []
    if not os.path.exists(PRESETS_DIR):
        return presets
    for filename in os.listdir(PRESETS_DIR):
        if filename.endswith('.json'):
            path = os.path.join(PRESETS_DIR, filename)
            with open(path, 'r') as f:
                data = json.load(f)
                presets.append({
                    "id": data["id"],
                    "name": data["name"],
                    "created_at": data.get("created_at", ""),
                    "council_models": data.get("council_models", []),
                    "chairman_model": data.get("chairman_model", ""),
                })
    presets.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return presets


def get_preset(preset_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific preset by ID."""
    path = _get_path(preset_id)
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        return json.load(f)


def save_preset(name: str, council_models: List[str], chairman_model: str) -> Dict[str, Any]:
    """Create a new preset."""
    _ensure_dir()
    import uuid
    preset_id = str(uuid.uuid4())[:8]
    preset = {
        "id": preset_id,
        "name": name,
        "created_at": datetime.utcnow().isoformat(),
        "council_models": council_models,
        "chairman_model": chairman_model,
    }
    path = _get_path(preset_id)
    with open(path, 'w') as f:
        json.dump(preset, f, indent=2)
    return preset


def delete_preset(preset_id: str) -> bool:
    """Delete a preset by ID."""
    path = _get_path(preset_id)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False
