"""FastAPI backend for LLM Council."""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Any, Optional, Literal
import uuid
import json
import html
import asyncio
import httpx
from datetime import datetime

from . import storage
from . import presets
from . import filesystem
from . import github_account
from . import github_repos
from . import mcp_servers_storage
from . import mcp_connectors
from .council import run_full_council, generate_conversation_title, stage1_collect_responses, stage2_collect_rankings, stage3_synthesize_final, calculate_aggregate_rankings
from .config import load_config, save_config, get_council_models, get_chairman_model, OPENROUTER_API_KEY
from .providers import list_copilot_models_if_configured

app = FastAPI(title="LLM Council API")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# File writes must originate from chairman proposals returned by this process.
_write_proposals: Dict[str, Dict[str, Any]] = {}
MAX_ATTACHMENTS = 5
MAX_ATTACHMENT_DATA_CHARS = 14 * 1024 * 1024
REDACTED_MCP_FIELDS = {"auth_token", "env", "headers"}


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    council_models: Optional[List[str]] = None
    chairman_model: Optional[str] = None


class Attachment(BaseModel):
    """Validated user attachment payload."""
    filename: str
    mimeType: str
    data: str
    type: Literal["file", "image"]

    @field_validator("data")
    @classmethod
    def validate_data_size(cls, data):
        if len(data) > MAX_ATTACHMENT_DATA_CHARS:
            raise ValueError("Attachment data is too large")
        return data


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    content: str
    attachments: Optional[List[Attachment]] = None
    allow_writes: bool = False
    enable_mcp_tools: bool = False

    @field_validator("attachments")
    @classmethod
    def validate_attachments(cls, attachments):
        if attachments is None:
            return attachments
        if len(attachments) > MAX_ATTACHMENTS:
            raise ValueError(f"At most {MAX_ATTACHMENTS} attachments are allowed")
        return attachments


class UpdateConfigRequest(BaseModel):
    """Request to update council configuration."""
    council_models: Optional[List[str]] = None
    chairman_model: Optional[str] = None


class UpdateConversationModelsRequest(BaseModel):
    """Request to update a conversation's model config."""
    council_models: List[str]
    chairman_model: str


class SavePresetRequest(BaseModel):
    """Request to save a preset."""
    name: str
    council_models: List[str]
    chairman_model: str


class ArchiveConversationRequest(BaseModel):
    """Request to archive/unarchive a conversation."""
    archived: bool


class MountFolderRequest(BaseModel):
    """Request to mount a folder."""
    path: str


class WriteFileRequest(BaseModel):
    """Request to write a file (chairman only)."""
    path: str
    content: str
    proposal_id: str


class UpdateMountsRequest(BaseModel):
    """Request to update conversation mounts."""
    mounted_paths: List[str]


class MountGithubRepoRequest(BaseModel):
    """Request to mount a GitHub repository."""
    repo: str
    ref: Optional[str] = None
    path: Optional[str] = None


class UpdateGithubMountsRequest(BaseModel):
    """Request to restore conversation GitHub mounts."""
    github_mounts: List[Dict[str, Any]]


class SaveGithubTokenRequest(BaseModel):
    """Request to store a local GitHub token."""
    token: str


class GithubOAuthStartRequest(BaseModel):
    """Request to begin GitHub OAuth."""
    frontend_redirect: Optional[str] = None


class MCPServerConfigRequest(BaseModel):
    """Request to create or update an MCP server config."""
    name: str
    transport: str
    enabled: bool = True
    scope: str = "council"
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, Any]] = None
    url: Optional[str] = None
    headers: Optional[Dict[str, Any]] = None
    auth_token: Optional[str] = None


class ConversationMetadata(BaseModel):
    """Conversation metadata for list view."""
    id: str
    created_at: str
    title: str
    message_count: int
    archived: bool = False


class Conversation(BaseModel):
    """Full conversation with all messages."""
    id: str
    created_at: str
    title: str
    messages: List[Dict[str, Any]]
    council_models: Optional[List[str]] = None
    chairman_model: Optional[str] = None
    mounted_paths: List[str] = Field(default_factory=list)
    github_mounts: List[Dict[str, Any]] = Field(default_factory=list)


def _register_write_proposals(stage3_result: Dict[str, Any], scope: str) -> None:
    """Assign opaque IDs to chairman write proposals for later approval."""
    proposals = stage3_result.get("proposed_writes") or []
    for proposal in proposals:
        proposal_id = proposal.get("id") or str(uuid.uuid4())
        proposal["id"] = proposal_id
        _write_proposals[proposal_id] = {
            "path": proposal.get("path"),
            "content": proposal.get("content", ""),
            "scope": scope,
            "created_at": datetime.utcnow().isoformat(),
            "used": False,
        }


def _validate_write_proposal(proposal_id: str, path: str, content: str) -> Dict[str, Any]:
    """Validate a registered chairman write proposal."""
    proposal = _write_proposals.get(proposal_id)
    if not proposal or proposal.get("used"):
        raise HTTPException(status_code=403, detail="File write was not approved")
    if proposal.get("path") != path or proposal.get("content") != content:
        raise HTTPException(status_code=403, detail="File write does not match approved proposal")
    return proposal


def _redact_mcp_server(server: Dict[str, Any]) -> Dict[str, Any]:
    """Return a browser-safe MCP server config without secrets."""
    return {key: value for key, value in server.items() if key not in REDACTED_MCP_FIELDS}


def _redact_mcp_servers(servers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return browser-safe MCP server configs without secrets."""
    return [_redact_mcp_server(server) for server in servers]


def _attachment_dicts(attachments: Optional[List[Attachment]]) -> Optional[List[Dict[str, Any]]]:
    """Convert validated attachment models to plain dictionaries."""
    if attachments is None:
        return None
    return [attachment.model_dump() for attachment in attachments]


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "LLM Council API"}


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations(archived: bool = False):
    """List conversations (metadata only), filtered by archive status."""
    return storage.list_conversations(archived=archived)


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(request: CreateConversationRequest):
    """Create a new conversation."""
    conversation_id = str(uuid.uuid4())
    # Use provided models or fall back to global config
    council_models = request.council_models or get_council_models()
    chairman_model = request.chairman_model or get_chairman_model()
    conversation = await asyncio.to_thread(storage.create_conversation, conversation_id, council_models, chairman_model)
    return conversation


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    """Get a specific conversation with all its messages."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.post("/api/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and run the 3-stage council process.
    Returns the complete response with all stages.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    # Add user message
    attachments = _attachment_dicts(request.attachments)
    await asyncio.to_thread(storage.add_user_message, conversation_id, request.content, attachments=attachments)

    # If this is the first message, generate a title
    if is_first_message:
        title = await generate_conversation_title(request.content)
        await asyncio.to_thread(storage.update_conversation_title, conversation_id, title)

    # Get per-conversation model config
    council_models = conversation.get("council_models")
    chairman_model = conversation.get("chairman_model")
    mounted_paths = conversation.get("mounted_paths", [])
    github_mounts = conversation.get("github_mounts", [])
    filesystem.restore_mounts(mounted_paths, scope=conversation_id)
    await github_repos.restore_mounts(github_mounts, scope=conversation_id)

    # Run the 3-stage council process
    stage1_results, stage2_results, stage3_result, metadata = await run_full_council(
        request.content,
        council_models=council_models,
        chairman_model=chairman_model,
        attachments=attachments,
        mounted_paths=mounted_paths if mounted_paths else None,
        github_mounts=github_mounts if github_mounts else None,
        allow_writes=request.allow_writes,
        enable_mcp_tools=request.enable_mcp_tools
    )

    # Add assistant message with all stages
    _register_write_proposals(stage3_result, conversation_id)
    await asyncio.to_thread(
        storage.add_assistant_message,
        conversation_id,
        stage1_results,
        stage2_results,
        stage3_result,
    )

    # Return the complete response with metadata
    return {
        "stage1": stage1_results,
        "stage2": stage2_results,
        "stage3": stage3_result,
        "metadata": metadata
    }


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and stream the 3-stage council process.
    Returns Server-Sent Events as each stage completes.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    async def event_generator():
        council_exit_stack = None
        chairman_exit_stack = None
        try:
            # Add user message
            attachments = _attachment_dicts(request.attachments)
            await asyncio.to_thread(storage.add_user_message, conversation_id, request.content, attachments=attachments)

            # Start title generation in parallel (don't await yet)
            title_task = None
            if is_first_message:
                title_task = asyncio.create_task(generate_conversation_title(request.content))

            # Get per-conversation model config (reuse conversation from outer scope)
            conv = storage.get_conversation(conversation_id)
            council_models = conv.get("council_models")
            chairman_model = conv.get("chairman_model")
            mounted_paths = conv.get("mounted_paths", [])
            github_mounts = conv.get("github_mounts", [])
            filesystem.restore_mounts(mounted_paths, scope=conversation_id)
            await github_repos.restore_mounts(github_mounts, scope=conversation_id)

            # --- MCP Tool Setup ---
            council_tools = None
            council_tool_sessions = {}
            chairman_tools = None
            chairman_tool_sessions = {}

            if request.enable_mcp_tools:
                try:
                    council_tools, council_tool_sessions, council_exit_stack = await mcp_connectors.get_tools_for_scope("council")
                except Exception as e:
                    print(f"Failed to load council MCP tools: {e}")
                try:
                    chairman_tools, chairman_tool_sessions, chairman_exit_stack = await mcp_connectors.get_tools_for_scope("chairman")
                except Exception as e:
                    print(f"Failed to load chairman MCP tools: {e}")

            # Event queue for tool-call status updates during stages
            event_queue = asyncio.Queue()
            def on_event(event):
                event_queue.put_nowait(event)

            # Stage 1: Collect responses
            yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"
            stage1_task = asyncio.create_task(stage1_collect_responses(
                request.content,
                models=council_models,
                attachments=attachments,
                mounted_paths=mounted_paths if mounted_paths else None,
                github_mounts=github_mounts if github_mounts else None,
                tools=council_tools,
                tool_to_session=council_tool_sessions,
                on_event=on_event,
            ))
            while not stage1_task.done():
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.2)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    pass
            stage1_results = await stage1_task
            while not event_queue.empty():
                yield f"data: {json.dumps(event_queue.get_nowait())}\n\n"
            yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results})}\n\n"

            # Stage 2: Collect rankings
            yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"
            stage2_results, label_to_model = await stage2_collect_rankings(
                request.content,
                stage1_results,
                models=council_models,
                attachments=attachments,
                mounted_paths=mounted_paths if mounted_paths else None,
                github_mounts=github_mounts if github_mounts else None,
            )
            aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
            yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_results, 'metadata': {'label_to_model': label_to_model, 'aggregate_rankings': aggregate_rankings}})}\n\n"

            # Stage 3: Synthesize final answer
            yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"
            stage3_task = asyncio.create_task(stage3_synthesize_final(
                request.content,
                stage1_results,
                stage2_results,
                chairman_model=chairman_model,
                attachments=attachments,
                mounted_paths=mounted_paths if mounted_paths else None,
                github_mounts=github_mounts if github_mounts else None,
                allow_writes=request.allow_writes,
                tools=chairman_tools,
                tool_to_session=chairman_tool_sessions,
                on_event=on_event,
            ))
            while not stage3_task.done():
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.2)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    pass
            stage3_result = await stage3_task
            _register_write_proposals(stage3_result, conversation_id)
            while not event_queue.empty():
                yield f"data: {json.dumps(event_queue.get_nowait())}\n\n"
            yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3_result})}\n\n"

            # Wait for title generation if it was started
            if title_task:
                title = await title_task
                await asyncio.to_thread(storage.update_conversation_title, conversation_id, title)
                yield f"data: {json.dumps({'type': 'title_complete', 'data': {'title': title}})}\n\n"

            # Save complete assistant message
            await asyncio.to_thread(
                storage.add_assistant_message,
                conversation_id,
                stage1_results,
                stage2_results,
                stage3_result,
            )

            # Send completion event
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        except Exception as e:
            # Send error event
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            # Clean up MCP connections
            if council_exit_stack:
                try:
                    await council_exit_stack.aclose()
                except Exception as e:
                    print(f"Error closing council MCP connections: {e}")
            if chairman_exit_stack:
                try:
                    await chairman_exit_stack.aclose()
                except Exception as e:
                    print(f"Error closing chairman MCP connections: {e}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.get("/api/models")
async def list_models():
    """Fetch available models from OpenRouter and configured additive providers."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
            )
            response.raise_for_status()
            data = response.json()
            models = [
                    {
                        "id": m["id"],
                        "name": m.get("name", m["id"]),
                        "description": m.get("description", ""),
                        "context_length": m.get("context_length", 0),
                        "pricing": m.get("pricing", {"prompt": "0", "completion": "0"}),
                        "provider": "openrouter",
                    }
                    for m in data.get("data", [])
                ]
            models.extend(list_copilot_models_if_configured())
            return {"models": models}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch models from OpenRouter: {str(e)}") from e


# --- GitHub account endpoints ---

@app.get("/api/account/github/status")
async def github_status():
    """Return browser-safe GitHub account status."""
    return github_account.get_github_status()


@app.post("/api/account/github/token")
async def save_github_token(request: SaveGithubTokenRequest):
    """Store a local GitHub token after verifying it against GitHub."""
    try:
        return await github_account.store_access_token(request.token, token_source="local")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=403, detail=f"GitHub token was rejected: {e.response.status_code}") from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.delete("/api/account/github")
async def disconnect_github():
    """Remove stored local GitHub account data."""
    github_account.disconnect_github()
    return github_account.get_github_status()


@app.post("/api/account/github/oauth/start")
async def start_github_oauth(request: GithubOAuthStartRequest):
    """Create a GitHub OAuth authorization URL."""
    try:
        return github_account.create_oauth_start(request.frontend_redirect)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/account/github/oauth/callback")
async def github_oauth_callback(code: str, state: str):
    """Handle GitHub OAuth callback for local single-user account setup."""
    try:
        await github_account.complete_oauth_callback(code, state)
        return HTMLResponse(
            "<html><body><h1>GitHub connected</h1><p>You can close this tab and return to LLM Council.</p></body></html>"
        )
    except Exception as e:
        return HTMLResponse(
            f"<html><body><h1>GitHub connection failed</h1><p>{html.escape(str(e))}</p></body></html>",
            status_code=400,
        )


@app.get("/api/config")
async def get_config():
    """Get the current council configuration."""
    config = load_config()
    return config


@app.put("/api/config")
async def update_config(request: UpdateConfigRequest):
    """Update the global council configuration."""
    config = load_config()
    if request.council_models is not None:
        config["council_models"] = request.council_models
    if request.chairman_model is not None:
        config["chairman_model"] = request.chairman_model
    save_config(config)
    return config


@app.put("/api/conversations/{conversation_id}/models")
async def update_conversation_models(conversation_id: str, request: UpdateConversationModelsRequest):
    """Update the model configuration for a specific conversation."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await asyncio.to_thread(
        storage.update_conversation_models,
        conversation_id,
        request.council_models,
        request.chairman_model,
    )
    return {
        "council_models": request.council_models,
        "chairman_model": request.chairman_model
    }


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation."""
    deleted = await asyncio.to_thread(storage.delete_conversation, conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": True}


@app.put("/api/conversations/{conversation_id}/archive")
async def archive_conversation(conversation_id: str, request: ArchiveConversationRequest):
    """Archive or unarchive a conversation."""
    try:
        conversation = await asyncio.to_thread(storage.archive_conversation, conversation_id, request.archived)
        return {"archived": conversation.get("archived", False)}
    except ValueError:
        raise HTTPException(status_code=404, detail="Conversation not found")


@app.get("/api/conversations/{conversation_id}/export")
async def export_conversation(conversation_id: str, format: str = "markdown"):
    """Export a conversation in the specified format."""
    from fastapi.responses import Response

    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    export_format = format

    if export_format == "json":
        content = json.dumps(conversation, indent=2)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{conversation_id}.json"'}
        )

    elif export_format == "markdown":
        content = _conversation_to_markdown(conversation)
        return Response(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{conversation.get("title", "conversation").replace(" ", "_")}.md"'}
        )

    elif export_format == "pdf":
        pdf_bytes = _conversation_to_pdf(conversation)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{conversation.get("title", "conversation").replace(" ", "_")}.pdf"'}
        )

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {export_format}. Use markdown, json, or pdf.")


def _conversation_to_markdown(conv: dict) -> str:
    """Convert a conversation dict to markdown."""
    lines = []
    lines.append(f"# {conv.get('title', 'New Conversation')}")
    lines.append(f"\n*Created: {conv.get('created_at', '')}*\n")

    for msg in conv.get("messages", []):
        if msg["role"] == "user":
            lines.append("## You\n")
            lines.append(msg["content"])
            lines.append("")
        elif msg["role"] == "assistant":
            lines.append("## LLM Council\n")

            if msg.get("stage1"):
                lines.append("### Stage 1: Individual Responses\n")
                for resp in msg["stage1"]:
                    model = resp.get("model", "unknown")
                    lines.append(f"**{model}**\n")
                    lines.append(resp.get("response", ""))
                    lines.append("---\n")

            if msg.get("stage2"):
                lines.append("### Stage 2: Peer Rankings\n")
                for rank in msg["stage2"]:
                    model = rank.get("model", "unknown")
                    lines.append(f"**{model}**\n")
                    lines.append(rank.get("ranking", ""))
                    if rank.get("parsed_ranking"):
                        lines.append(f"\n*Parsed ranking: {', '.join(rank['parsed_ranking'])}*\n")
                    lines.append("---\n")

            if msg.get("stage3"):
                lines.append("### Stage 3: Final Council Answer\n")
                model = msg["stage3"].get("model", "unknown")
                lines.append(f"**Chairman: {model}**\n")
                lines.append(msg["stage3"].get("response", ""))
                lines.append("")

    return "\n".join(lines)


def _conversation_to_pdf(conv: dict) -> bytes:
    """Convert a conversation dict to PDF using reportlab."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.lib.units import inch
    import io

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()

    # Custom styles
    styles.add(ParagraphStyle(
        'ConvTitle',
        parent=styles['Title'],
        fontSize=18,
        spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        'StageHeader',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        'ModelName',
        parent=styles['Heading3'],
        fontSize=11,
        spaceAfter=4,
        textColor='#4a90e2',
    ))
    styles.add(ParagraphStyle(
        'BodyWrap',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        spaceAfter=8,
    ))

    story = []
    story.append(Paragraph(conv.get('title', 'New Conversation'), styles['ConvTitle']))
    story.append(Paragraph(f"Created: {conv.get('created_at', '')}", styles['Normal']))
    story.append(Spacer(1, 0.3 * inch))

    for msg in conv.get("messages", []):
        if msg["role"] == "user":
            story.append(Paragraph("You", styles['StageHeader']))
            story.append(Paragraph(msg["content"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")[:2000], styles['BodyWrap']))
            story.append(HRFlowable(width="80%", thickness=1, color='#e0e0e0'))
            story.append(Spacer(1, 0.2 * inch))

        elif msg["role"] == "assistant":
            story.append(Paragraph("LLM Council", styles['StageHeader']))

            if msg.get("stage1"):
                story.append(Paragraph("Stage 1: Individual Responses", styles['StageHeader']))
                for resp in msg["stage1"]:
                    model = resp.get("model", "unknown")
                    story.append(Paragraph(f"<b>{model}</b>", styles['ModelName']))
                    text = resp.get("response", "")[:2000]
                    story.append(Paragraph(text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), styles['BodyWrap']))
                    story.append(HRFlowable(width="60%", thickness=0.5, color='#e0e0e0'))

            if msg.get("stage3"):
                story.append(Paragraph("Stage 3: Final Council Answer", styles['StageHeader']))
                model = msg["stage3"].get("model", "unknown")
                story.append(Paragraph(f"<b>Chairman: {model}</b>", styles['ModelName']))
                text = msg["stage3"].get("response", "")[:2000]
                story.append(Paragraph(text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), styles['BodyWrap']))

            story.append(Spacer(1, 0.3 * inch))

    doc.build(story)
    return buffer.getvalue()


# --- Filesystem endpoints ---

@app.post("/api/fs/mount")
async def mount_folder(request: MountFolderRequest):
    """Mount a folder path on the host filesystem."""
    try:
        result = filesystem.mount_folder(request.path)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except NotADirectoryError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/fs/mount/{mount_id}")
async def unmount_folder(mount_id: str):
    """Unmount a folder."""
    if not filesystem.unmount_folder(mount_id):
        raise HTTPException(status_code=404, detail="Mount not found")
    return {"unmounted": True}


@app.get("/api/fs/mounts")
async def list_mounts():
    """List all current mounts."""
    return filesystem.list_mounts()


@app.get("/api/fs/browse")
async def browse_directory(path: str):
    """Browse a directory within mounted paths."""
    try:
        return filesystem.list_directory(path)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/fs/read")
async def read_file(path: str):
    """Read a file from within mounted paths."""
    try:
        return filesystem.read_file(path)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=413, detail=str(e))


@app.get("/api/fs/search")
async def search_files(path: str, pattern: str):
    """Search for files matching a glob pattern within mounted paths."""
    try:
        return filesystem.search_files(path, pattern)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@app.post("/api/fs/write")
async def write_file(request: WriteFileRequest):
    """Write a file to disk after validating a chairman proposal approval."""
    proposal = _validate_write_proposal(request.proposal_id, request.path, request.content)
    try:
        filesystem.set_active_scope(proposal.get("scope"))
        result = filesystem.write_file(request.path, request.content)
        proposal["used"] = True
        return result
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/conversations/{conversation_id}/mounts")
async def update_conversation_mounts(conversation_id: str, request: UpdateMountsRequest):
    """Update the mounted paths for a conversation."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await asyncio.to_thread(storage.update_conversation_mounts, conversation_id, request.mounted_paths)
    # Restore mounts in the filesystem module, even when the list is empty.
    filesystem.restore_mounts(request.mounted_paths, scope=conversation_id)
    return {"mounted_paths": request.mounted_paths}


@app.post("/api/conversations/{conversation_id}/github-mounts")
async def mount_github_repo(conversation_id: str, request: MountGithubRepoRequest):
    """Mount a GitHub repository read-only for a conversation."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    try:
        github_repos.set_active_scope(conversation_id)
        result = await github_repos.mount_repo(request.repo, ref=request.ref, path=request.path)
        mounts = github_repos.list_mounts()
        await asyncio.to_thread(storage.update_conversation_github_mounts, conversation_id, mounts)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {e.response.status_code}") from e


@app.put("/api/conversations/{conversation_id}/github-mounts")
async def update_github_mounts(conversation_id: str, request: UpdateGithubMountsRequest):
    """Restore GitHub repository mounts for a conversation."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    restored = await github_repos.restore_mounts(request.github_mounts, scope=conversation_id)
    await asyncio.to_thread(storage.update_conversation_github_mounts, conversation_id, restored)
    return {"github_mounts": restored}


@app.get("/api/conversations/{conversation_id}/github-mounts")
async def list_github_mounts(conversation_id: str):
    """List GitHub repository mounts for a conversation."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    github_repos.set_active_scope(conversation_id)
    return github_repos.list_mounts()


@app.delete("/api/conversations/{conversation_id}/github-mounts/{mount_id}")
async def unmount_github_repo(conversation_id: str, mount_id: str):
    """Unmount a GitHub repository from a conversation."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    github_repos.set_active_scope(conversation_id)
    if not github_repos.unmount_repo(mount_id):
        raise HTTPException(status_code=404, detail="GitHub mount not found")
    mounts = github_repos.list_mounts()
    await asyncio.to_thread(storage.update_conversation_github_mounts, conversation_id, mounts)
    return {"unmounted": True}


@app.get("/api/conversations/{conversation_id}/github/browse")
async def browse_github_repo(conversation_id: str, path: str):
    """Browse a directory inside a mounted GitHub repository."""
    if storage.get_conversation(conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    try:
        github_repos.set_active_scope(conversation_id)
        return await github_repos.list_directory(path)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/conversations/{conversation_id}/github/read")
async def read_github_file(conversation_id: str, path: str):
    """Read a file inside a mounted GitHub repository."""
    if storage.get_conversation(conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    try:
        github_repos.set_active_scope(conversation_id)
        return await github_repos.read_file(path)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=413, detail=str(e)) from e


@app.get("/api/conversations/{conversation_id}/github/search")
async def search_github_files(conversation_id: str, path: str, pattern: str):
    """Search files inside a mounted GitHub repository."""
    if storage.get_conversation(conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    try:
        github_repos.set_active_scope(conversation_id)
        return await github_repos.search_files(path, pattern)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@app.get("/api/presets")
async def list_presets():
    """List all saved presets."""
    return presets.list_presets()


@app.post("/api/presets")
async def save_preset_endpoint(request: SavePresetRequest):
    """Save a new preset."""
    return presets.save_preset(
        name=request.name,
        council_models=request.council_models,
        chairman_model=request.chairman_model
    )


@app.delete("/api/presets/{preset_id}")
async def delete_preset(preset_id: str):
    """Delete a preset."""
    deleted = presets.delete_preset(preset_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Preset not found")
    return {"deleted": True}


# --- MCP Server endpoints ---

@app.get("/api/mcp/servers")
async def list_mcp_servers():
    """List all configured MCP servers."""
    return _redact_mcp_servers(mcp_servers_storage.list_servers())


@app.post("/api/mcp/servers")
async def create_mcp_server(request: MCPServerConfigRequest):
    """Add a new MCP server configuration."""
    server = mcp_servers_storage.add_server(request.model_dump())
    return _redact_mcp_server(server)


@app.put("/api/mcp/servers/{server_id}")
async def update_mcp_server(server_id: str, request: MCPServerConfigRequest):
    """Update an existing MCP server configuration."""
    updated = mcp_servers_storage.update_server(server_id, request.model_dump())
    if not updated:
        raise HTTPException(status_code=404, detail="MCP server not found")
    return _redact_mcp_server(updated)


@app.delete("/api/mcp/servers/{server_id}")
async def delete_mcp_server(server_id: str):
    """Delete an MCP server configuration."""
    deleted = mcp_servers_storage.delete_server(server_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="MCP server not found")
    return {"deleted": True}


@app.post("/api/mcp/servers/{server_id}/test")
async def test_mcp_server(server_id: str):
    """Test connection to an MCP server and return status."""
    config = mcp_servers_storage.get_server(server_id)
    if not config:
        raise HTTPException(status_code=404, detail="MCP server not found")
    result = await mcp_connectors.test_connection(config)
    return result


@app.get("/api/mcp/servers/{server_id}/tools")
async def list_mcp_server_tools(server_id: str):
    """List tools available from a connected MCP server."""
    config = mcp_servers_storage.get_server(server_id)
    if not config:
        raise HTTPException(status_code=404, detail="MCP server not found")
    try:
        tools = await mcp_connectors.get_server_tools(config)
        return {"tools": tools}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
