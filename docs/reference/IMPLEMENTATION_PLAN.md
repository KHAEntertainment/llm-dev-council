# Implementation Plan: Capability Substrate for LLM Dev Council

## Overview

The LLM Dev Council is a 3-stage deliberation system (parallel responses → anonymized peer ranking → chairman synthesis) that already has basic filesystem access via its web UI (mounted folders, directory browsing, chairman write proposals with approval). However, the architecture has two structural limitations: (1) file context is injected statically up front — council models cannot autonomously query files or tools during deliberation, and (2) the MCP server surface exposes filesystem tools that duplicate what coding agents already have natively.

This plan grafts Mini-Agent's **capability substrate** onto the council with a fundamentally different interface model: **build the agent tool-use loop for the WebUI first** (council models call tools like `read_file` and `search_files` mid-response during deliberation), then expose the council as an **A2A (Agent-to-Agent) server** for peer-to-peer agent communication. The MCP surface becomes a thin communication wrapper — not a filesystem API — and a pre-built **MCP-to-A2A bridge** connects Claude Code to the council's A2A server.

The **chairman is the explicit tool controller**: the chairman gets full tool access (read + propose_write) during Stage 3 synthesis, while Stage 1 council members get configurable read-only tool access per conversation. This maps naturally to the council's existing authority hierarchy.

**Protocol Stack**:
```
MCP  = Agent ↔ Tools/Data     (Claude Code's native interface)
A2A  = Agent ↔ Agent          (council's primary communication protocol)
Bridge = MCP → A2A translation (a2anet/a2a-mcp connects the two)
```

**Total Estimated Effort**: 5–8 weeks (6 phases)
**Risk Assessment**: Medium overall. Phase 2 is the highest-complexity phase (agent tool-use loop modifies the core LLM call path). Phase 4 (A2A server) carries SDK maturity risk (`a2a-sdk` is at v0.3.26, v1.0 alpha in development). Other phases are moderate/low risk.

---

## Phases

### Phase 1: Capability Layer Foundation

**Scope**:
Create the internal capability substrate that all subsequent phases build on. This is the structural transplant from Mini-Agent — unified tool interface, capability registry, session state, and structured logging — designed for direct model consumption from day one.

No external interface changes in this phase. The existing MCP tool and web UI continue to work unchanged.

Specifically:
1. **Create `backend/capabilities/` module** with:
   - `base.py` — `Capability` base class and `CapabilityResult` (Pydantic model with `success`, `content`, `error`, `metadata`). Include **dual schema generation methods** (`to_anthropic_schema()` and `to_openai_schema()`) — Phase 2 will pass these schemas to models during deliberation via OpenRouter's OpenAI-format tool calling.
   - `registry.py` — flat dict registry that loads and holds all capabilities. Key methods:
     - `get_schemas(format="openai")` — returns all registered capability schemas
     - `get_filtered_schemas(allowed_tools, format)` — returns schemas for specified tools only (for per-stage/per-skill filtering)
     - `execute(tool_name, **kwargs)` — dispatches to the named capability
   - `filesystem.py` — wraps existing `backend/filesystem.py` functions as capabilities: `list_files`, `read_file`, `search_files`, `write_file` (with `CapabilityResult` returns, session-aware path resolution)
   - `session.py` — session/workspace state manager:
     - `session_id`, `workspace_root`, `mounted_paths`
     - `chairman_write_enabled`, `enable_tool_use`, `tool_use_scope` (configurable: "chairman_only" | "all_stages")
     - `max_tool_rounds` (default: 5)
     - `session_notes` (category-filtered, JSON persistence in `data/sessions/`)
     - `approved_actions`, `proposed_changes` (for chairman write workflow)
   - `policy.py` — per-stage tool access control:
     - `get_allowed_tools(stage, role, session_config)` → returns tool name list
     - When `tool_use_scope="chairman_only"`: Stage 1/2 get no tools, Stage 3 chairman gets read + propose_write
     - When `tool_use_scope="all_stages"`: Stage 1 gets read-only tools, Stage 2 gets no tools, Stage 3 chairman gets read + propose_write
     - Always: Stage 2 ranking gets NO tools (evaluation is text-only by design)

2. **Create `backend/logging_trace.py`** — structured execution logger:
   - Per-run log files in `data/logs/` with timestamped filenames
   - Log events: incoming query, workspace/mounted paths, each stage 1 output, each stage 2 ranking, chairman verdict, **every tool call** (model, stage, tool name, arguments, result, duration), writes proposed, writes approved/applied
   - JSON-structured entries for machine readability

3. **Integrate with existing code**:
   - `backend/main.py` filesystem endpoints (`/api/fs/*`) refactored to call through capability registry instead of direct `filesystem.py` calls
   - Session state replaces the volatile `_mounts` dict in `filesystem.py` — mounts stored in `data/sessions/{session_id}.json`, restored on session load
   - Existing `backend/mcp.py` `consult_council` tool unchanged (backward compatible)

**Out of Scope**:
- Agent tool-use loop (Phase 2)
- A2A server (Phase 4)
- Skills system (Phase 3)
- New MCP tools (the MCP surface stays as-is)

**Dependencies**:
- None (this is the foundation)

**Acceptance Criteria**:
- [ ] `backend/capabilities/` module exists with `base.py`, `registry.py`, `filesystem.py`, `session.py`, `policy.py`
- [ ] `Capability` base class includes `to_anthropic_schema()` and `to_openai_schema()` returning valid tool definitions
- [ ] `CapabilityResult` is a Pydantic model with `success: bool`, `content: str`, `error: str | None`, `metadata: dict | None`
- [ ] Capability registry loads filesystem capabilities at startup
- [ ] `registry.get_schemas(format="openai")` returns tool definitions usable in OpenRouter API calls
- [ ] `registry.get_filtered_schemas(allowed_tools=["list_files", "read_file"], format="openai")` returns only specified tools
- [ ] `registry.execute("read_file", path="src/main.py")` returns a `CapabilityResult`
- [ ] `policy.get_allowed_tools(stage="stage1", role="council_member", session_config)` returns correct tools based on `tool_use_scope`
- [ ] Session state persists to `data/sessions/{session_id}.json` with atomic writes
- [ ] `backend/logging_trace.py` creates per-run log files with JSON-structured entries
- [ ] Existing web UI filesystem features work through the capability layer
- [ ] Existing `consult_council` MCP tool works unchanged

**Testing Strategy**:
- Unit tests for `Capability` base class and schema generation (both formats)
- Unit tests for registry (load, filter, execute, dispatch)
- Unit tests for policy (per-stage tool access for both `tool_use_scope` values)
- Unit tests for session state (create, persist, restore, update)
- Integration test: web UI mount folder → browse → read file → verify it goes through capability layer
- Verify existing MCP tool still works

**Implementation Notes**:
- The `Capability` base class mirrors Mini-Agent's `Tool` interface: `name`, `description`, `parameters` (JSON Schema), `async execute(**kwargs) → CapabilityResult`.
- **Dual schema generation is critical.** OpenRouter passes tools to models in OpenAI format. Phase 2 will pass `registry.get_filtered_schemas(format="openai")` as the `tools` parameter in API calls.
- Session state files use the same atomic write pattern as `backend/storage.py` (temp file + rename + fcntl locking).
- Keep existing `backend/filesystem.py` intact as the low-level implementation. `capabilities/filesystem.py` wraps it.
- The `tool_use_scope` config makes Stage 1 tool access user-configurable per conversation: `"chairman_only"` (cheaper, simpler) or `"all_stages"` (richer but more tokens).

**Estimated Effort**: 5–7 days

**Risk Level**: Medium — New abstraction layer, but additive (existing code stays intact).

---

### Phase 2: Agent Tool-Use Loop in WebUI

**Scope**:
The core architectural change: enable council models to call tools (read_file, search_files, list_files) during their deliberation stages via the web UI. This shifts the council from "static context injection" to "dynamic context gathering." The chairman gets read + propose_write tools in Stage 3.

This is where Mini-Agent's execution loop pattern gets transplanted — scoped to per-stage bounded tool-use rounds, not an open-ended agent session.

Specifically:
1. **Extend `backend/openrouter.py`** with tool-use support:
   - New function `query_model_with_tools(model, messages, tools, max_tool_rounds=5)`:
     - Call model with `tools` parameter (OpenAI function calling format)
     - If model responds with `tool_calls`: execute each via capability registry → append tool results as `role: "tool"` messages → re-call model
     - Repeat until model returns content (no more tool calls) or `max_tool_rounds` exceeded
     - Returns final content plus full tool-call history for logging
   - Existing `query_model()` unchanged when `tools` not provided (backward compatible)
   - Graceful fallback for models that don't support tool-use

2. **Extend `backend/council.py`** stage functions:
   - `stage1_collect_responses()` gains optional `tools` parameter. When provided + `tool_use_scope="all_stages"`, uses `query_model_with_tools()` for each parallel model query
   - `stage2_collect_rankings()` — **NO tools ever** (evaluation is text-only)
   - `stage3_synthesize_final()` gains `tools` parameter. Chairman uses `query_model_with_tools()` with read + propose_write tools
   - `run_full_council()` gains `enable_tool_use: bool` and reads `tool_use_scope` and `max_tool_rounds` from session config
   - Per-stage tool filtering: `policy.get_allowed_tools(stage, role, session_config)` → `registry.get_filtered_schemas()`

3. **Tool execution bridge** — `backend/capabilities/executor.py`:
   - `execute_tool_call(tool_call, registry, policy_context)` — dispatches an LLM tool call to the capability registry
   - Enforces policy: rejects tool calls not in the allowed set for this stage/role
   - Formats results as OpenRouter-compatible `role: "tool"` messages
   - All executions logged via the execution tracer

4. **Parallel tool-use isolation**:
   - In Stage 1, multiple models run in parallel via `asyncio.gather()`. Each model's tool-use loop maintains its own message history. Tool results from model A never leak into model B's context.
   - Per-session semaphore to limit concurrent tool calls (configurable, default: 3)

5. **SSE streaming updates for tool activity**:
   - New SSE event types: `tool_call_started { model, tool, args }`, `tool_call_completed { model, tool, success }`
   - Emitted within existing stage streaming in `backend/main.py`

6. **Frontend changes**:
   - Toggle in `ChatInterface.jsx`: "Enable Tool Use" (per-conversation, stored in conversation state)
   - When enabled, sub-toggle: "All Stages" vs "Chairman Only" (maps to `tool_use_scope`)
   - `max_tool_rounds` configurable in settings
   - `ToolActivityIndicator` component: shows tool activity per model during loading (e.g., "GPT-4 is reading src/config.py...")
   - Collapsible tool activity log within each stage's response tab

**Out of Scope**:
- A2A server (Phase 4)
- Skills system (Phase 3 — but the policy layer is ready for skill `allowed_tools`)
- New MCP tools or MCP changes
- Shell/bash tool exposure
- Chairman write approval UI changes (the existing `WriteApprovalDialog` continues to work for chairman proposals)

**Dependencies**:
- Phase 1: Capability layer, registry, policy, session state, executor

**Acceptance Criteria**:
- [ ] `query_model_with_tools()` handles the tool-use loop correctly: model requests tool → tool executes → result appended → model re-called
- [ ] Loop terminates after `max_tool_rounds` even if model keeps requesting tools
- [ ] Models that don't support tool-use gracefully fall back to `query_model()`
- [ ] Stage 1 models can call `read_file`, `list_files`, `search_files` when `tool_use_scope="all_stages"`
- [ ] Stage 1 models get NO tools when `tool_use_scope="chairman_only"`
- [ ] Stage 2 models NEVER get tools regardless of config
- [ ] Stage 3 chairman can call read tools + `propose_write` (when `chairman_write_enabled=True`)
- [ ] Policy enforcement: stage 1 model attempting `write_file` → rejected → error returned to model
- [ ] Parallel stage 1 queries don't interfere (isolated tool contexts)
- [ ] Concurrent tool calls rate-limited via semaphore
- [ ] SSE stream emits `tool_call_started` and `tool_call_completed` events
- [ ] Frontend toggle enables/disables tool-use per conversation
- [ ] Frontend shows tool activity indicator per model
- [ ] `enable_tool_use=False` (default) produces identical behavior to pre-Phase 2
- [ ] All tool calls logged in execution trace

**Testing Strategy**:
- Unit tests for `query_model_with_tools()` — mock OpenRouter responses with `tool_calls`, verify loop, verify max_tool_rounds termination
- Unit tests for executor — dispatch, policy enforcement, error handling, message formatting
- Integration test: enable tool-use → stage 1 model reads a file → file content appears in response
- Integration test: chairman uses tools in stage 3 → proposes write → proposal stored
- Integration test: policy violation → error returned to model, stage continues
- Concurrency test: 3 models doing parallel tool-use → no race conditions, no context leakage
- Manual test: enable tool-use on real codebase → compare response quality vs static injection
- A/B test: same query with tool-use on vs off

**Implementation Notes**:
- OpenRouter supports OpenAI function calling format. When `tools` is provided, compatible models return `tool_calls`. Not all models support this — check error handling.
- Tool results must use `role: "tool"` with `tool_call_id` matching the model's request.
- Each tool round-trip consumes tokens. With `max_tool_rounds=5`, a single stage 1 response could consume 5x normal tokens. Monitor and surface token usage.
- The existing `_build_fs_context()` in `council.py` (static context injection) remains available as fallback when `enable_tool_use=False`. Both paths coexist.
- This is borrowed from Mini-Agent's execution loop but scoped to bounded per-stage rounds.

**Estimated Effort**: 7–10 days

**Risk Level**: High — Modifies the core LLM call path (`openrouter.py`), orchestration flow (`council.py`), streaming pipeline (`main.py`), and frontend. Concurrent tool-use adds complexity. Mitigations: bounded tool rounds, per-stage policy, graceful fallback, default-off toggle.

---

### Phase 3: Minimal Skills System

**Scope**:
Implement a lightweight skills system borrowing Mini-Agent's progressive disclosure pattern. Skills are reusable professional workflows that configure the council's behavior and constrain which tools are available during agent deliberation.

Specifically:
1. **Skill contract** — `backend/capabilities/skills.py`:
   - `Skill` dataclass: `name`, `description`, `instructions` (markdown), `allowed_tools` (optional list), `chairman_only_instructions` (str), `metadata` (dict)
   - `SkillLoader` class: discovers `SKILL.md` files from `backend/skills/` directory
   - Progressive disclosure: system prompt gets skill names + descriptions only; full content injected only when selected

2. **Starter skills** in `backend/skills/`:
   - `repo-analysis/SKILL.md` — architecture mapping, dependency analysis, code quality. `allowed_tools: [read_file, list_files, search_files]`
   - `bug-triage/SKILL.md` — reproduce, isolate, root cause, propose fix. `allowed_tools: [read_file, search_files, propose_write]`
   - `refactor-planning/SKILL.md` — identify targets, plan incremental steps, assess risk. `allowed_tools: [read_file, list_files, search_files]`
   - `patch-review/SKILL.md` — correctness, security, style, edge cases. `allowed_tools: [read_file, search_files, propose_write]`

3. **Integration with tool-use** (Phase 2):
   - Selected skill's `allowed_tools` feeds into `policy.get_allowed_tools()` to constrain which tools models can call during deliberation
   - Skill instructions injected into stage prompts as additional context
   - `chairman_only_instructions` added only to Stage 3 prompt

4. **MCP + Web UI**:
   - `list_skills()` available via existing MCP tool or new thin MCP tool
   - Skill selector dropdown in `ChatInterface.jsx`

**Out of Scope**:
- More than 4 starter skills
- Skill marketplace or external loading
- Dynamic skill creation

**Dependencies**:
- Phase 1: Capability layer and registry
- Phase 2: Agent tool-use loop (skills constrain tool access)

**Acceptance Criteria**:
- [ ] `SKILL.md` format: YAML frontmatter + markdown body
- [ ] `SkillLoader` discovers and parses skills from `backend/skills/`
- [ ] Progressive disclosure: metadata-only in prompt; full content on selection
- [ ] 4 starter skills with appropriate `allowed_tools` lists
- [ ] Skill `allowed_tools` constrains agent tool-use during deliberation
- [ ] Web UI skill selector with description previews
- [ ] Token usage doesn't increase when no skill selected

**Testing Strategy**:
- Unit tests for `SkillLoader` (discovery, parsing, validation)
- Unit tests for progressive disclosure
- Integration test: skill with `allowed_tools=["read_file"]` prevents `search_files` during tool-use
- Manual test: `patch-review` skill via web UI on real code

**Implementation Notes**:
- Borrow Mini-Agent's `SKILL.md` YAML frontmatter format directly.
- Skill instructions are additive: `## Skill Context: {name}\n{instructions}` at the top of each prompt.
- When agent tool-use is active, `allowed_tools` feeds into: `policy.get_allowed_tools()` → `registry.get_filtered_schemas()` → the LLM API `tools` parameter.

**Estimated Effort**: 4–5 days

**Risk Level**: Low — Additive, no core flow changes.

---

### Phase 4: A2A Server Surface

**Scope**:
Expose the LLM Council as an **A2A (Agent-to-Agent) server** using the `a2a-sdk` Python package. This is the council's primary protocol for communicating with external agents. The council publishes an Agent Card, accepts tasks, streams deliberation progress, and can ask the calling agent for clarification via `INPUT_REQUIRED`.

Specifically:
1. **A2A server setup** — `backend/a2a_server.py`:
   - Uses `a2a-sdk[http-server]` (FastAPI/Starlette integration)
   - Can run alongside the existing FastAPI app (same process, different routes) or as a separate process
   - Publishes Agent Card at `/.well-known/agent-card.json`

2. **Agent Card**:
   ```json
   {
     "name": "LLM Dev Council",
     "description": "Multi-model deliberation council with anonymized peer review and chairman synthesis",
     "version": "1.0.0",
     "capabilities": { "streaming": true },
     "skills": [
       { "id": "deliberate", "name": "Full Council Deliberation", "description": "3-stage: collect → rank → synthesize" },
       { "id": "repo-analysis", "name": "Repository Analysis", "description": "Deep codebase analysis with tool-use" },
       { "id": "bug-triage", "name": "Bug Triage", "description": "Systematic bug investigation" },
       { "id": "refactor-planning", "name": "Refactor Planning", "description": "Safe refactoring plans" },
       { "id": "patch-review", "name": "Patch Review", "description": "Code review for correctness and security" }
     ],
     "default_input_modes": ["text/plain", "application/json"],
     "default_output_modes": ["text/markdown"]
   }
   ```

3. **Task handling**:
   - `SendStreamingMessage` → creates task → streams deliberation:
     - `WORKING` + "Stage 1: Collecting responses from N models..." (with model names)
     - `WORKING` + "Stage 2: Anonymized peer review underway..."
     - `WORKING` + "Stage 3: Chairman synthesizing..."
     - `COMPLETED` + Artifact (final synthesis as markdown, plus structured metadata)
   - Task maps to a council session (workspace, tool-use config, skill selection parsed from input message)

4. **Bidirectional communication via INPUT_REQUIRED**:
   - If Stage 1 responses are ambiguous or contradictory, the council can transition to `INPUT_REQUIRED` asking the calling agent for clarification
   - The calling agent responds → council resumes Stage 3 with additional context
   - Chairman can also trigger `INPUT_REQUIRED` if tool-use reveals the query needs refinement

5. **Chairman write proposals as Artifacts**:
   - When the chairman proposes file changes, they're returned as typed `Artifact` objects (not inline text)
   - The calling agent can inspect artifacts and decide whether to apply them
   - This replaces the MCP-based `chairman_propose_changes` / `chairman_apply_changes` pattern — the calling agent (which has its own filesystem tools) applies changes directly

6. **Multi-turn task context**:
   - Tasks maintain history via `contextId` for conversation threading
   - Follow-up questions reference previous tasks

**Out of Scope**:
- MCP-to-A2A bridge configuration (Phase 5)
- Authentication beyond basic API key (production auth is future work)
- Push notifications (webhook-based — not needed for local development)
- gRPC binding (JSON-RPC over HTTP is sufficient)

**Dependencies**:
- Phase 1: Capability layer and session state
- Phase 2: Agent tool-use loop (A2A server triggers tool-use-enabled deliberation)
- Phase 3: Skills (A2A skills map to council skills)

**Acceptance Criteria**:
- [ ] `a2a-sdk[http-server]` installed as dependency
- [ ] Agent Card served at `/.well-known/agent-card.json` with correct skills and capabilities
- [ ] `SendStreamingMessage` creates a task and streams SSE updates through all 3 stages
- [ ] Task lifecycle: `SUBMITTED` → `WORKING` (stage updates) → `COMPLETED` (with artifacts)
- [ ] `INPUT_REQUIRED` works: council asks for clarification → calling agent responds → council resumes
- [ ] Chairman write proposals returned as typed `Artifact` objects
- [ ] Skill selection: calling agent specifies skill in message → correct skill loaded for deliberation
- [ ] Workspace path: calling agent specifies workspace in message → council mounts and uses it
- [ ] Tool-use config: calling agent can enable/disable tool-use and set scope
- [ ] Multi-turn: follow-up messages to same `contextId` share conversation context
- [ ] Concurrent tasks don't interfere (separate session state per task)

**Testing Strategy**:
- Unit tests for A2A message handling and task lifecycle
- Integration test: send task → receive streaming updates → verify all 3 stages complete
- Integration test: trigger INPUT_REQUIRED → respond → verify task resumes
- Integration test with `a2a-sdk` client: full round-trip
- Manual test: use A2A Python client to query council about a real codebase

**Implementation Notes**:
- The `a2a-sdk` is at v0.3.26 (spec v0.3). A v1.0 alpha exists. **Pin the dependency version** and expect to update when v1.0 stabilizes. Discriminator format changes between v0.3 and v1.0 may require adaptation.
- The A2A server can share the FastAPI process with the existing web API — mount A2A routes alongside existing routes. Or run separately on a different port. Decide during implementation.
- The "chairman applies changes" model shifts with A2A: the council **proposes** changes as artifacts, the **calling agent** applies them. This is cleaner because the calling agent has its own filesystem context and can verify changes before applying.
- For INPUT_REQUIRED, add configurable behavior: `auto_clarify=True` (council asks for clarification when ambiguous) vs `auto_clarify=False` (council does its best with available context). Default: True for A2A, False for web UI.

**Estimated Effort**: 6–8 days

**Risk Level**: Medium-High — SDK maturity risk (v0.3, not v1.0). The protocol itself is well-specified, but the Python SDK may have gaps or breaking changes. Mitigation: pin SDK version, abstract the A2A integration behind an adapter layer, keep existing web UI and MCP paths working as fallbacks.

---

### Phase 5: MCP Communication Layer + A2A Bridge

**Scope**:
Restructure the MCP surface from filesystem tools to a thin communication layer, and configure the MCP-to-A2A bridge so Claude Code can talk to the council's A2A server.

The MCP surface becomes:
- `consult_council(query, files)` — existing tool, kept for backward compatibility (direct call, no A2A)
- `consult_council_a2a(query, workspace?, skill?, enable_tool_use?)` — routes through A2A server internally, returns streamed result
- No filesystem tools on MCP (Claude Code has its own)

Plus the external bridge:
- Configure `a2anet/a2a-mcp` bridge so Claude Code can discover and talk to the council's A2A server natively via MCP

Specifically:
1. **Thin MCP wrapper** — update `backend/mcp.py`:
   - Keep `consult_council(query, files)` unchanged (backward compat)
   - Add `consult_council_a2a(query, workspace_path?, skill?, enable_tool_use?, tool_use_scope?)` that internally creates an A2A task against the local A2A server and returns the result
   - Remove the planned filesystem MCP tools (no `list_workspace_files`, `read_workspace_file`, etc.) — the council handles its own file access internally via tool-use

2. **MCP-to-A2A bridge configuration**:
   - Document how to add the `a2anet/a2a-mcp` bridge to Claude Code's MCP config:
     ```json
     {
       "mcpServers": {
         "council-bridge": {
           "command": "uvx",
           "args": ["a2anet-mcp", "--agent-url", "http://localhost:8001"]
         }
       }
     }
     ```
   - This gives Claude Code `send_message`, `get_task`, `get_agents` tools that speak A2A to the council
   - Claude Code can discover the council's Agent Card, send tasks, stream results, and respond to INPUT_REQUIRED

3. **Bridge integration testing**:
   - Verify end-to-end: Claude Code → MCP bridge → A2A → council → streaming result back
   - Document the setup process for users

**Out of Scope**:
- Custom MCP-to-A2A bridge implementation (use existing `a2anet/a2a-mcp`)
- Authentication for the bridge (local development only)
- External connectors (Phase 6)

**Dependencies**:
- Phase 4: A2A server must be running and functional

**Acceptance Criteria**:
- [ ] `consult_council` MCP tool still works unchanged (backward compat)
- [ ] `consult_council_a2a` MCP tool routes through A2A server and returns results
- [ ] No filesystem MCP tools exposed (no `list_files`, `read_file`, etc. on MCP surface)
- [ ] `a2anet/a2a-mcp` bridge successfully discovers council's Agent Card
- [ ] Claude Code can send a query through the bridge → council deliberates with tool-use → result streams back
- [ ] Claude Code can respond to INPUT_REQUIRED from council (bidirectional)
- [ ] Setup documentation exists for configuring the bridge in Claude Code
- [ ] Chairman's proposed changes returned as artifacts that Claude Code can inspect and apply

**Testing Strategy**:
- Integration test: `consult_council_a2a` MCP tool → A2A server → full deliberation → result
- End-to-end test with Claude Code: configure bridge → send query → verify streaming → verify artifacts
- Manual test: real codebase query through Claude Code → council uses tool-use → chairman proposes changes → Claude Code applies them

**Implementation Notes**:
- The `a2anet/a2a-mcp` package (v2.0.0, March 2026) provides 6 tools including `send_message`, `get_task`, `get_agents`, and artifact viewing. It handles multi-turn, long-running tasks, and automatic artifact minimization.
- The bridge is a small project (11 stars, 2 contributors). Expect to spend some time on setup and testing. Have a fallback plan: the direct `consult_council_a2a` MCP tool works without the bridge.
- Authentication: for local development, no auth needed. For remote deployment, the A2A Agent Card declares security schemes. The bridge handles auth propagation. This is future work.

**Estimated Effort**: 3–4 days

**Risk Level**: Medium — Depends on third-party bridge package stability. Mitigation: the direct `consult_council_a2a` MCP tool works without the bridge; the bridge is an enhancement for richer interaction.

---

### Phase 6: External Connectors + Context Management + Hardening

**Scope**:
Add external MCP client connectors (DeepWiki as first), token-aware context management for long sessions, and harden the entire system.

Specifically:
1. **External MCP connector framework** — `backend/connectors/`:
   - `base.py` — `MCPConnector` base class with `connect()`, `disconnect()`, `list_tools()`, `call_tool()`
   - `registry.py` — loads from `backend/connectors/config.json`, manages lifecycle
   - `deepwiki.py` — DeepWiki connector, exposes `deepwiki_search` and `deepwiki_read` as capabilities
   - Connectors register as capabilities in the main registry → available to council models during tool-use

2. **Context management** — `backend/capabilities/context.py`:
   - Token counting via `tiktoken` (cl100k_base)
   - Conversation summarization when approaching token limits
   - Recognizes tool-call/tool-result message types for summarization (critical for tool-use sessions)
   - Configurable per-session token limit (default: 80,000)

3. **Logging polish**:
   - Log viewer endpoint: `GET /api/logs`, `GET /api/logs/{run_id}`
   - Web UI log viewer component
   - A2A task logs accessible via `get_session_log`
   - Log rotation (30-day auto-cleanup)

4. **Hardening**:
   - Session auto-expiry (24h inactivity, configurable)
   - Mount validation on session restore
   - Error boundaries: capability failures → `CapabilityResult(success=False)`, no crashes
   - Retry with exponential backoff for OpenRouter API calls (borrow Mini-Agent's `RetryConfig`)
   - Concurrent session safety (file locking on session state)
   - Rate limiting on A2A tasks

**Out of Scope**:
- More than DeepWiki as an external connector
- Authentication/authorization (local-only)
- Multi-user support
- Cloud deployment

**Dependencies**:
- All previous phases should be complete

**Acceptance Criteria**:
- [ ] DeepWiki connector works: `deepwiki_search(repo, query)` returns results
- [ ] Connectors register as capabilities → available during agent tool-use
- [ ] Token counting works; summarization triggers at threshold
- [ ] Summarization handles tool-call messages correctly
- [ ] Log viewer shows execution traces
- [ ] Sessions auto-expire after inactivity
- [ ] OpenRouter retries with exponential backoff
- [ ] Concurrent session state access is safe (file locking)

**Testing Strategy**:
- Integration test with real DeepWiki
- Token counting and summarization tests
- Failure injection: kill OpenRouter mid-request → verify retry
- Concurrent session access stress test
- Session expiry verification

**Implementation Notes**:
- Add `tiktoken` as dependency.
- Summarization uses a lightweight model (e.g., `gemini-2.5-flash`).
- DeepWiki is read-only and low-risk — good first connector.
- Connectors are lazy-initialized (no startup penalty).

**Estimated Effort**: 5–7 days

**Risk Level**: Low-Medium — Quality-of-life and robustness. Token management is the most complex piece.

---

## Dependencies Map

```
Phase 1 (Capability Layer Foundation)
    ↓
Phase 2 (Agent Tool-Use in WebUI)  ←  highest complexity
    ↓
Phase 3 (Skills System)  ←  can start after Phase 1 if Phase 2 is delayed
    ↓
Phase 4 (A2A Server Surface)  ←  requires Phases 1, 2, 3
    ↓
Phase 5 (MCP Communication + A2A Bridge)  ←  requires Phase 4
    ↓
Phase 6 (Connectors + Context Mgmt + Hardening)  ←  benefits from all above
```

Phase 3 (Skills) is **partially independent** — it can start after Phase 1. But it reaches full value only after Phase 2 (tool-use) because skills constrain which tools are available.

Phases 4-5 (A2A) can begin once Phases 1-2 are solid. Phase 5 is lightweight once Phase 4 works.

---

## Architecture Summary

### Before (Current)
```
Claude Code → MCP → consult_council(query, files) → council.py → static context → result
Web UI → REST API → council.py → _build_fs_context() → static context → result
```

### After (Target)
```
Claude Code → a2anet/a2a-mcp bridge → A2A protocol → Council A2A Server
                                                            ↓
Web UI → REST API (with SSE) ────────────────────→ council.py
                                                            ↓
                                              ┌─────────────┴──────────────┐
                                              ↓                            ↓
                                     Stage 1 (parallel)           Stage 3 (chairman)
                                     query_model_with_tools()     query_model_with_tools()
                                              ↓                            ↓
                                     read_file, list_files,       read_file, search_files,
                                     search_files                 propose_write
                                     (configurable per-convo)     (always available)
                                              ↓                            ↓
                                     ← capabilities/registry.py executes tools →
                                     ← capabilities/policy.py enforces access →
                                              ↓
                                     Stage 2 (peer review) — NO tools, text-only
                                              ↓
                                     Result → Artifacts (A2A) or SSE (WebUI)
                                     Chairman proposals → Artifacts for calling agent
```

---

## Protocol Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Claude Code                                              │
│  ├── Native tools: filesystem, git, shell (MCP)          │
│  └── Council access: a2anet/a2a-mcp bridge (MCP→A2A)    │
└────────────────────┬─────────────────────────────────────┘
                     │ A2A Protocol (JSON-RPC/SSE)
                     ▼
┌──────────────────────────────────────────────────────────┐
│  LLM Dev Council (A2A Server)                             │
│  ├── Agent Card: skills, capabilities, streaming          │
│  ├── Task lifecycle: submitted → working → completed      │
│  ├── Bidirectional: INPUT_REQUIRED for clarification      │
│  ├── Artifacts: chairman proposals as typed outputs        │
│  └── Internal tool-use: models call capabilities directly │
│       ├── read_file, list_files, search_files             │
│       ├── propose_write (chairman only)                   │
│       └── deepwiki_search (via MCP connector)             │
└──────────────────────────────────────────────────────────┘
```

**Key insight**: The council handles its own tool-use internally. External agents communicate at the task/conversation level via A2A, not by calling filesystem tools. The chairman proposes changes as artifacts; the calling agent (which has its own tools) decides whether to apply them.

---

## Borrowing Map: Mini-Agent → LLM Council

| Mini-Agent Concept | Borrow? | Adaptation |
|---|---|---|
| `Tool` + `ToolResult` base classes | **Yes** | `Capability` + `CapabilityResult` |
| Dual schema generation | **Yes** | Both formats for OpenRouter tool-use |
| Flat tool dict registry | **Yes** | Capability registry with filtered schema support |
| Agent execution loop (call→tool→re-call) | **Yes** | Bounded per-stage tool-use loop |
| `SKILL.md` with YAML frontmatter | **Yes** | Same format, 4 dev-focused skills |
| Progressive skill disclosure | **Yes** | Token-efficient capability management |
| `MCPServerConnection` connector | **Yes** | External connector framework (DeepWiki) |
| `AgentLogger` per-run logging | **Yes** | Structured execution tracer |
| `SessionNoteTool` persistence | **Yes** | Session notes with category filtering |
| `workspace_dir` scoping | **Yes** | Workspace root in session state |
| Token-aware summarization | **Yes** | Context management with tool-message awareness |
| Retry with exponential backoff | **Yes** | OpenRouter retry |
| BashTool / shell execution | **No** | Too risky; read + propose_write is sufficient |
| MiniMax model assumptions | **No** | Keep OpenRouter multi-provider |
| Large skills catalog | **No** | 4 focused dev skills |
| ACP server | **No** | A2A replaces this need |

---

## Feature Flags

| Flag | Scope | Default | Controls |
|---|---|---|---|
| `enable_tool_use` | Per-conversation | `False` | Whether models can call tools during deliberation |
| `tool_use_scope` | Per-conversation | `"chairman_only"` | `"chairman_only"` or `"all_stages"` |
| `max_tool_rounds` | Per-conversation / global | `5` | Max tool-call round-trips per stage |
| `chairman_write_enabled` | Per-conversation | `True` | Whether chairman can propose writes |
| `auto_clarify` | Per-task (A2A) | `True` | Whether council can ask calling agent for clarification |
| `connectors.*.enabled` | Global | per-connector | Enable/disable external connectors |

---

## Rollback Plan

**Per-Phase Rollback**:
- **Phase 1**: Capability layer is additive. Rollback: revert `backend/capabilities/`. Existing code unchanged.
- **Phase 2**: Tool-use gated by `enable_tool_use=False` (default). Rollback: set to `False` permanently.
- **Phase 3**: Skills fully additive. Rollback: remove `backend/skills/` and skill loader.
- **Phase 4**: A2A server is a new surface. Rollback: shut it down. Web UI and MCP unaffected.
- **Phase 5**: Bridge is external config. Rollback: remove bridge from Claude Code MCP config. Direct MCP tools still work.
- **Phase 6**: Connectors are opt-in. Context management can be disabled via `token_limit: null`.

**Emergency Rollback**: `git revert` to last good commit. All storage is JSON files, no migrations.

---

## Best Practices

- [ ] Start each phase by verifying existing functionality still works
- [ ] Keep `backend/council.py` orchestration as the core — extend via parameters
- [ ] Every capability returns `CapabilityResult` — never raw values, never exceptions
- [ ] Session state writes use atomic file operations
- [ ] Default `enable_tool_use=False` — never break existing behavior
- [ ] Pin `a2a-sdk` version — expect breaking changes before v1.0 stable
- [ ] Keep `CLAUDE.md` updated as architecture evolves

---

## Progress Tracking

- [ ] Phase 1: Capability Layer Foundation
- [ ] Phase 2: Agent Tool-Use Loop in WebUI
- [ ] Phase 3: Minimal Skills System
- [ ] Phase 4: A2A Server Surface
- [ ] Phase 5: MCP Communication Layer + A2A Bridge
- [ ] Phase 6: External Connectors + Context Management + Hardening

---

## Notes & Learnings

_Add notes as phases are completed._

---

**Created**: 2026-04-13
**Last Updated**: 2026-04-13
**Status**: Planning Complete — Ready for Phase 1
