"""GitHub Copilot SDK provider adapter."""

import asyncio
import uuid
from typing import Any, Dict, List, Optional

from .github_account import get_github_token

COPILOT_MODEL_PREFIX = "copilot/"
DEFAULT_COPILOT_MODELS = [
    {
        "id": "copilot/gpt-5",
        "name": "GitHub Copilot GPT-5",
        "description": "GitHub Copilot SDK model routed through the user's Copilot subscription.",
        "context_length": 0,
        "pricing": {"prompt": "0", "completion": "0"},
        "provider": "copilot",
    },
    {
        "id": "copilot/claude-sonnet-4.5",
        "name": "GitHub Copilot Claude Sonnet 4.5",
        "description": "GitHub Copilot SDK model routed through the user's Copilot subscription.",
        "context_length": 0,
        "pricing": {"prompt": "0", "completion": "0"},
        "provider": "copilot",
    },
    {
        "id": "copilot/gemini-2.5-pro",
        "name": "GitHub Copilot Gemini 2.5 Pro",
        "description": "GitHub Copilot SDK model routed through the user's Copilot subscription.",
        "context_length": 0,
        "pricing": {"prompt": "0", "completion": "0"},
        "provider": "copilot",
    },
]


def is_copilot_model(model: str) -> bool:
    """Return whether a model ID is routed through GitHub Copilot."""
    return model.startswith(COPILOT_MODEL_PREFIX)


def strip_prefix(model: str) -> str:
    """Return the Copilot SDK model name for a public council model ID."""
    return model[len(COPILOT_MODEL_PREFIX):] if is_copilot_model(model) else model


def copilot_is_configured() -> bool:
    """Return whether a GitHub token source is configured for Copilot SDK auth."""
    token, _source = get_github_token()
    return bool(token)


def list_static_models() -> List[Dict[str, Any]]:
    """Return the conservative static Copilot model list."""
    return [dict(model) for model in DEFAULT_COPILOT_MODELS]


def _message_to_text(messages: List[Dict[str, Any]]) -> str:
    """Flatten OpenAI-style messages to a single Copilot SDK prompt."""
    parts = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text_parts = []
            for item in content:
                if item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
                elif item.get("type") == "image_url":
                    text_parts.append("[Image attachment omitted for Copilot provider]")
                elif item.get("type") == "file":
                    text_parts.append("[File attachment omitted for Copilot provider]")
            text = "\n".join(part for part in text_parts if part)
        else:
            text = str(content)
        parts.append(f"{role.upper()}:\n{text}")
    return "\n\n".join(parts)


def _deny_tool_permission(request, invocation):
    """Deny Copilot SDK tool execution; LLM Council owns tool/file access."""
    return {"kind": "denied-by-rules", "rules": []}


async def query_model(
    model: str,
    messages: List[Dict[str, Any]],
    timeout: float = 120.0,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Query a single GitHub Copilot model through the Copilot Python SDK."""
    if tools:
        print("Copilot provider does not support LLM Council tool injection; tools were ignored")

    token, _source = get_github_token()
    if not token:
        print("GitHub Copilot provider is not configured")
        return None

    try:
        from copilot import CopilotClient
    except Exception as exc:
        print(f"GitHub Copilot SDK is not installed or importable: {exc}")
        return None

    prompt = _message_to_text(messages)
    config = {
        "github_token": token,
        "use_logged_in_user": False,
        "env": {"COPILOT_GITHUB_TOKEN": token},
        "log_level": "error",
    }
    sdk_model = strip_prefix(model)

    client = CopilotClient(config)
    session = None
    try:
        await client.start()
        session = await client.create_session({
            "on_permission_request": _deny_tool_permission,
            "model": sdk_model,
            "session_id": f"llm-council-{uuid.uuid4()}",
            "available_tools": [],
            "excluded_tools": ["*"],
            "infinite_sessions": {"enabled": False},
        })
        event = await session.send_and_wait({"prompt": prompt}, timeout=timeout)
        content = getattr(getattr(event, "data", None), "content", "") if event else ""
        return {"content": content or "", "reasoning_details": None, "tool_calls": None}
    except asyncio.TimeoutError:
        print(f"Timed out querying Copilot model {model}")
        return None
    except Exception as exc:
        print(f"Error querying Copilot model {model}: {exc}")
        return None
    finally:
        if session is not None:
            try:
                await session.destroy()
            except Exception:
                pass
        try:
            await client.stop()
        except Exception:
            pass
