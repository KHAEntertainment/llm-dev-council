# LLM Council

![llmcouncil](header.jpg)

The idea of this repo is that instead of asking a question to your favorite LLM provider (e.g. OpenAI GPT 5.1, Google Gemini 3.0 Pro, Anthropic Claude Sonnet 4.5, xAI Grok 4, eg.c), you can group them into your "LLM Council". This repo is a simple, local web app that essentially looks like ChatGPT except it uses OpenRouter to send your query to multiple LLMs, it then asks them to review and rank each other's work, and finally a Chairman LLM produces the final response.

In a bit more detail, here is what happens when you submit a query:

1. **Stage 1: First opinions**. The user query is given to all LLMs individually, and the responses are collected. The individual responses are shown in a "tab view", so that the user can inspect them all one by one.
2. **Stage 2: Review**. Each individual LLM is given the responses of the other LLMs. Under the hood, the LLM identities are anonymized so that the LLM can't play favorites when judging their outputs. The LLM is asked to rank them in accuracy and insight.
3. **Stage 3: Final response**. The designated Chairman of the LLM Council takes all of the model's responses and compiles them into a single final answer that is presented to the user.

## Vibe Code Alert

This project was 99% vibe coded as a fun Saturday hack because I wanted to explore and evaluate a number of LLMs side by side in the process of [reading books together with LLMs](https://x.com/karpathy/status/1990577951671509438). It's nice and useful to see multiple responses side by side, and also the cross-opinions of all LLMs on each other's outputs. I'm not going to support it in any way, it's provided here as is for other people's inspiration and I don't intend to improve it. Code is ephemeral now and libraries are over, ask your LLM to change it in whatever way you like.

## Setup

### 1. Install Dependencies

The project uses [uv](https://docs.astral.sh/uv/) for project management.

**Backend:**
```bash
uv sync
```

**Frontend:**
```bash
cd frontend
npm install
cd ..
```

### 2. Configure API Key

Copy the template and add your key:

```bash
cp .env.template .env.local
# Edit .env.local and add your OpenRouter API key
```

Get your API key at [openrouter.ai](https://openrouter.ai/). Make sure to purchase the credits you need, or sign up for automatic top up.

### 3. Configure Models (Optional)

Edit `backend/config.py` to customize the council:

```python
COUNCIL_MODELS = [
    "openai/gpt-5.1",
    "google/gemini-3-pro-preview",
    "anthropic/claude-sonnet-4.5",
    "x-ai/grok-4",
]

CHAIRMAN_MODEL = "google/gemini-3-pro-preview"
```

## Running the Application

**Option 1: Use the start script**
```bash
./start.sh
```

**Option 2: Run manually**

Terminal 1 (Backend):
```bash
uv run python -m backend.main
```

Terminal 2 (Frontend):
```bash
cd frontend
npm run dev
```

Then open http://localhost:5173 in your browser.

## MCP Server (Claude Code Integration)

The LLM Council can also be used as an MCP server, allowing Claude Code (or any MCP client) to invoke the council as a native tool. This runs the logic in stateless mode -- no running backend required.

### Quick Install

Add the council as an MCP server to Claude Code:

```bash
# Set your OpenRouter key (get one at openrouter.ai)
claude mcp add llm-council \
  -e OPENROUTER_API_KEY="$(cat .env.local | grep OPENROUTER | cut -d= -f2)" \
  -- uvx --from git+https://github.com/YOUR-ORG/llm-dev-council.git \
  llm-council \
  --council-models "openai/gpt-5.1,google/gemini-3-pro-preview,anthropic/claude-sonnet-4.5,x-ai/grok-4" \
  --chairman-model "google/gemini-3-pro-preview"
```

Or for local development (runs from source):

```bash
claude mcp add llm-council \
  -e OPENROUTER_API_KEY="$(cat .env.local | grep OPENROUTER | cut -d= -f2)" \
  -- uv run python mcp_server.py \
  --council-models "openai/gpt-5.1,google/gemini-3-pro-preview" \
  --chairman-model "google/gemini-3-pro-preview"
```

### MCP Tool: `consult_council`

The server exposes a single tool:

- **`consult_council(query, files?)`** -- Runs the 3-stage council process and returns a structured Markdown response with all stages and the Chairman's Verdict.

The `files` parameter accepts a list of file contents (strings) to provide as context. The MCP tool handles base64 encoding automatically.

### CLI Integration

For use with Claude Code slash commands or standalone CLI:

```bash
python3 scripts/council_cli.py "Why is this code failing?" --files src/main.py src/utils.py
```

This requires the web app backend to be running locally (Mode 1). See `docs/architecture-mcp.md` for details.

## Usage Modes

| Mode | Description | Requires |
|------|-------------|----------|
| **Web App** | Full browser UI with conversation history | `./start.sh` |
| **MCP Server** | Native tool in Claude Code or any MCP client | `claude mcp add` |
| **CLI / Slash Command** | Command-line interface or Claude Code slash command | Running backend |

## Tech Stack

- **Backend:** FastAPI (Python 3.10+), async httpx, OpenRouter API
- **Frontend:** React + Vite, react-markdown for rendering
- **MCP:** Model Context Protocol (FastMCP)
- **Storage:** JSON files in `data/conversations/`
- **Package Management:** uv for Python, npm for JavaScript
