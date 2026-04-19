"""JSON-based storage for MCP server configurations."""

import json
import os
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

MCP_SERVERS_PATH = "data/mcp_servers.json"


def _ensure_dir():
    Path("data").mkdir(parents=True, exist_ok=True)


def _load_raw() -> List[Dict[str, Any]]:
    _ensure_dir()
    if not os.path.exists(MCP_SERVERS_PATH):
        return []
    try:
        with open(MCP_SERVERS_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_raw(servers: List[Dict[str, Any]]):
    _ensure_dir()
    tmp_path = MCP_SERVERS_PATH + ".tmp"
    try:
        with open(tmp_path, "w") as f:
            json.dump(servers, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, MCP_SERVERS_PATH)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def list_servers() -> List[Dict[str, Any]]:
    """List all configured MCP servers."""
    return _load_raw()


def get_server(server_id: str) -> Optional[Dict[str, Any]]:
    """Get a single server by ID."""
    for s in _load_raw():
        if s.get("id") == server_id:
            return s
    return None


def add_server(server: Dict[str, Any]) -> Dict[str, Any]:
    """Add a new MCP server config."""
    servers = _load_raw()
    server["id"] = str(uuid.uuid4())[:8]
    server["created_at"] = datetime.utcnow().isoformat()
    servers.append(server)
    _save_raw(servers)
    return server


def update_server(server_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update an existing server config."""
    servers = _load_raw()
    for i, s in enumerate(servers):
        if s.get("id") == server_id:
            servers[i].update(updates)
            servers[i]["updated_at"] = datetime.utcnow().isoformat()
            _save_raw(servers)
            return servers[i]
    return None


def delete_server(server_id: str) -> bool:
    """Delete a server by ID."""
    servers = _load_raw()
    new_servers = [s for s in servers if s.get("id") != server_id]
    if len(new_servers) != len(servers):
        _save_raw(new_servers)
        return True
    return False
