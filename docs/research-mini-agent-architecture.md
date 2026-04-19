# Mini-Agent Architecture Research Report

> **Source**: [MiniMax-AI/Mini-Agent](https://github.com/MiniMax-AI/Mini-Agent)
> **Research Date**: 2026-04-13
> **Purpose**: Identify architectural patterns borrowable for LLM Council capability substrate

---

## 1. Overall Architecture Overview

Mini-Agent is a minimal, single-agent framework organized around four pillars:

| Pillar | Implementation | Key File(s) |
|--------|---------------|-------------|
| **Brain (LLM)** | Unified `LLMClient` with provider routing | `mini_agent/llm/llm_wrapper.py`, `base.py`, `anthropic_client.py`, `openai_client.py` |
| **Tools** | 3-tier tool system (Basic → MCP → Skills) | `mini_agent/tools/base.py`, `file_tools.py`, `bash_tool.py`, `note_tool.py` |
| **Memory** | Message history + persistent notes file | `mini_agent/agent.py` (messages list), `note_tool.py` (.agent_memory.json) |
| **Loop** | Iterative Perception→Thinking→Action→Feedback | `mini_agent/agent.py` (`Agent.run()`) |

**Entry points**: CLI (`mini_agent/cli.py`) and ACP server (`mini_agent/acp/server.py`).

**Key design philosophy**: Lightweight, no over-abstraction, clear separation of concerns. All tools share a single `Tool` base class interface. The LLM is abstracted behind a provider-agnostic wrapper. Configuration is hierarchical (dev → user → package).

---

## 2. Tool / Capability Registry Design

### 2.1 The `Tool` Base Class (`mini_agent/tools/base.py`)

```python
class Tool:
    @property
    def name(self) -> str: ...         # Unique identifier
    @property
    def description(self) -> str: ...  # LLM-readable description
    @property
    def parameters(self) -> dict: ...  # JSON Schema for inputs

    async def execute(self, **kwargs) -> ToolResult: ...

    def to_schema(self) -> dict:       # Anthropic format
    def to_openai_schema(self) -> dict: # OpenAI function format
```

### 2.2 The `ToolResult` Class (Pydantic BaseModel)

```python
class ToolResult(BaseModel):
    success: bool
    content: str
    error: str | None = None
```

### 2.3 Registration Pattern

Tools are **instantiated and passed as a list** to the `Agent`. There is no formal registry object—the agent holds `self.tools: dict[str, Tool]` as a name→instance mapping. Tool loading happens at startup:

1. **Basic tools** are created directly (file tools, bash, notes)
2. **MCP tools** are loaded dynamically via `load_mcp_tools_async()`
3. **Skill tools** are loaded via `SkillLoader.discover_skills()`

All converge into a single flat `tools` dict. The agent dispatches by tool name from LLM's `tool_calls`.

### 2.4 Schema Generation

Each tool provides dual schema methods (`to_schema()` for Anthropic, `to_openai_schema()` for OpenAI) enabling multi-provider support.

### Key Pattern Worth Borrowing

- **Unified `Tool` base class** with `name`, `description`, `parameters` (JSON Schema), `execute()` → `ToolResult`
- **`ToolResult` as Pydantic model** with `success`, `content`, `error` — clean, serializable
- **Flat dict registry** — simple, no over-engineering
- **Dual schema methods** for multi-provider LLM support

---

## 3. Skills System Design

### 3.1 Contract: `SKILL.md` Files

Each skill is a Markdown file with YAML frontmatter:

```markdown
---
name: skill-name
description: Brief description
license: MIT
allowed-tools:
  - read_file
  - write_file
metadata:
  author: Author Name
  version: "1.0"
---
# Skill instructions in Markdown
```

### 3.2 Data Model: `Skill` Dataclass

```python
@dataclass
class Skill:
    name: str
    description: str
    content: str                     # Full markdown content
    license: Optional[str]
    allowed_tools: Optional[List[str]]  # Tool restrictions
    metadata: Optional[Dict[str, str]]
    skill_path: Optional[Path]
```

### 3.3 Loading: `SkillLoader` Class

- `discover_skills()` — recursively finds all `SKILL.md` via `Path.rglob("SKILL.md")`
- `load_skill(path)` — parses YAML frontmatter with regex, validates required fields, processes paths
- `loaded_skills: Dict[str, Skill]` — keyed by skill name
- `_process_skill_paths()` — converts relative paths in content to absolute paths (3 regex patterns for scripts, doc refs, markdown links)

### 3.4 Progressive Disclosure (Token Optimization)

**Level 1**: `get_skills_metadata_prompt()` injects only names + descriptions into system prompt (~few tokens)

**Level 2**: When agent explicitly requests a skill, `get_skill(name)` → `skill.to_prompt()` returns full content with root directory context

This is a **major pattern worth borrowing** for managing large capability sets without blowing up context.

### 3.5 `allowed-tools` Constraint

Skills can declare which tools they are allowed to use, providing a soft permission boundary.

---

## 4. MCP Integration Approach

### 4.1 Architecture

Mini-Agent acts as an **MCP Host**, connecting to external MCP servers. Implemented in `mini_agent/tools/mcp_loader.py`.

### 4.2 Key Classes

| Class | Purpose |
|-------|---------|
| `MCPTimeoutConfig` | Configurable timeouts (connect, execute, SSE read) |
| `MCPTool(Tool)` | Wraps an individual MCP server tool as a standard `Tool` |
| `MCPServerConnection` | Manages lifecycle of one MCP server connection |
| `load_mcp_tools_async()` | Top-level loader: reads config, connects servers, returns Tool list |
| `cleanup_mcp_connections()` | Tears down all connections |

### 4.3 Connection Types

| Transport | Config Keys | Use Case |
|-----------|-------------|----------|
| **stdio** | `command`, `args` | Local processes |
| **SSE** | `url` | Remote HTTP streaming |
| **streamable_http** | `url` | Bidirectional HTTP |

### 4.4 Connector Pattern

```python
class MCPServerConnection:
    async def connect(self) -> bool:
        # 1. Create async exit stack for cleanup
        # 2. Apply timeout (asyncio.timeout)
        # 3. Establish transport (stdio/SSE/HTTP)
        # 4. Create MCP ClientSession
        # 5. Initialize session (handshake)
        # 6. List tools from server
        # 7. Wrap each as MCPTool instance
```

`MCPTool.execute()` delegates to `session.call_tool(name, arguments)` with timeout protection. Results are converted to standard `ToolResult`.

### 4.5 Configuration (`mcp.json`)

```json
{
  "mcpServers": {
    "memory": {
      "command": "npx",
      "args": ["-y", "@anthropic/memory-server"],
      "env": {}
    }
  }
}
```

### Key Pattern Worth Borrowing

- **Wrapping external tools as `Tool` subclasses** — seamless integration
- **Per-server timeout configuration** — robust error handling
- **Global connection list with cleanup function** — proper lifecycle management
- **Transport auto-detection** from config shape

---

## 5. Session / Workspace State Management

### 5.1 Workspace Directory

- `workspace_dir` is set via config or CLI `--workspace` flag
- Created automatically: `self.workspace_dir.mkdir(parents=True, exist_ok=True)`
- Injected into system prompt so the LLM knows the working directory
- All file tools and BashTool operations are scoped to this directory

### 5.2 Session State (In-Memory)

- `self.messages: list[Message]` — conversation history
- `self.api_total_tokens: int` — running token counter from API responses
- `self._skip_next_token_check: bool` — loop prevention for summarization
- `self.tools: dict[str, Tool]` — loaded tool registry
- `self.llm: LLMClient` — configured LLM client
- `self.logger: AgentLogger` — execution logger

### 5.3 History Access

- `get_history()` returns `self.messages.copy()` (defensive copy)
- `_cleanup_incomplete_messages()` removes partial assistant messages on cancellation

### 5.4 No Cross-Session Persistence of Conversation

Conversation state is **ephemeral** — only the current session's messages are in memory. Cross-session memory is handled by the notes tool (see §6).

---

## 6. Memory / Notes Persistence System

### 6.1 Tools

| Tool | Class | Function |
|------|-------|----------|
| `record_note` | `SessionNoteTool` | Saves a fact/preference to JSON |
| `recall_notes` | `RecallNoteTool` | Retrieves saved notes, optionally filtered |

### 6.2 Storage Format

File: `{workspace_dir}/.agent_memory.json`

```json
[
  {
    "timestamp": "2026-04-13T10:30:00",
    "category": "env",
    "content": "Python 3.12 is installed"
  }
]
```

### 6.3 Design Details

- **Lazy creation** — directory/file created on first `record_note`
- **Category filtering** — `recall_notes(category="env")` returns only matching notes
- **Each note**: `timestamp`, `category`, `content`
- **Persists across sessions** because it's a file, not in-memory

### Key Pattern Worth Borrowing

- **Separate tools for read vs write** (record_note / recall_notes)
- **Category-based filtering** for selective recall
- **JSON file storage** — simple, human-readable, debuggable
- **Workspace-scoped** — notes live alongside the project

---

## 7. Logging Architecture

### 7.1 `AgentLogger` Class (`mini_agent/logger.py`)

- Creates a **timestamped log file per run** in `~/.mini-agent/log/`
- Log file initialized via `start_new_run()`

### 7.2 What Gets Logged

| Event | Method | Data Captured |
|-------|--------|---------------|
| LLM Request | `log_request(messages, tools)` | Message roles, content, thinking blocks, available tool names |
| LLM Response | `log_response()` | Content, thinking, tool calls, finish reason |
| Tool Execution | `log_tool_result(name, args, success, content, error)` | Tool name, arguments, success/error, result content |

### 7.3 Integration Points

- `log_request()` called before each LLM call
- `log_response()` called after each LLM response
- `log_tool_result()` called after each tool execution
- Complete execution tracing from input→LLM→tools→output

### 7.4 CLI Log Management

- `/log` command shows 10 most recent log files
- `/log <file>` reads specific log file
- Can open system file manager for the log directory

### Key Pattern Worth Borrowing

- **Per-run log files** with timestamps — great for debugging specific sessions
- **Structured logging of request/response/tool triples** — full execution tracing
- **Separate from Python logging** — dedicated agent execution logs
- **CLI access to logs** — developer-friendly

---

## 8. File Tools Implementation

### 8.1 ReadTool (`read_file`)
- Adds line numbers (`LINE_NUMBER|LINE_CONTENT`, 1-indexed)
- Supports `offset` and `limit` parameters
- **Token truncation**: `truncate_text_by_tokens()` with 32,000 token limit; keeps head + tail, removes middle

### 8.2 WriteTool (`write_file`)
- Creates parent directories automatically
- Full file overwrite

### 8.3 EditTool (`edit_file`)
- Search-and-replace using `old_str` / `new_str`
- Preferred over `write_file` for large files (minimizes token usage)

### 8.4 BashTool (`bash`)
- Cross-platform: bash on Unix, PowerShell on Windows
- Foreground (blocking with timeout) and background (non-blocking) modes
- `BackgroundShellManager` manages background processes
- `BashOutputTool` retrieves incremental output from background processes
- `BashKillTool` graceful termination (SIGTERM → wait 5s → SIGKILL)

### Key Pattern Worth Borrowing

- **Token truncation on file reads** — prevents context blowup
- **Line numbering in output** — helps LLM reference specific code
- **Background process management** with output buffering

---

## 9. Permission / Policy Model

Mini-Agent has a **minimal permission model** — there's no sandbox or policy engine:

- **Filesystem scoping**: Tools operate within `workspace_dir`
- **Production guide**: Recommends running as non-root `agent` user with `chmod 750` workspace
- **Skill `allowed-tools`**: Soft constraint declaring which tools a skill can use
- **No runtime permission checks**: No ask-before-execute, no tool allowlists enforced at runtime
- **BashTool timeout**: 120s default for foreground execution — only "safety" mechanism

**This is a weakness** — for a system like LLM Council, you'd want stronger sandboxing.

---

## 10. Execution Loop Architecture

### 10.1 The Core Loop (`Agent.run()`)

```python
async def run(self) -> str:
    step = 0
    while step < self.max_steps:
        # 1. Check cancellation
        self._check_cancelled()

        # 2. Context management — summarize if over token_limit
        await self._summarize_messages()

        # 3. Call LLM
        response = await self.llm.generate(
            messages=self.messages,
            tools=tool_schemas
        )

        # 4. Update token tracking
        self.api_total_tokens = response.usage.total_tokens

        # 5. Process thinking blocks (display)
        # 6. Process text content (display)

        # 7. If no tool_calls → task complete, return content
        if not response.tool_calls:
            return response.content

        # 8. Execute each tool call
        for tool_call in response.tool_calls:
            tool = self.tools[tool_call.function.name]
            result = await tool.execute(**arguments)
            # Log result, append to messages

        step += 1
```

### 10.2 Context Summarization (`_summarize_messages()`)

- Uses `tiktoken` (cl100k_base) for token counting
- Dual threshold: local estimate OR API-reported usage > `token_limit` (default: 80,000)
- **Summarization strategy**:
  1. Preserve all user messages (intents)
  2. Group assistant+tool messages between user messages as "execution rounds"
  3. Each round summarized via separate LLM call
  4. Replaced with `[Assistant Execution Summary]` marker
- Skip flag prevents consecutive summarization triggers

### 10.3 Retry Mechanism

- `RetryConfig`: `enabled`, `max_retries`, `initial_delay`, `max_delay`, `exponential_base`
- Wraps `_make_api_request()` with `async_retry` decorator
- Exponential backoff
- `retry_callback` for terminal feedback
- Raises `RetryExhaustedError` after all retries fail

---

## 11. Key Design Patterns Worth Borrowing

### High-Value Patterns

| Pattern | Description | Applicability to LLM Council |
|---------|-------------|------------------------------|
| **`Tool` + `ToolResult` base classes** | Clean, Pydantic-based tool interface with JSON Schema parameters | Foundation for any capability system |
| **Progressive Disclosure for Skills** | Metadata-only in system prompt; full content on demand | Reduce token usage when council has many capabilities |
| **MCP as Tool wrapper** | External services appear as regular `Tool` instances | Council could integrate external tools seamlessly |
| **Per-run structured logging** | Request/response/tool triple logging | Debug council deliberation flows |
| **Token-aware context summarization** | Dual-threshold (local + API), preserves user intent | Critical for multi-turn council conversations |
| **Workspace directory scoping** | All operations rooted in a single directory | Council file operations need boundaries |
| **Notes persistence** | JSON file with category filtering | Council could persist session context across runs |
| **Hierarchical config loading** | Dev → User → Package priority | Flexible deployment configurations |
| **Dual schema generation** | `to_schema()` + `to_openai_schema()` | Support multiple LLM providers |
| **Retry with exponential backoff** | Configurable per-request retries | Essential for parallel multi-model queries |

### Specific Interfaces That Map to LLM Council

1. **`Tool` base class** → Council "capabilities" (file access, web search, MCP tools)
2. **`ToolResult`** → Standardized output format for capability results
3. **`AgentLogger` pattern** → Council deliberation logger (stage1→stage2→stage3 tracing)
4. **`SkillLoader` + progressive disclosure** → Capability/skill management without context bloat
5. **`MCPServerConnection`** → Generic external service connector
6. **`_summarize_messages()`** → Long council conversations need context management
7. **`SessionNoteTool`** → Council session notes / persistent preferences

---

## 12. What NOT to Borrow and Why

| Pattern | Reason to Skip |
|---------|---------------|
| **Single-agent execution loop** | Council is multi-model parallel, not single-agent sequential. The `while step < max_steps` loop doesn't fit the 3-stage pipeline. |
| **Flat tool dict keyed by name** | Works for single agent, but Council needs per-model or per-stage tool availability control. |
| **No permission model** | Council operations involving file/shell access need explicit permission gating, not just directory scoping. |
| **LLM provider abstraction** | Council already has its own `openrouter.py`; Mini-Agent's `LLMClient` is designed for single-provider, not multi-model fan-out. |
| **ACP server** | Editor integration protocol irrelevant to Council's web UI + MCP server architecture. |
| **CLI interactive REPL** | Council has its own web frontend; CLI mode is irrelevant. |
| **Interleaved thinking handling** | MiniMax M2.5-specific feature; Council uses OpenRouter which handles thinking differently. |
| **Background shell management** | Overkill for Council — it doesn't need long-running background processes. |
| **Skills as git submodule** | Council capabilities should be inline, not a separate repo. The `SKILL.md` format itself is useful, but the submodule pattern is not. |
| **Cross-platform shell detection** | Council backend is Python on a known platform; no need for Windows/PowerShell detection. |

---

## Summary

Mini-Agent is a well-architected reference implementation for a single-agent system. Its strongest borrowable patterns for LLM Council are:

1. **Tool/ToolResult base classes** — clean capability interface
2. **Progressive disclosure skills** — token-efficient capability management
3. **MCP tool wrapping** — external service integration
4. **Per-run structured logging** — execution tracing
5. **Token-aware context summarization** — long conversation support
6. **Notes persistence** — cross-session memory
7. **Retry with backoff** — robust API calls

The main gaps vs. Council needs are: no multi-agent/parallel execution patterns, minimal permission model, and single-provider LLM focus.
