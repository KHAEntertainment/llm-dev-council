"""Model provider router for OpenRouter and additive providers."""

import asyncio
from typing import Any, Dict, List, Optional

from . import copilot_provider
from . import openrouter


async def query_model(
    model: str,
    messages: List[Dict[str, Any]],
    timeout: float = 120.0,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Route a model query to the correct provider."""
    if copilot_provider.is_copilot_model(model):
        return await copilot_provider.query_model(model, messages, timeout=timeout, tools=tools)
    return await openrouter.query_model(model, messages, timeout=timeout, tools=tools)


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """Query models across providers in parallel with graceful degradation."""
    tasks = [query_model(model, messages, tools=tools) for model in models]
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    return {
        model: None if isinstance(response, Exception) else response
        for model, response in zip(models, responses)
    }


def list_copilot_models_if_configured() -> List[Dict[str, Any]]:
    """Return Copilot models only when credentials are configured."""
    if not copilot_provider.copilot_is_configured():
        return []
    return copilot_provider.list_static_models()
