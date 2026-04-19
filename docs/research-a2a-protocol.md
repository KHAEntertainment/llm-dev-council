# A2A Protocol Research Report

**Date:** 2026-04-13
**Purpose:** Evaluate Google's Agent2Agent (A2A) protocol for potential use in LLM Council's architecture, specifically for coding agent ↔ council chairman communication.

---

## 1. Protocol Overview & Current Status

### What is A2A?
The **Agent2Agent (A2A) Protocol** is an open standard launched by Google in **April 2025** that enables communication and interoperability between independent, potentially opaque AI agent systems. Unlike MCP which connects agents to *tools*, A2A enables agents to communicate with *other agents* as peers.

### Current Status (April 2026)
- **Spec Version:** `1.0.0` (released March 12, 2026)
- **Previous versions:** 0.1.0, 0.2.6, 0.3.0
- **Governance:** Transferred to the **Linux Foundation** in June 2025
- **Partners:** 170+ organizations including Microsoft, AWS, IBM, SAP, Salesforce, Anthropic(!!), LangChain, and others
- **Python SDK:** `a2a-sdk` v0.3.26 (April 9, 2026) — implements spec v0.3; alpha version for v1.0 in development
- **Repository:** https://github.com/a2aproject/A2A (spec), https://github.com/a2aproject/a2a-python (Python SDK)
- **Official docs:** https://a2a-protocol.org

### Maturity Assessment
| Aspect | Rating | Notes |
|--------|--------|-------|
| Spec completeness | ⭐⭐⭐⭐⭐ | v1.0 released, comprehensive 3-layer architecture |
| Python SDK | ⭐⭐⭐⭐ | Active development (0.3.26), v1.0 alpha available, 1.8k stars |
| Ecosystem adoption | ⭐⭐⭐⭐ | 170+ partners, major cloud vendors onboard |
| Production readiness | ⭐⭐⭐ | Still early for production multi-agent systems; SDK moving fast |
| Documentation | ⭐⭐⭐⭐⭐ | Excellent — spec site, DeepWiki, tutorials, samples repo |

---

## 2. Architecture

### Three-Layer Design

```
Layer 3: Protocol Bindings
  ├── JSON-RPC 2.0 over HTTP/SSE  (baseline — easiest to adopt)
  ├── gRPC over HTTP/2              (high-performance)
  └── HTTP/REST with JSON           (RESTful)

Layer 2: Abstract Operations
  ├── SendMessage / SendStreamingMessage
  ├── GetTask / ListTasks / CancelTask
  ├── SubscribeToTask
  └── Push Notification management

Layer 1: Canonical Data Model (Protocol Buffers)
  ├── Task          (stateful unit of work)
  ├── Message       (communication turn, role: USER | AGENT)
  ├── Part          (text | file | structured data)
  ├── Artifact      (task output — generated files, data)
  ├── AgentCard     (agent metadata/capability declaration)
  └── TaskState     (lifecycle enum)
```

### Transport
- Built on **HTTP, JSON-RPC 2.0, Server-Sent Events** — all standard web technologies
- No proprietary transport; designed for enterprise IT stacks
- Supports all three bindings simultaneously; agents declare which they support in their AgentCard

### Message Format
- JSON-RPC 2.0 is the baseline binding
- Messages contain `Parts` which are polymorphic: text, raw bytes (base64), URLs, or structured data (JSON)
- Supports multimodal content (text, images, audio, video via file references)

---

## 3. Core Concepts

### Client ↔ Server Model
- **A2A Client:** Initiates requests, coordinates tasks (e.g., a coding agent asking for help)
- **A2A Server (Remote Agent):** Exposes capabilities, processes tasks (e.g., a council chairman)
- Communication is **task-oriented**, not just message passing

### Task Lifecycle
```
                    ┌─────────────┐
                    │  SUBMITTED  │ (task created)
                    └──────┬──────┘
                           ▼
                    ┌─────────────┐
               ┌────│   WORKING   │────┐
               │    └──────┬──────┘    │
               ▼           │           ▼
    ┌──────────────┐       │   ┌──────────────┐
    │INPUT_REQUIRED│◄──────┘   │AUTH_REQUIRED  │
    │(needs info)  │───────┐   │(needs creds)  │
    └──────────────┘       │   └───────────────┘
               ▲           ▼           ▲
               │    ┌─────────────┐    │
               └────│   WORKING   │────┘
                    └──────┬──────┘
                    ┌──────┼──────┬──────────┐
                    ▼      ▼      ▼          ▼
              COMPLETED  FAILED  CANCELED  REJECTED
              (terminal states — immutable)
```

Key insight: **`INPUT_REQUIRED` is the mechanism for bidirectional communication.** The server agent can transition a task to `INPUT_REQUIRED` with a message explaining what it needs, and the client must respond with additional information before the task resumes. This is exactly how a council chairman could ask the coding agent for clarification.

### Streaming
- Real-time via **Server-Sent Events (SSE)** for JSON-RPC, or native streaming for gRPC
- `SendStreamingMessage`: initiates task and streams updates
- `SubscribeToTask`: subscribe to updates on existing task
- Events: `TaskStatusUpdateEvent`, `TaskArtifactUpdateEvent`
- Stream closes when task reaches terminal state

### Push Notifications
- For long-running tasks (hours/days), clients can register webhook URLs
- Server POSTs updates to webhook when task state changes
- Multiple notification configs per task supported

---

## 4. Agent Card Specification

The **AgentCard** is a JSON metadata document that agents publish for discovery. It is served at a well-known URI:

```
GET https://{agent-server}/.well-known/agent-card.json
```

### Key Fields

```json
{
  "name": "LLM Council Chairman",
  "description": "Multi-model deliberation council that synthesizes answers from multiple LLMs",
  "version": "1.0.0",
  "documentation_url": "https://...",
  "provider": { "organization": "LucidityLabs" },

  "supported_interfaces": [
    {
      "url": "https://council.example.com/rpc",
      "protocol_binding": "jsonrpc"
    }
  ],

  "capabilities": {
    "streaming": true,
    "push_notifications": false,
    "extended_agent_card": false
  },

  "skills": [
    {
      "id": "deliberate",
      "name": "Council Deliberation",
      "description": "Run a 3-stage deliberation with multiple LLMs on a given question",
      "tags": ["multi-model", "deliberation", "synthesis"],
      "examples": ["What is the best sorting algorithm for this use case?"]
    }
  ],

  "default_input_modes": ["text/plain", "application/json"],
  "default_output_modes": ["text/plain", "text/markdown"],

  "security_schemes": {
    "bearer": {
      "type": "http",
      "scheme": "bearer"
    }
  },
  "security_requirements": [{ "bearer": [] }]
}
```

### Discovery Flow
1. Client fetches `/.well-known/agent-card.json` (public, unauthenticated)
2. Client inspects capabilities, skills, supported modes
3. Client authenticates per the declared `security_schemes`
4. Client sends messages to the declared endpoint

---

## 5. Bidirectional Communication

**Yes, A2A supports true bidirectional communication.** The mechanism:

1. **Client → Server:** Client sends messages via `SendMessage` or `SendStreamingMessage`
2. **Server → Client (asking for info):** Server transitions task to `INPUT_REQUIRED` state with a message explaining what it needs
3. **Client → Server (responding):** Client sends a follow-up message to the same task with the requested information
4. **Server resumes:** Task transitions back to `WORKING`

There is also `AUTH_REQUIRED` for when the server needs authentication credentials.

### Multi-Turn Conversations
- Tasks maintain a `history` of messages (conversation turns)
- Each message has a `role` (USER or AGENT) and contains `Parts`
- Tasks are grouped by `contextId` for logical conversation threading
- The `referenceTaskIds` field allows tasks to reference previous tasks

### Practical Example for LLM Council
```
Coding Agent → Council: "What's the best architecture for this feature?"
                        (SendStreamingMessage with code context)

Council → Task: WORKING (running Stage 1: parallel model queries)
Council → Task: status update (Stage 1 complete)
Council → Task: status update (Stage 2: peer review underway)
Council → Task: INPUT_REQUIRED "I need clarification: are you using
                 PostgreSQL or MySQL? The responses differ."

Coding Agent → Council: "PostgreSQL" (follow-up message to same task)

Council → Task: WORKING (resuming Stage 3: synthesis)
Council → Task: COMPLETED + Artifact (final synthesized answer as markdown)
```

---

## 6. A2A vs MCP: Complementary Protocols

### The Analogy
- **MCP** = USB-C port — one agent connecting to many tools/resources
- **A2A** = Phone calls between agents — agents collaborating as peers

### Side-by-Side Comparison

| Aspect | MCP | A2A |
|--------|-----|-----|
| **Purpose** | Agent ↔ Tool/Resource | Agent ↔ Agent |
| **Interaction model** | Function calling / tool use | Task-based conversation |
| **Statefulness** | Mostly stateless tool calls | Stateful task lifecycle |
| **Agent opacity** | Agent sees tool internals (schema) | Agents are opaque to each other |
| **Discovery** | Tool manifests | Agent Cards |
| **Long-running work** | Not designed for it | First-class support |
| **Streaming** | Limited | Built-in SSE/gRPC streaming |
| **Bidirectional** | Tool responds to calls | Agents can ask each other for info |
| **Human-in-the-loop** | Not built-in | Native INPUT_REQUIRED state |
| **Transport** | stdio, HTTP+SSE | HTTP, JSON-RPC, gRPC, REST |
| **Developed by** | Anthropic | Google (now Linux Foundation) |

### How They Work Together
The spec is explicit: **A2A complements MCP, not replaces it.**

```
┌─────────────────────────────────────────────────┐
│  Coding Agent (Claude Code)                      │
│  ├── Uses MCP: filesystem, git, shell tools      │
│  └── Uses A2A: talks to Council Agent            │
└─────────────────┬───────────────────────────────┘
                  │ A2A Protocol
                  ▼
┌─────────────────────────────────────────────────┐
│  Council Chairman Agent                          │
│  ├── Uses MCP: OpenRouter API tool               │
│  ├── Uses A2A: receives tasks from coding agent  │
│  └── Internal: runs 3-stage deliberation         │
└─────────────────────────────────────────────────┘
```

An agent can support **both** protocols simultaneously for different purposes.

---

## 7. Python SDK

### Official SDK: `a2a-sdk`

- **Install:** `pip install a2a-sdk` or `uv add a2a-sdk`
- **Package:** https://pypi.org/project/a2a-sdk/
- **GitHub:** https://github.com/a2aproject/a2a-python (1.8k stars, 79 contributors, 458 commits)
- **Current version:** 0.3.26 (April 9, 2026)
- **Spec compatibility:** Implements spec v0.3; v1.0 alpha in development
- **License:** Apache 2.0
- **Python:** 3.10+

### SDK Features
- Full A2A protocol compliance (client + server)
- Async-first (modern async Python)
- All three transport bindings: JSON-RPC, HTTP/REST, gRPC
- Optional integrations:
  - HTTP servers (FastAPI, Starlette)
  - gRPC support
  - OpenTelemetry tracing
  - SQL databases (PostgreSQL, MySQL, SQLite)
  - Vertex AI Task Store
  - Encryption

### Installation Options
```bash
pip install a2a-sdk                    # Core SDK
pip install "a2a-sdk[http-server]"     # + FastAPI/Starlette
pip install "a2a-sdk[grpc]"            # + gRPC
pip install "a2a-sdk[all]"             # Everything
```

### Sample Code Structure
The SDK provides server and client components:
- **Server side:** Define an `AgentCard`, implement message handlers, run HTTP server
- **Client side:** Create client, discover agent card, send messages, handle streaming

### Samples Repository
https://github.com/a2aproject/a2a-samples — contains Python and JavaScript examples

### Alternative Libraries
- `python-a2a` (community, simpler interface)
- `agent-framework-a2a` (higher-level framework)
- Framework integrations: Pydantic AI, LangGraph, CrewAI, ADK all have A2A support

---

## 8. Applicability to LLM Council

### Current Architecture (MCP)
```
Claude Code → MCP → consult_council tool → run_full_council() → result
```
- One-shot, tool-style interaction
- No streaming during deliberation
- No ability for council to ask clarifying questions
- Stateless — no conversation history between calls

### Potential A2A Architecture
```
Claude Code (A2A Client) → A2A → Council Agent (A2A Server)
```

Benefits:
1. **Streaming deliberation updates:** Client gets real-time status as council progresses through stages
2. **Bidirectional communication:** Council can ask coding agent for clarification (INPUT_REQUIRED)
3. **Task persistence:** Tasks maintain history; can be queried later
4. **Structured artifacts:** Council output delivered as typed Artifacts (markdown, JSON, files)
5. **Discoverable:** Agent Card describes council capabilities for any A2A-compatible client
6. **Framework agnostic:** Any A2A client could use the council, not just MCP-aware tools

### Concrete Design Sketch

**Council as A2A Server:**
```python
from a2a.server import A2AServer, AgentCard, AgentSkill

council_card = AgentCard(
    name="LLM Council",
    description="Multi-model deliberation system with anonymized peer review",
    skills=[
        AgentSkill(
            id="deliberate",
            name="Full Council Deliberation",
            description="3-stage process: collect responses, peer review, synthesis",
            tags=["multi-model", "deliberation"]
        )
    ],
    capabilities=AgentCapabilities(streaming=True),
    default_input_modes=["text/plain", "application/json"],
    default_output_modes=["text/markdown"]
)

# Handle incoming messages
async def handle_message(request):
    query = request.message.parts[0].text
    task = create_task()

    # Stage 1
    yield TaskStatusUpdate(state="working", message="Stage 1: Collecting responses...")
    responses = await stage1_collect_responses(query)

    # Stage 2
    yield TaskStatusUpdate(state="working", message="Stage 2: Peer review...")
    rankings = await stage2_collect_rankings(responses)

    # Optionally ask for clarification
    if ambiguous(responses):
        yield TaskStatusUpdate(state="input-required",
            message="Clarification needed: which database are you using?")
        # Wait for client response...
        clarification = await get_next_message()
        # Resume with clarification

    # Stage 3
    yield TaskStatusUpdate(state="working", message="Stage 3: Synthesizing...")
    final = await stage3_synthesize(responses, rankings)

    yield Artifact(parts=[TextPart(text=final)])
    yield TaskStatusUpdate(state="completed")
```

**Coding Agent as A2A Client:**
```python
from a2a.client import A2AClient

client = A2AClient("https://council.example.com")
card = await client.get_agent_card()

# Stream the deliberation
async for event in client.send_streaming_message(
    message=Message(role="user", parts=[TextPart(text="What's the best approach?")])
):
    if isinstance(event, TaskStatusUpdate):
        print(f"Council: {event.message}")
    elif isinstance(event, TaskArtifactUpdate):
        print(f"Result: {event.artifact.parts[0].text}")
    elif event.status.state == "input-required":
        # Council needs clarification — respond
        await client.send_message(task_id=event.task_id,
            message=Message(role="user", parts=[TextPart(text="PostgreSQL")]))
```

---

## 9. Risks & Concerns

### Technical Risks
1. **SDK maturity gap:** The Python SDK (v0.3.26) implements spec v0.3, not the latest v1.0. The v1.0 alpha exists but is not stable yet. Breaking changes between v0.3 → v1.0 include discriminator format changes.
2. **Complexity overhead:** A2A adds significant architectural complexity vs. the current simple MCP tool call. The 3-layer protocol, task lifecycle, and streaming infrastructure all need implementation.
3. **Claude Code A2A support:** Claude Code currently supports MCP natively but does **not** have built-in A2A client support. Using A2A would require either: (a) building a custom MCP tool that internally acts as an A2A client, or (b) waiting for Claude Code to add A2A client support.
4. **Deployment:** A2A requires the council to run as a persistent HTTP server (not just a Python module). This changes the deployment model significantly.

### Ecosystem Risks
1. **Spec velocity:** 10 spec versions in ~1 year is fast. API surface may continue to change.
2. **Multiple competing standards:** ACP (Agent Communication Protocol) also exists. While A2A has broader industry backing, fragmentation is possible.
3. **Google-centric:** Despite Linux Foundation governance, Google remains the primary driver. Risk of priorities not aligning with community needs.

### Practical Risks for LLM Council
1. **Over-engineering:** The current MCP tool approach is simple and works. A2A adds value mainly when: (a) the council needs to ask the coding agent questions, (b) streaming intermediate results matters, or (c) multiple different clients should use the council.
2. **Adoption timeline:** If Claude Code doesn't natively support A2A client mode, the benefits are diminished since you'd wrap A2A in an MCP tool anyway.

---

## 10. Recommendations for LLM Council

### Short-term (Now)
**Keep the MCP approach.** It works, it's simple, and Claude Code supports it natively. The current `consult_council` MCP tool is the right abstraction for single-turn, stateless council queries.

### Medium-term (When A2A SDK hits stable v1.0)
**Add A2A as a secondary interface** alongside MCP:
1. Wrap the council as an A2A server using `a2a-sdk[http-server]`
2. Expose an AgentCard at `/.well-known/agent-card.json`
3. Support streaming so clients see deliberation progress in real-time
4. Implement `INPUT_REQUIRED` for the council to ask clarifying questions
5. Keep the MCP tool working — it can internally use the A2A server

### Long-term (When Claude Code supports A2A)
**A2A becomes the primary interface** for coding agent ↔ council communication:
- Full streaming of 3-stage deliberation
- Bidirectional Q&A between council and coding agent
- Task history and context threading across multiple consultations
- Discoverable by any A2A-compatible agent, not just Claude Code

### Architecture Evolution
```
Phase 1 (Current):   Claude Code → MCP Tool → council.py (direct call)
Phase 2 (Medium):    Claude Code → MCP Tool → A2A Client → Council A2A Server
Phase 3 (Long-term): Claude Code → A2A Client → Council A2A Server
```

### Key Decision Points
1. **Wait for `a2a-sdk` v1.0 stable** before investing in A2A integration
2. **Watch for Claude Code A2A support** — this would be the primary trigger for Phase 3
3. **Streaming is the killer feature** — if real-time deliberation updates matter to users, A2A's value increases significantly
4. **Bidirectional communication** is valuable but not critical for the current single-query use case; becomes important for complex, multi-turn research tasks

---

## Sources

1. A2A Protocol Specification v1.0.0 — https://a2a-protocol.org/latest/specification/
2. Official A2A GitHub Repository — https://github.com/a2aproject/A2A
3. A2A Python SDK — https://github.com/a2aproject/a2a-python
4. Google Developers Blog: Announcing A2A (April 2025) — https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/
5. Google Cloud Blog: A2A Protocol Upgrade (July 2025) — https://cloud.google.com/blog/products/ai-machine-learning/agent2agent-protocol-upgrade
6. Linux Foundation: A2A Project Launch (June 2025) — https://www.linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project
7. Auth0: MCP vs A2A Guide — https://auth0.com/blog/mcp-vs-a2a/
8. IBM: What is A2A — https://www.ibm.com/think/topics/agent2agent-protocol
9. Google Developers Blog: Developer's Guide to AI Agent Protocols (March 2026) — https://developers.googleblog.com/developers-guide-to-ai-agent-protocols/
10. PyPI: a2a-sdk — https://pypi.org/project/a2a-sdk/
