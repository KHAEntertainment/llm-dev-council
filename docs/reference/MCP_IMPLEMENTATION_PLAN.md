# MCP Server Management — Implementation Plan (Approach B)

**Status**: In Progress
**Started**: 2026-04-18

## Overview

Build full-stack MCP server management: WebUI for adding/configuring MCP servers,
connector framework using the official `mcp` SDK, and integration into council
deliberation via a bounded tool-use loop.

## Phases

### Phase 1: Backend Infrastructure ✅
- [x] `backend/mcp_servers_storage.py` — JSON persistence for MCP server configs
- [x] `backend/mcp_connectors.py` — MCP client connector (stdio, sse, http)
- [x] `backend/main.py` — REST endpoints: CRUD + test + list-tools

### Phase 2: Frontend UI ✅
- [x] `frontend/src/components/MCPManager.jsx` — UI component
- [x] `frontend/src/components/MCPManager.css` — styles
- [x] `frontend/src/api.js` — MCP API client methods
- [x] Integrate MCPManager into ChatInterface.jsx

### Phase 3: Council Integration ✅
- [x] `backend/openrouter.py` — add `tools` parameter support
- [x] `backend/council.py` — bounded tool-use loop for Stage 1 and Stage 3
- [x] Frontend toggle: "Enable MCP Tools" per conversation

### Phase 4: Testing & Polish
- [ ] Test with SSE-based MCP server
- [ ] Test with stdio-based MCP server
- [ ] Test error handling and reconnection
- [ ] Verify scope enforcement (council vs chairman)

## Design Notes

### Data Model
```python
class MCPServerConfig(BaseModel):
    id: str
    name: str
    transport: Literal["stdio", "sse", "streamable_http"]
    enabled: bool = True
    scope: Literal["council", "chairman"] = "council"
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    auth_token: Optional[str] = None
```

### Connector API
```python
async def connect_server(config) -> ClientSession
async def list_tools(session) -> List[Dict]
async def call_tool(session, name, arguments) -> str
async def disconnect_server(session)
async def get_all_tools(scope: str) -> List[dict]
```

### REST Endpoints
- GET /api/mcp/servers
- POST /api/mcp/servers
- PUT /api/mcp/servers/{id}
- DELETE /api/mcp/servers/{id}
- POST /api/mcp/servers/{id}/test
- GET /api/mcp/servers/{id}/tools

## Completion Log

- **2026-04-18 14:24** — Plan written. Starting Phase 1.
- **2026-04-18 14:53** — Phase 1 complete. Backend storage, connector, and REST endpoints implemented and verified.
- **2026-04-18 15:17** — Phase 2 complete. Frontend UI built and integrated.
- **2026-04-18 15:35** — Phase 3 complete. Council integration with bounded tool-use loop implemented. Backend and frontend both compile cleanly.
