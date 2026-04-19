"""JSON-based storage for conversations."""

import json
import os
try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
from .config import DATA_DIR


def _lock_file(lock_file):
    if fcntl is not None:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)


def _unlock_file(lock_file):
    if fcntl is not None:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def ensure_data_dir():
    """Ensure the data directory exists."""
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)


def get_conversation_path(conversation_id: str) -> str:
    """Get the file path for a conversation."""
    return os.path.join(DATA_DIR, f"{conversation_id}.json")


def create_conversation(conversation_id: str, council_models: Optional[list] = None, chairman_model: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a new conversation.

    Args:
        conversation_id: Unique identifier for the conversation
        council_models: Optional list of model IDs for this conversation
        chairman_model: Optional chairman model ID for this conversation

    Returns:
        New conversation dict
    """
    ensure_data_dir()

    conversation = {
        "id": conversation_id,
        "created_at": datetime.utcnow().isoformat(),
        "title": "New Conversation",
        "messages": [],
        "council_models": council_models,
        "chairman_model": chairman_model,
        "mounted_paths": [],
    }

    # Save to file
    path = get_conversation_path(conversation_id)
    with open(path, 'w') as f:
        json.dump(conversation, f, indent=2)

    return conversation


def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    """
    Load a conversation from storage.

    Args:
        conversation_id: Unique identifier for the conversation

    Returns:
        Conversation dict or None if not found
    """
    path = get_conversation_path(conversation_id)

    if not os.path.exists(path):
        return None

    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def save_conversation(conversation: Dict[str, Any]):
    """
    Save a conversation to storage atomically with file locking.

    Args:
        conversation: Conversation dict to save
    """
    ensure_data_dir()

    path = get_conversation_path(conversation['id'])
    lock_path = path + ".lock"

    with open(lock_path, 'w') as lock_file:
        _lock_file(lock_file)
        try:
            tmp_path = path + ".tmp"
            with open(tmp_path, 'w') as f:
                json.dump(conversation, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        finally:
            _unlock_file(lock_file)
    try:
        os.remove(lock_path)
    except OSError:
        pass


def list_conversations(archived: bool = False) -> List[Dict[str, Any]]:
    """
    List conversations (metadata only), filtered by archive status.

    Args:
        archived: If True, return archived conversations. If False, return active ones.

    Returns:
        List of conversation metadata dicts
    """
    ensure_data_dir()

    conversations = []
    for filename in os.listdir(DATA_DIR):
        if filename.endswith('.json'):
            path = os.path.join(DATA_DIR, filename)
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    is_archived = data.get("archived", False)
                    if is_archived != archived:
                        continue
                    conversations.append({
                        "id": data["id"],
                        "created_at": data["created_at"],
                        "title": data.get("title", "New Conversation"),
                        "message_count": len(data["messages"]),
                        "archived": is_archived,
                    })
            except (json.JSONDecodeError, KeyError):
                continue

    # Sort by creation time, newest first
    conversations.sort(key=lambda x: x["created_at"], reverse=True)

    return conversations


def add_user_message(conversation_id: str, content: str, attachments: Optional[List[Dict[str, Any]]] = None):
    """
    Add a user message to a conversation.

    Args:
        conversation_id: Conversation identifier
        content: User message content
        attachments: Optional list of attachment metadata dicts
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    message = {"role": "user", "content": content}
    if attachments:
        # Store lightweight metadata only (no base64 data)
        message["attachments"] = [
            {"filename": a.get("filename"), "mimeType": a.get("mimeType"), "type": a.get("type")}
            for a in attachments
        ]

    conversation["messages"].append(message)
    save_conversation(conversation)


def add_assistant_message(
    conversation_id: str,
    stage1: List[Dict[str, Any]],
    stage2: List[Dict[str, Any]],
    stage3: Dict[str, Any]
):
    """
    Add an assistant message with all 3 stages to a conversation.

    Args:
        conversation_id: Conversation identifier
        stage1: List of individual model responses
        stage2: List of model rankings
        stage3: Final synthesized response
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    conversation["messages"].append({
        "role": "assistant",
        "stage1": stage1,
        "stage2": stage2,
        "stage3": stage3
    })

    save_conversation(conversation)


def update_conversation_title(conversation_id: str, title: str):
    """
    Update the title of a conversation.

    Args:
        conversation_id: Conversation identifier
        title: New title for the conversation
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    conversation["title"] = title
    save_conversation(conversation)


def update_conversation_models(conversation_id: str, council_models: list, chairman_model: str):
    """
    Update the model configuration for a conversation.

    Args:
        conversation_id: Conversation identifier
        council_models: List of model IDs for the council
        chairman_model: Chairman model ID
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    conversation["council_models"] = council_models
    conversation["chairman_model"] = chairman_model
    save_conversation(conversation)


def update_conversation_mounts(conversation_id: str, mounted_paths: list):
    """
    Update the mounted folder paths for a conversation.

    Args:
        conversation_id: Conversation identifier
        mounted_paths: List of absolute folder paths
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    conversation["mounted_paths"] = mounted_paths
    save_conversation(conversation)


def delete_conversation(conversation_id: str) -> bool:
    """
    Delete a conversation file and any associated lock file.

    Args:
        conversation_id: Conversation identifier

    Returns:
        True if deleted, False if not found
    """
    path = get_conversation_path(conversation_id)
    if os.path.exists(path):
        os.remove(path)
        # Clean up lock file if present
        lock_path = path + ".lock"
        try:
            if os.path.exists(lock_path):
                os.remove(lock_path)
        except OSError:
            pass
        return True
    return False


def archive_conversation(conversation_id: str, archived: bool) -> Dict[str, Any]:
    """
    Set the archived status of a conversation.

    Args:
        conversation_id: Conversation identifier
        archived: True to archive, False to unarchive

    Returns:
        Updated conversation dict
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation {conversation_id} not found")

    conversation["archived"] = archived
    save_conversation(conversation)
    return conversation