# AGENTS.md — LLM Council

This file is the single source of truth for AI coding agents working on the LLM Council project. The reader is assumed to know nothing about the codebase.

---

## Project Overview

LLM Council is a local web application that queries multiple LLMs simultaneously via the OpenRouter API, orchestrates anonymized peer review among them, and synthesizes a final answer through a designated "Chairman" model. It can also run as an MCP (Model Context Protocol) server for integration with Claude Code or other MCP clients.

The core user flow has three stages:

1. **Stage 1 — First Opinions**: The user's query is sent in parallel to all council models. Individual responses are shown in a tab view.
2. **Stage 2 — Review**: Each model evaluates and ranks the anonymized responses of the other models. Labels like "Response A", "Response B" prevent bias.
3. **Stage 3 — Final Response**: The Chairman model synthesizes all responses and rankings into a single final answer.

The project was built as a quick hack ("vibe coded"). It is functional and useful, but minimal. There are no tests, no CI, and no deployment pipeline. Changes should be simple and pragmatic.

---

## Technology Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.10+, FastAPI, async `httpx`, Pydantic |
| **Frontend** | React 19, Vite 7, react-markdown 10 |
| **LLM Gateway** | OpenRouter API (`openrouter.ai`) |
| **MCP** | FastMCP (`mcp>=1.24.0`) |
| **Storage** | JSON files on disk (`data/conversations/`, `data/presets/`, `data/config.json`) |
| **PDF Export** | reportlab |
| **Package Managers** | `uv` (Python), `npm` (JavaScript) |

---

## Project Structure

```
llm-dev-council/
├── backend/                    # Python backend package
│   ├── __init__.py
│   ├── main.py                 # FastAPI app, REST endpoints, export logic
│   ├── council.py              # 3-stage orchestration (core logic)
│   ├── openrouter.py           # OpenRouter API client (single + parallel queries)
│   ├── config.py               # Config loading, env vars, defaults
│   ├── storage.py              # JSON conversation persistence
│   ├── presets.py              # JSON preset persistence
│   ├── filesystem.py           # Sandboxed filesystem access for mounted dirs
│   └── mcp.py                  # FastMCP tool definition (consult_council)
├── frontend/                   # React + Vite frontend
│   ├── src/
│   │   ├── main.jsx            # Entry point
│   │   ├── App.jsx             # Top-level state (conversations, mounts, writes)
│   │   ├── api.js              # Fetch wrapper for all backend endpoints
│   │   ├── index.css           # Global styles, .markdown-content class
│   │   └── components/         # React components (ChatInterface, Stage1/2/3, Sidebar, etc.)
│   ├── package.json
│   └── vite.config.js
├── scripts/
│   └── council_cli.py          # CLI client (requires running backend)
├── docs/
│   ├── architecture-mcp.md     # MCP server docs
│   ├── research-a2a-protocol.md
│   └── research-mini-agent-architecture.md
├── data/
│   ├── conversations/          # One JSON file per conversation
│   ├── presets/                # Saved model presets
│   └── config.json             # Global council config
├── mcp_server.py               # MCP server entry point (parses CLI args)
├── start.sh                    # One-shot launcher (backend + frontend)
├── pyproject.toml              # Python project metadata & deps
├── uv.lock                     # uv lockfile
├── .env.template               # Copy to .env.local and add OPENROUTER_API_KEY
└── CLAUDE.md                   # Deep technical notes (read before non-trivial changes)
```

### Key Files for Agents

- **`backend/council.py`** — The heart of the system. Contains `stage1_collect_responses`, `stage2_collect_rankings`, `stage3_synthesize_final`, `run_full_council`, ranking parsing, and aggregate ranking calculation.
- **`backend/openrouter.py`** — All LLM calls go through here. `query_model()` for single queries, `query_models_parallel()` for parallel Stage 1 queries.
- **`backend/config.py`** — Config priority chain: env vars (`COUNCIL_MODELS`, `CHAIRMAN_MODEL`) > `data/config.json` > hardcoded defaults. Also loads `OPENROUTER_API_KEY` from `.env.local`.
- **`backend/main.py`** — FastAPI routes. CORS is enabled for `http://localhost:5173` and `http://localhost:3000`. Backend port is **8001**.
- **`frontend/src/api.js`** — All HTTP calls to the backend. Base URL is `http://localhost:8001`.

---

## Build and Run Commands

### Install Dependencies

```bash
# Python backend
uv sync

# JavaScript frontend
cd frontend && npm install && cd ..
```

### Configure API Key

```bash
cp .env.template .env.local
# Edit .env.local and set OPENROUTER_API_KEY
```

### Run the Application

```bash
# Option 1: Start both backend and frontend with one script
./start.sh

# Option 2: Run manually in separate terminals
# Terminal 1 (backend)
uv run python -m backend.main

# Terminal 2 (frontend)
cd frontend && npm run dev
```

- Backend URL: `http://localhost:8001`
- Frontend URL: `http://localhost:5173`

> **Critical**: Always run the backend as `python -m backend.main` from the project root. Do **not** run it from inside the `backend/` directory or module imports will break.

### Build Frontend for Production

```bash
cd frontend && npm run build
```

### Lint Frontend

```bash
cd frontend && npm run lint
```

---

## MCP Server Mode

The council can run as a standalone MCP server (no FastAPI, no conversation storage).

```bash
# Local development
claude mcp add llm-council \
  -e OPENROUTER_API_KEY="your-key" \
  -- uv run python mcp_server.py \
  --council-models "openai/gpt-5.1,google/gemini-3-pro-preview" \
  --chairman-model "google/gemini-3-pro-preview"
```

- Entry point: `mcp_server.py`
- Tool name: `consult_council(query, files?)`
- `mcp_server.py` parses `--council-models` and `--chairman-model`, injects them as env vars, then calls `mcp.run()` from `backend/mcp.py`.

---

## Code Style Guidelines

### Python

- **Relative imports only** inside the `backend/` package. Use `from .config import ...`, never `from backend.config import ...`. This is required because the module is executed as `python -m backend.main`.
- Use type hints (`typing.List`, `typing.Dict`, `typing.Optional`).
- Async/await throughout the backend for I/O-bound work.
- Docstrings for all public functions.
- Keep functions focused. `council.py` is already ~500 lines; prefer extracting helpers over adding inline complexity.

### JavaScript / React

- Functional components with hooks.
- CSS files are co-located with components (`ComponentName.css`).
- Global styles live in `index.css`.
- All `ReactMarkdown` output must be wrapped in `<div className="markdown-content">` for correct spacing.
- Light mode only. Primary color is `#4a90e2`.

---

## Testing Instructions

**There are currently no automated tests in this repository.**

When adding tests, prefer `pytest`. Place tests in a `tests/` directory at the project root. If you add tests, update this section.

For manual verification:

1. Start the backend and frontend.
2. Create a conversation and send a message.
3. Verify Stage 1 tabs render, Stage 2 rankings parse correctly, and Stage 3 shows the Chairman's verdict.
4. Test file attachments (images and text files) via the web UI.
5. Test mount/unmount via the folder manager.
6. Test export to Markdown, JSON, and PDF.

---

## Security Considerations

- **OpenRouter API key** lives in `.env.local`. This file is gitignored. Never commit it.
- **Filesystem sandboxing**: `backend/filesystem.py` only allows access to explicitly mounted directories. All paths are resolved with `os.path.realpath()` and validated against the mount list.
- **File write restrictions**: The `/api/fs/write` endpoint is intended for Chairman-proposed changes only and requires user approval in the UI.
- **Preset IDs**: `backend/presets.py` validates preset IDs with `replace("-", "").replace("_", "").isalnum()` to prevent path traversal.
- **CORS**: The FastAPI CORS middleware is locked to `localhost:5173` and `localhost:3000`.
- **No authentication**: The app is designed for local, single-user use. Do not expose the backend to the public internet without adding authentication.

---

## Important Conventions and Gotchas

1. **Port 8001, not 8000** — The backend intentionally uses port 8001 to avoid conflicts. If you change it, update `backend/main.py` and `frontend/src/api.js`.

2. **Config Priority Chain** — `get_council_models()` and `get_chairman_model()` read in this order:
   - `COUNCIL_MODELS` / `CHAIRMAN_MODEL` env vars (set by MCP CLI args)
   - `data/config.json` (set via web UI)
   - Hardcoded defaults in `backend/config.py`

3. **Metadata is Ephemeral** — `label_to_model` and `aggregate_rankings` are returned by the API but **not persisted** to `data/conversations/`. The frontend stores them in React state for display.

4. **De-anonymization Happens in the Frontend** — Models only see "Response A", "Response B". The backend creates the `label_to_model` mapping. The frontend swaps labels for real model names in **bold** when displaying Stage 2 evaluations.

5. **Graceful Degradation** — If one model fails in Stage 1 or 2, the process continues with the successful responses. Only if **all** models fail does the user see an error.

6. **Attachment Storage** — `storage.py` strips base64 data from attachments before saving conversations. Only lightweight metadata (`filename`, `mimeType`, `type`) is persisted.

7. **Atomic File Writes** — Both `storage.py` and `config.py` use temp-file + `fsync` + `os.replace()` for atomic writes. `storage.py` also uses `fcntl` file locking.

8. **No Dark Mode** — The UI is light mode only. Do not add dark mode CSS unless explicitly requested.

9. **Markdown Rendering** — Always wrap `ReactMarkdown` in `<div className="markdown-content">`. The `.markdown-content` class in `index.css` provides `12px` padding and typography defaults.

10. **Ranking Parse Fallback** — If a model ignores the "FINAL RANKING:" format instructions, `parse_ranking_from_text()` falls back to extracting any "Response X" patterns in order of appearance.

---

## Documentation References

- **`CLAUDE.md`** — Deep technical notes, architecture decisions, data flow diagrams, and common gotchas. Read this before making any non-trivial change.
- **`IMPLEMENTATION_PLAN.md`** — A 6-phase roadmap for adding a capability substrate (agent tool-use loop, skills system, A2A server, MCP-to-A2A bridge). Most of this is **not yet implemented**. Do not assume any Phase 1–6 code exists unless you see it in `backend/capabilities/`.
- **`docs/architecture-mcp.md`** — Detailed MCP server usage and configuration.
- **`README.md`** — Human-facing setup and usage guide.

---

## When in Doubt

- Keep changes minimal and pragmatic.
- Do not over-engineer. The project is intentionally simple.
- Prefer extending existing functions with optional parameters over rewriting orchestration logic.
- If a change touches `council.py` or `openrouter.py`, test both the web app and MCP paths.
