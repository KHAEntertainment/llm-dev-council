"""Read-only virtual GitHub repository mounts."""

import base64
import fnmatch
import os
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx

from .github_account import GITHUB_API_URL, get_github_headers

_DEFAULT_SCOPE = "__global__"
_active_scope = _DEFAULT_SCOPE
_repo_mounts_by_scope: Dict[str, Dict[str, Dict[str, Any]]] = {_DEFAULT_SCOPE: {}}
MAX_FILE_SIZE = 1024 * 1024
MAX_SEARCH_RESULTS = 200
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class GitHubRepoError(Exception):
    """Raised for GitHub repository mount failures."""


def set_active_scope(scope: Optional[str]) -> None:
    """Select the conversation scope used by GitHub repo endpoints."""
    global _active_scope
    _active_scope = scope or _DEFAULT_SCOPE
    _repo_mounts_by_scope.setdefault(_active_scope, {})


def _get_scope_mounts(scope: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    scope_id = scope or _active_scope
    return _repo_mounts_by_scope.setdefault(scope_id, {})


def _parse_repo(repo: str) -> Tuple[str, str]:
    if not REPO_RE.match(repo):
        raise ValueError("Repository must be in owner/repo format")
    owner, name = repo.split("/", 1)
    return owner, name


def _normalize_path(path: Optional[str]) -> str:
    clean = (path or "").strip().strip("/")
    if clean == ".":
        return ""
    parts = clean.split("/") if clean else []
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("Repository path cannot contain empty, '.', or '..' segments")
    return "/".join(parts)


def _match_mount_path(mount: Dict[str, Any], path: str) -> bool:
    prefix = f"github://{mount['owner']}/{mount['repo']}@{mount['ref']}"
    mount_path = mount.get("path") or ""
    if mount_path:
        prefix = f"{prefix}/{mount_path}"
    return path == prefix or path.startswith(prefix + "/")


def _path_for_mount(mount: Dict[str, Any]) -> str:
    base = f"github://{mount['owner']}/{mount['repo']}@{mount['ref']}"
    if mount.get("path"):
        return f"{base}/{mount['path']}"
    return base


def _relative_path(mount: Dict[str, Any], path: str) -> str:
    base = _path_for_mount(mount)
    if path == base:
        return ""
    return _normalize_path(path[len(base):].lstrip("/"))


def _virtual_child_path(mount: Dict[str, Any], relative_path: str) -> str:
    base = _path_for_mount(mount)
    clean = _normalize_path(relative_path)
    return f"{base}/{clean}" if clean else base


def _resolve_mount(path_or_mount_id: str) -> Tuple[str, Dict[str, Any], str]:
    mounts = _get_scope_mounts()
    if path_or_mount_id in mounts:
        mount = mounts[path_or_mount_id]
        return path_or_mount_id, mount, ""
    for mount_id, mount in mounts.items():
        if _match_mount_path(mount, path_or_mount_id):
            return mount_id, mount, _relative_path(mount, path_or_mount_id)
    raise PermissionError(f"Path '{path_or_mount_id}' is not within any mounted GitHub repository")


async def _github_get(path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{GITHUB_API_URL}{path}",
            headers=get_github_headers(),
            params=params,
        )
        if response.status_code in (401, 403, 404):
            detail = "GitHub repository is not accessible with the configured credentials"
            raise PermissionError(detail)
        response.raise_for_status()
        return response.json()


async def _repo_info(owner: str, repo: str) -> Dict[str, Any]:
    return await _github_get(f"/repos/{owner}/{repo}")


async def _tree(owner: str, repo: str, ref: str, recursive: bool = True) -> List[Dict[str, Any]]:
    data = await _github_get(
        f"/repos/{owner}/{repo}/git/trees/{quote(ref, safe='')}",
        params={"recursive": "1"} if recursive else None,
    )
    tree = data.get("tree") or []
    return [item for item in tree if isinstance(item, dict)]


async def mount_repo(repo: str, ref: Optional[str] = None, path: Optional[str] = None) -> Dict[str, Any]:
    """Mount a GitHub repository read-only in the active scope."""
    owner, repo_name = _parse_repo(repo)
    clean_path = _normalize_path(path)
    info = await _repo_info(owner, repo_name)
    target_ref = ref or info.get("default_branch") or "main"
    # Validate ref/path by touching the tree.
    tree = await _tree(owner, repo_name, target_ref, recursive=True)
    if clean_path and not any(item.get("path") == clean_path or item.get("path", "").startswith(clean_path + "/") for item in tree):
        raise FileNotFoundError(f"Path not found in repository: {clean_path}")

    mounts = _get_scope_mounts()
    for mount_id, mount in mounts.items():
        if (
            mount["owner"].lower() == owner.lower()
            and mount["repo"].lower() == repo_name.lower()
            and mount["ref"] == target_ref
            and (mount.get("path") or "") == clean_path
        ):
            return {"mount_id": mount_id, **mount}

    mount_id = str(uuid.uuid4())[:8]
    mount_data = {
        "type": "github",
        "owner": owner,
        "repo": repo_name,
        "ref": target_ref,
        "path": clean_path,
        "name": f"{owner}/{repo_name}",
        "display_name": f"{owner}/{repo_name}@{target_ref}" + (f"/{clean_path}" if clean_path else ""),
        "mounted_at": datetime.utcnow().isoformat(),
        "read_only": True,
    }
    mounts[mount_id] = mount_data
    return {"mount_id": mount_id, **mount_data}


def unmount_repo(mount_id: str) -> bool:
    """Unmount a GitHub repository by mount ID."""
    mounts = _get_scope_mounts()
    if mount_id in mounts:
        del mounts[mount_id]
        return True
    return False


def list_mounts() -> List[Dict[str, Any]]:
    """List current GitHub repo mounts."""
    return [{"mount_id": mid, **data} for mid, data in _get_scope_mounts().items()]


async def _directory_entries_for_mount(mount: Dict[str, Any], rel: str = "") -> List[Dict[str, Any]]:
    mount_root = mount.get("path") or ""
    base_path = "/".join(part for part in [mount_root, rel] if part)
    tree = await _tree(mount["owner"], mount["repo"], mount["ref"], recursive=True)

    children: Dict[str, Dict[str, Any]] = {}
    prefix = base_path + "/" if base_path else ""
    for item in tree:
        item_path = item.get("path") or ""
        if base_path and item_path == base_path:
            continue
        if not item_path.startswith(prefix):
            continue
        remainder = item_path[len(prefix):]
        if not remainder:
            continue
        name = remainder.split("/", 1)[0]
        child_rel = "/".join(part for part in [rel, name] if part)
        existing = children.get(name)
        is_dir = "/" in remainder or item.get("type") == "tree"
        if existing and existing["type"] == "directory":
            continue
        children[name] = {
            "name": name,
            "path": _virtual_child_path(mount, child_rel),
            "type": "directory" if is_dir else "file",
            "size": None if is_dir else item.get("size"),
            "modified": None,
            "source": "github",
        }

    entries = list(children.values())
    entries.sort(key=lambda e: (e["type"] != "directory", e["name"].lower()))
    return entries


async def list_directory(path: str) -> List[Dict[str, Any]]:
    """List a virtual GitHub repository directory."""
    _mount_id, mount, rel = _resolve_mount(path)
    return await _directory_entries_for_mount(mount, rel)


async def read_file(path: str) -> Dict[str, Any]:
    """Read a file from a mounted GitHub repository."""
    _mount_id, mount, rel = _resolve_mount(path)
    repo_path = "/".join(part for part in [mount.get("path") or "", rel] if part)
    if not repo_path:
        raise FileNotFoundError("Path is a repository root, not a file")
    data = await _github_get(
        f"/repos/{mount['owner']}/{mount['repo']}/contents/{repo_path}",
        params={"ref": mount["ref"]},
    )
    if isinstance(data, list) or data.get("type") != "file":
        raise FileNotFoundError(f"Not a file: {path}")
    size = data.get("size") or 0
    if size > MAX_FILE_SIZE:
        raise ValueError(f"File too large ({size} bytes). Max: {MAX_FILE_SIZE}")
    content = data.get("content") or ""
    encoding = data.get("encoding")
    if encoding == "base64":
        raw = base64.b64decode(content)
        try:
            text = raw.decode("utf-8")
            return {
                "path": path,
                "name": os.path.basename(repo_path),
                "encoding": "utf-8",
                "content": text,
                "size": size,
                "source": "github",
            }
        except UnicodeDecodeError:
            return {
                "path": path,
                "name": os.path.basename(repo_path),
                "encoding": "base64",
                "content": base64.b64encode(raw).decode("ascii"),
                "size": size,
                "source": "github",
            }
    raise ValueError(f"Unsupported GitHub content encoding: {encoding}")


def _is_safe_pattern(pattern: str) -> bool:
    if not pattern or pattern.startswith("/") or ".." in pattern.split("/"):
        return False
    return True


async def search_files(path: str, pattern: str) -> List[Dict[str, Any]]:
    """Search a mounted GitHub repo using a safe glob pattern."""
    if not _is_safe_pattern(pattern):
        raise PermissionError("Search pattern must be relative and cannot contain '..'")
    _mount_id, mount, rel = _resolve_mount(path)
    base_path = "/".join(part for part in [mount.get("path") or "", rel] if part)
    tree = await _tree(mount["owner"], mount["repo"], mount["ref"], recursive=True)
    prefix = base_path + "/" if base_path else ""
    matches = []
    for item in tree:
        if item.get("type") != "blob":
            continue
        item_path = item.get("path") or ""
        if prefix and not item_path.startswith(prefix):
            continue
        rel_path = item_path[len(prefix):] if prefix else item_path
        if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(os.path.basename(rel_path), pattern):
            virtual_rel = "/".join(part for part in [rel, rel_path] if part)
            matches.append({
                "name": os.path.basename(item_path),
                "path": _virtual_child_path(mount, virtual_rel),
                "size": item.get("size"),
                "modified": None,
                "source": "github",
            })
    matches.sort(key=lambda r: r["path"].lower())
    return matches[:MAX_SEARCH_RESULTS]


async def restore_mounts(mounts_data: List[Dict[str, Any]], scope: Optional[str] = None) -> List[Dict[str, Any]]:
    """Restore GitHub repo mounts for a conversation scope."""
    set_active_scope(scope)
    mounts = _get_scope_mounts()
    mounts.clear()
    for mount in mounts_data:
        if not isinstance(mount, dict):
            continue
        try:
            owner, repo_name = _parse_repo(f"{mount.get('owner')}/{mount.get('repo')}")
            clean_path = _normalize_path(mount.get("path"))
            ref = str(mount.get("ref") or "main").strip()
            if not ref:
                continue
            mount_id = str(mount.get("mount_id") or uuid.uuid4())[:8]
            mount_data = {
                "type": "github",
                "owner": owner,
                "repo": repo_name,
                "ref": ref,
                "path": clean_path,
                "name": f"{owner}/{repo_name}",
                "display_name": f"{owner}/{repo_name}@{ref}" + (f"/{clean_path}" if clean_path else ""),
                "mounted_at": mount.get("mounted_at") or datetime.utcnow().isoformat(),
                "read_only": True,
            }
            mounts[mount_id] = mount_data
        except Exception:
            continue
    return list_mounts()


async def build_context_summary(mounts_data: List[Dict[str, Any]], max_entries: int = 40) -> str:
    """Build bounded prompt context for GitHub repository mounts."""
    if not mounts_data:
        return ""
    lines = ["\n\n--- Mounted GitHub Repository Context ---"]
    for mount in mounts_data:
        try:
            owner, repo_name = _parse_repo(f"{mount.get('owner')}/{mount.get('repo')}")
            mounted = {
                "owner": owner,
                "repo": repo_name,
                "ref": str(mount.get("ref") or "main"),
                "path": _normalize_path(mount.get("path")),
                "display_name": mount.get("display_name") or f"{owner}/{repo_name}@{mount.get('ref') or 'main'}",
            }
            entries = await _directory_entries_for_mount(mounted)
            lines.append(f"\nRepository: {mounted['display_name']} (read-only)")
            for entry in entries[:max_entries]:
                prefix = "[DIR] " if entry["type"] == "directory" else "      "
                size_str = f" ({entry['size']} bytes)" if entry.get("size") else ""
                lines.append(f"  {prefix}{entry['name']}{size_str}")
            if len(entries) > max_entries:
                lines.append(f"  ... and {len(entries) - max_entries} more entries")
        except Exception as exc:
            lines.append(f"\nRepository: {mount.get('owner')}/{mount.get('repo')} (unable to read: {exc})")
    lines.append("--- End GitHub Repository Context ---\n")
    return "\n".join(lines)
