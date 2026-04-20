"""Local single-user GitHub account and token helpers."""

import json
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import httpx

GITHUB_ACCOUNT_PATH = "data/github_account.json"
GITHUB_OAUTH_STATE_PATH = "data/github_oauth_state.json"
GITHUB_API_URL = "https://api.github.com"
GITHUB_OAUTH_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"
TOKEN_ENV_VARS = ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")


def _ensure_data_dir() -> None:
    Path("data").mkdir(parents=True, exist_ok=True)


def _chmod_owner_only(path: str) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _read_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json(path: str, data: Dict[str, Any]) -> None:
    _ensure_data_dir()
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)
    _chmod_owner_only(path)


def get_env_token_source() -> Optional[str]:
    """Return the first configured GitHub token env var name."""
    for key in TOKEN_ENV_VARS:
        if os.getenv(key):
            return key
    return None


def get_stored_account() -> Dict[str, Any]:
    """Return stored local GitHub account metadata and token."""
    return _read_json(GITHUB_ACCOUNT_PATH)


def get_github_token() -> Tuple[Optional[str], Optional[str]]:
    """Return a GitHub token and its source label without exposing it to callers."""
    for key in TOKEN_ENV_VARS:
        token = os.getenv(key)
        if token:
            return token, key
    account = get_stored_account()
    token = account.get("access_token")
    if token:
        return token, account.get("token_source") or "stored"
    return None, None


def get_github_headers() -> Dict[str, str]:
    """Return headers for GitHub API requests, including auth when configured."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "llm-dev-council",
    }
    token, _source = get_github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def get_github_status() -> Dict[str, Any]:
    """Return browser-safe GitHub account status."""
    account = get_stored_account()
    env_source = get_env_token_source()
    stored_connected = bool(account.get("access_token"))
    token_source = env_source or account.get("token_source")
    return {
        "connected": bool(env_source or stored_connected),
        "token_source": token_source,
        "oauth_configured": bool(os.getenv("GITHUB_OAUTH_CLIENT_ID") and os.getenv("GITHUB_OAUTH_CLIENT_SECRET")),
        "login": account.get("login") if stored_connected else None,
        "name": account.get("name") if stored_connected else None,
        "avatar_url": account.get("avatar_url") if stored_connected else None,
        "repo_access": bool(env_source or stored_connected),
        "copilot_available": bool(env_source or stored_connected),
        "stored_token": stored_connected,
    }


async def fetch_current_user(token: str) -> Dict[str, Any]:
    """Fetch the current GitHub user for a token."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            f"{GITHUB_API_URL}/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "llm-dev-council",
            },
        )
        response.raise_for_status()
        return response.json()


async def store_access_token(token: str, token_source: str = "local") -> Dict[str, Any]:
    """Store a local token with user metadata and restrictive file permissions."""
    user = await fetch_current_user(token)
    account = {
        "access_token": token,
        "token_source": token_source,
        "login": user.get("login"),
        "name": user.get("name"),
        "avatar_url": user.get("avatar_url"),
        "connected_at": datetime.utcnow().isoformat(),
    }
    _write_json(GITHUB_ACCOUNT_PATH, account)
    return get_github_status()


def disconnect_github() -> None:
    """Delete stored local GitHub token data."""
    try:
        os.remove(GITHUB_ACCOUNT_PATH)
    except FileNotFoundError:
        pass


def create_oauth_start(frontend_redirect: Optional[str] = None) -> Dict[str, Any]:
    """Create a GitHub OAuth authorization URL for the local account flow."""
    client_id = os.getenv("GITHUB_OAUTH_CLIENT_ID")
    client_secret = os.getenv("GITHUB_OAUTH_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("GITHUB_OAUTH_CLIENT_ID and GITHUB_OAUTH_CLIENT_SECRET are required")

    state = secrets.token_urlsafe(24)
    _write_json(GITHUB_OAUTH_STATE_PATH, {
        "state": state,
        "frontend_redirect": frontend_redirect,
        "created_at": datetime.utcnow().isoformat(),
    })
    scope = os.getenv("GITHUB_OAUTH_SCOPE", "").strip()
    scope_param = f"&scope={scope.replace(' ', '%20')}" if scope else ""
    url = (
        f"{GITHUB_OAUTH_AUTHORIZE_URL}"
        f"?client_id={client_id}"
        f"{scope_param}"
        f"&state={state}"
    )
    return {"authorization_url": url, "state": state}


async def complete_oauth_callback(code: str, state: str) -> Dict[str, Any]:
    """Exchange a GitHub OAuth code for a user token and store it locally."""
    saved = _read_json(GITHUB_OAUTH_STATE_PATH)
    if not saved or saved.get("state") != state:
        raise ValueError("Invalid OAuth state")

    client_id = os.getenv("GITHUB_OAUTH_CLIENT_ID")
    client_secret = os.getenv("GITHUB_OAUTH_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("GITHUB OAuth is not configured")

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            GITHUB_OAUTH_TOKEN_URL,
            headers={"Accept": "application/json"},
            json={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
            },
        )
        response.raise_for_status()
        data = response.json()

    token = data.get("access_token")
    if not token:
        raise RuntimeError(data.get("error_description") or "GitHub did not return an access token")

    try:
        os.remove(GITHUB_OAUTH_STATE_PATH)
    except FileNotFoundError:
        pass
    return await store_access_token(token, token_source="oauth")
