"""MCP client connector for external MCP servers."""

import os
from contextlib import AsyncExitStack
from typing import Dict, Any, List, Optional, Tuple

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
import httpx

from . import mcp_servers_storage


@staticmethod
async def _connect_single_server(server: Dict[str, Any], exit_stack: AsyncExitStack) -> Optional[ClientSession]:
    """Connect to a single MCP server and add it to the exit stack."""
    transport = server.get("transport", "stdio")

    try:
        if transport == "stdio":
            server_params = StdioServerParameters(
                command=server.get("command", ""),
                args=server.get("args") or [],
                env={**os.environ, **(server.get("env") or {})},
            )
            read, write = await exit_stack.enter_async_context(stdio_client(server_params))
        elif transport == "streamable_http":
            url = server.get("url", "")
            headers = dict(server.get("headers") or {})
            auth_token = server.get("auth_token")
            if auth_token:
                headers["Authorization"] = f"Bearer {auth_token}"
            client = httpx.AsyncClient(headers=headers or None, timeout=30.0)
            await exit_stack.enter_async_context(client)
            read, write, _ = await exit_stack.enter_async_context(
                streamable_http_client(url, http_client=client)
            )
        elif transport == "sse":
            url = server.get("url", "")
            headers = dict(server.get("headers") or {})
            auth_token = server.get("auth_token")
            if auth_token:
                headers["Authorization"] = f"Bearer {auth_token}"
            read, write = await exit_stack.enter_async_context(sse_client(url, headers=headers or None))
        else:
            return None

        session = ClientSession(read, write)
        session = await exit_stack.enter_async_context(session)
        await session.initialize()
        return session
    except Exception as e:
        print(f"Failed to connect to MCP server {server.get('name')}: {e}")
        return None


async def list_tools(session: ClientSession) -> List[Dict[str, Any]]:
    """List tools from a connected MCP server, returning OpenAI function schema."""
    result = await session.list_tools()
    tools = []
    for tool in result.tools:
        tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema or {"type": "object", "properties": {}},
            },
        })
    return tools


async def call_tool(session: ClientSession, name: str, arguments: Dict[str, Any]) -> str:
    """Execute a tool call and return the result as a string."""
    result = await session.call_tool(name, arguments)

    # Convert ToolResult content to string
    parts = []
    for content in result.content:
        if hasattr(content, "text"):
            parts.append(content.text)
        elif hasattr(content, "data"):
            parts.append(str(content.data))
        else:
            parts.append(str(content))

    return "\n".join(parts) if parts else "(no output)"


async def test_connection(config: Dict[str, Any]) -> Dict[str, Any]:
    """Test connecting to an MCP server and return status + tool count."""
    exit_stack = AsyncExitStack()
    try:
        session = await _connect_single_server(config, exit_stack)
        if session is None:
            return {"connected": False, "tool_count": 0, "error": "Failed to establish connection"}
        tools = await list_tools(session)
        return {"connected": True, "tool_count": len(tools), "error": None}
    except Exception as e:
        return {"connected": False, "tool_count": 0, "error": str(e)}
    finally:
        await exit_stack.aclose()


async def get_server_tools(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Connect, list tools, and disconnect for a single server."""
    exit_stack = AsyncExitStack()
    try:
        session = await _connect_single_server(config, exit_stack)
        if session is None:
            return []
        return await list_tools(session)
    finally:
        await exit_stack.aclose()


# --- Scope-aware tool aggregation for council integration ---

async def get_tools_for_scope(scope: str) -> Tuple[List[Dict[str, Any]], Dict[str, ClientSession], AsyncExitStack]:
    """
    Connect to all enabled MCP servers matching the scope and aggregate their tools.

    Args:
        scope: "council" or "chairman"

    Returns:
        Tuple of (combined_tools_list, tool_to_session_map, exit_stack)
        Caller MUST call `await exit_stack.aclose()` when done.
    """
    servers = mcp_servers_storage.list_servers()
    combined_tools: List[Dict[str, Any]] = []
    tool_to_session: Dict[str, ClientSession] = {}
    exit_stack = AsyncExitStack()

    for server in servers:
        if not server.get("enabled", True):
            continue
        server_scope = server.get("scope", "council")
        # Chairman gets both council and chairman scoped tools
        # Council gets only council scoped tools
        if scope == "council" and server_scope != "council":
            continue
        if scope == "chairman" and server_scope not in ("council", "chairman"):
            continue

        session = await _connect_single_server(server, exit_stack)
        if session is None:
            continue

        try:
            tools = await list_tools(session)
            for tool in tools:
                name = tool["function"]["name"]
                # Deduplicate: prefer first server with this tool name
                if name not in tool_to_session:
                    tool_to_session[name] = session
                    combined_tools.append(tool)
        except Exception as e:
            print(f"Failed to list tools from MCP server {server.get('name')}: {e}")
            continue

    return combined_tools, tool_to_session, exit_stack


async def execute_tool_call(
    tool_name: str,
    arguments: Dict[str, Any],
    tool_to_session: Dict[str, ClientSession]
) -> str:
    """Execute a single tool call against the appropriate MCP server."""
    if tool_name not in tool_to_session:
        return f"Error: Tool '{tool_name}' not found in any connected MCP server"

    session = tool_to_session[tool_name]
    try:
        return await call_tool(session, tool_name, arguments)
    except Exception as e:
        return f"Error executing tool '{tool_name}': {e}"
