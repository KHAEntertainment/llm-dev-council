"""Filesystem access with security sandboxing for mounted directories."""

import os
import glob
import base64
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# In-memory mount registry (keyed by mount ID)
_mounts: Dict[str, Dict[str, Any]] = {}

# Max file size for reading (10MB)
MAX_READ_SIZE = 10 * 1024 * 1024

# Text file extensions
TEXT_EXTENSIONS = {
    '.txt', '.md', '.py', '.js', '.jsx', '.ts', '.tsx', '.json', '.yaml',
    '.yml', '.toml', '.cfg', '.ini', '.html', '.css', '.scss', '.xml',
    '.csv', '.sh', '.bash', '.zsh', '.env', '.gitignore', '.dockerfile',
    '.sql', '.r', '.rb', '.go', '.rs', '.java', '.c', '.cpp', '.h',
    '.hpp', '.swift', '.kt', '.scala', '.lua', '.pl', '.php', '.vue',
    '.svelte', '.astro', '.mdx', '.rst', '.tex', '.log', '.conf',
}


def _is_text_file(filepath: str) -> bool:
    ext = Path(filepath).suffix.lower()
    return ext in TEXT_EXTENSIONS


def _resolve_and_validate(path: str, mounted_paths: List[str]) -> str:
    """Resolve a path and validate it falls within a mounted directory."""
    resolved = os.path.realpath(os.path.expanduser(path))
    for mount_path in mounted_paths:
        mount_resolved = os.path.realpath(os.path.expanduser(mount_path))
        if resolved == mount_resolved or resolved.startswith(mount_resolved + os.sep):
            return resolved
    raise PermissionError(f"Path '{path}' is not within any mounted directory")


def get_mounted_paths() -> List[str]:
    """Return list of all currently mounted absolute paths."""
    return [m["path"] for m in _mounts.values()]


def mount_folder(path: str) -> Dict[str, Any]:
    """Mount a folder path. Validates the path exists and is a directory."""
    resolved = os.path.realpath(os.path.expanduser(path))
    if not os.path.exists(resolved):
        raise FileNotFoundError(f"Path does not exist: {path}")
    if not os.path.isdir(resolved):
        raise NotADirectoryError(f"Path is not a directory: {path}")

    # Check if already mounted
    for mid, mount in _mounts.items():
        if mount["path"] == resolved:
            return {"mount_id": mid, **mount}

    mount_id = str(uuid.uuid4())[:8]
    mount_data = {
        "path": resolved,
        "name": os.path.basename(resolved),
        "mounted_at": datetime.utcnow().isoformat(),
    }
    _mounts[mount_id] = mount_data
    return {"mount_id": mount_id, **mount_data}


def unmount_folder(mount_id: str) -> bool:
    """Unmount a folder by its mount ID."""
    if mount_id in _mounts:
        del _mounts[mount_id]
        return True
    return False


def list_mounts() -> List[Dict[str, Any]]:
    """List all current mounts."""
    return [{"mount_id": mid, **data} for mid, data in _mounts.items()]


def list_directory(path: str) -> List[Dict[str, Any]]:
    """List contents of a directory within mounted paths."""
    resolved = _resolve_and_validate(path, get_mounted_paths())

    entries = []
    try:
        for entry in os.scandir(resolved):
            stat = entry.stat(follow_symlinks=False)
            entries.append({
                "name": entry.name,
                "path": entry.path,
                "type": "directory" if entry.is_dir() else "file",
                "size": stat.st_size if entry.is_file() else None,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
    except PermissionError:
        raise PermissionError(f"Cannot read directory: {path}")

    entries.sort(key=lambda e: (e["type"] != "directory", e["name"].lower()))
    return entries


def read_file(path: str) -> Dict[str, Any]:
    """Read a file from within mounted paths. Returns text or base64."""
    resolved = _resolve_and_validate(path, get_mounted_paths())

    if not os.path.isfile(resolved):
        raise FileNotFoundError(f"Not a file: {path}")

    size = os.path.getsize(resolved)
    if size > MAX_READ_SIZE:
        raise ValueError(f"File too large ({size} bytes). Max: {MAX_READ_SIZE}")

    if _is_text_file(resolved):
        try:
            with open(resolved, 'r', encoding='utf-8') as f:
                content = f.read()
            return {
                "path": resolved,
                "name": os.path.basename(resolved),
                "encoding": "utf-8",
                "content": content,
                "size": size,
            }
        except UnicodeDecodeError:
            pass

    # Binary / fallback: return base64
    with open(resolved, 'rb') as f:
        data = base64.b64encode(f.read()).decode('ascii')
    return {
        "path": resolved,
        "name": os.path.basename(resolved),
        "encoding": "base64",
        "content": data,
        "size": size,
    }


def search_files(path: str, pattern: str) -> List[Dict[str, Any]]:
    """Search for files matching a glob pattern within a mounted path."""
    resolved = _resolve_and_validate(path, get_mounted_paths())

    results = []
    for match in glob.glob(os.path.join(resolved, '**', pattern), recursive=True):
        if os.path.isfile(match):
            stat = os.stat(match)
            results.append({
                "name": os.path.basename(match),
                "path": match,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })

    results.sort(key=lambda r: r["name"].lower())
    return results[:200]  # Cap results


def write_file(path: str, content: str) -> Dict[str, Any]:
    """Write content to a file within mounted paths. Chairman-only operation."""
    resolved = _resolve_and_validate(path, get_mounted_paths())

    # Ensure parent directory exists
    parent = os.path.dirname(resolved)
    os.makedirs(parent, exist_ok=True)

    with open(resolved, 'w', encoding='utf-8') as f:
        f.write(content)

    return {
        "path": resolved,
        "name": os.path.basename(resolved),
        "size": os.path.getsize(resolved),
        "written_at": datetime.utcnow().isoformat(),
    }


def restore_mounts(paths: List[str]) -> List[Dict[str, Any]]:
    """Restore mounts from a list of paths (e.g., from conversation metadata).
    Clears stale mounts not in the incoming paths, then re-adds. Skips paths that no longer exist."""
    global _mounts

    # Compute set of resolved paths we want to keep
    desired_resolved = set()
    for p in paths:
        try:
            resolved = os.path.realpath(os.path.expanduser(p))
            desired_resolved.add(resolved)
        except Exception:
            continue

    # Remove mounts not in the desired set
    stale_ids = [
        mid for mid, mount in _mounts.items()
        if mount["path"] not in desired_resolved
    ]
    for mid in stale_ids:
        del _mounts[mid]

    # Re-add mounts for each path
    restored = []
    for p in paths:
        try:
            result = mount_folder(p)
            restored.append(result)
        except (FileNotFoundError, NotADirectoryError):
            continue
    return restored
