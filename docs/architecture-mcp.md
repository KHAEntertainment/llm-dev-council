# MCP Server Architecture

This document covers the MCP (Model Context Protocol) integration for LLM Council, which allows Claude Code or any MCP client to invoke the council as a native tool.

## Overview

The MCP server runs the council's 3-stage deliberation process in **stateless mode** -- no conversation storage, no FastAPI server required. It's a standalone stdio-based MCP server that can be added to Claude Code with a single command.

## Architecture

```
Claude Code / MCP Client
       │
       ▼
  mcp_server.py          ← Entry point (parses CLI args, sets env vars)
       │
       ▼
  backend/mcp.py         ← FastMCP tool definition (consult_council)
       │
       ▼
  backend/council.py     ← run_full_council() (shared with web app)
       │
       ▼
  backend/openrouter.py  ← OpenRouter API client
       │
       ▼
  backend/config.py      ← Config with env-var override chain
```

## Three Usage Modes

### Mode 1: MCP Server (Recommended for Claude Code)

Runs the council logic directly in the MCP process. No separate backend needed.

```bash
# Set your OpenRouter key (get one at openrouter.ai)
claude mcp add llm-council \
  -e OPENROUTER_API_KEY="$(cat .env.local | grep OPENROUTER | cut -d= -f2)" \
  -- uvx --from git+https://github.com/YOUR-ORG/llm-dev-council.git \
  llm-council \
  --council-models "openai/gpt-5.1,google/gemini-3-pro-preview,anthropic/claude-sonnet-4.5,x-ai/grok-4" \
  --chairman-model "google/gemini-3-pro-preview"
```

For local development (from source):
```bash
claude mcp add llm-council \
  -e OPENROUTER_API_KEY="$(cat .env.local | grep OPENROUTER | cut -d= -f2)" \
  -- uv run python mcp_server.py \
  --council-models "openai/gpt-5.1,google/gemini-3-pro-preview" \
  --chairman-model "google/gemini-3-pro-preview"
```

### Mode 2: CLI Script (Requires Running Backend)

The `scripts/council_cli.py` script sends requests to the running FastAPI backend and streams results to the terminal.

```bash
# Start backend first
uv run python -m backend.main

# In another terminal
python3 scripts/council_cli.py "Why is this code failing?" --files src/main.py
```

### Mode 3: Slash Command (Claude Code with Running Backend)

The `.claude/commands/ask-council.md` slash command integrates with Claude Code's command system. It requires a running backend.

```
/ask-council Why is this code failing?
```

## MCP Tool Reference

### `consult_council`

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | The question or problem description |
| `files` | list[string] | No | List of file contents (strings) to provide as context |

**Returns:** A structured Markdown string containing:

1. **Stage 1: Individual Responses** -- Each council model's response
2. **Stage 2: Peer Rankings** -- Compact ranking view with aggregate scores
3. **CHAIRMAN'S VERDICT** -- The final synthesized answer

**File handling:** The `files` parameter accepts raw text strings. The MCP tool automatically base64-encodes them and wraps them in the attachment format expected by `run_full_council()`. Each file is labeled "Context File 1", "Context File 2", etc.

## Configuration Priority Chain

Model configuration follows this priority (highest wins):

1. **CLI args** (`--council-models`, `--chairman-model`) → set as env vars
2. **Environment variables** (`COUNCIL_MODELS`, `CHAIRMAN_MODEL`)
3. **File config** (`data/config.json` -- set via web UI)
4. **Defaults** (`DEFAULT_COUNCIL_MODELS`, `DEFAULT_CHAIRMAN_MODEL` in `config.py`)

This means MCP CLI args override everything, which is the correct behavior for stateless MCP mode.

## Key Differences from Web App Mode

| Aspect | Web App | MCP Server |
|--------|---------|------------|
| Entry point | `backend/main.py` (FastAPI) | `mcp_server.py` (FastMCP) |
| Transport | HTTP (port 8001) | stdio |
| State | Multi-turn conversations | Single-turn stateless |
| Storage | `data/conversations/` | None |
| Model config | Per-conversation overrides | CLI args / env vars |
| Attachments | Not yet in web UI | Supported via `files` param |
| Streaming | SSE events | Single response |

## Adding New MCP Tools

To add a new MCP tool, edit `backend/mcp.py` and add a new decorated function:

```python
@mcp.tool()
async def my_new_tool(param: str) -> str:
    """Description of what the tool does."""
    # Implementation
    return "result"
```

The `mcp` FastMCP instance is defined at the top of `backend/mcp.py`. All tools registered on it will be automatically available when the MCP server runs.
