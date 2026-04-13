"""FastAPI backend for LLM Council."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uuid
import json
import asyncio
import httpx

from . import storage
from . import presets
from . import filesystem
from .council import run_full_council, generate_conversation_title, stage1_collect_responses, stage2_collect_rankings, stage3_synthesize_final, calculate_aggregate_rankings
from .config import load_config, save_config, get_council_models, get_chairman_model, OPENROUTER_API_KEY

app = FastAPI(title="LLM Council API")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    council_models: Optional[List[str]] = None
    chairman_model: Optional[str] = None


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    content: str
    attachments: Optional[List[Dict[str, Any]]] = None
    allow_writes: bool = False


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


class UpdateMountsRequest(BaseModel):
    """Request to update conversation mounts."""
    mounted_paths: List[str]


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
    conversation = storage.create_conversation(conversation_id, council_models, chairman_model)
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
    storage.add_user_message(conversation_id, request.content)

    # If this is the first message, generate a title
    if is_first_message:
        title = await generate_conversation_title(request.content)
        storage.update_conversation_title(conversation_id, title)

    # Get per-conversation model config
    council_models = conversation.get("council_models")
    chairman_model = conversation.get("chairman_model")
    mounted_paths = conversation.get("mounted_paths", [])

    # Run the 3-stage council process
    stage1_results, stage2_results, stage3_result, metadata = await run_full_council(
        request.content,
        council_models=council_models,
        chairman_model=chairman_model,
        attachments=request.attachments,
        mounted_paths=mounted_paths if mounted_paths else None,
        allow_writes=request.allow_writes
    )

    # Add assistant message with all stages
    storage.add_assistant_message(
        conversation_id,
        stage1_results,
        stage2_results,
        stage3_result
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
        try:
            # Add user message
            storage.add_user_message(conversation_id, request.content)

            # Start title generation in parallel (don't await yet)
            title_task = None
            if is_first_message:
                title_task = asyncio.create_task(generate_conversation_title(request.content))

            # Get per-conversation model config
            conv = storage.get_conversation(conversation_id)
            council_models = conv.get("council_models")
            chairman_model = conv.get("chairman_model")
            mounted_paths = conv.get("mounted_paths", [])

            # Stage 1: Collect responses
            yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"
            stage1_results = await stage1_collect_responses(request.content, models=council_models, attachments=request.attachments, mounted_paths=mounted_paths if mounted_paths else None)
            yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results})}\n\n"

            # Stage 2: Collect rankings
            yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"
            stage2_results, label_to_model = await stage2_collect_rankings(request.content, stage1_results, models=council_models, attachments=request.attachments, mounted_paths=mounted_paths if mounted_paths else None)
            aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
            yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_results, 'metadata': {'label_to_model': label_to_model, 'aggregate_rankings': aggregate_rankings}})}\n\n"

            # Stage 3: Synthesize final answer
            yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"
            stage3_result = await stage3_synthesize_final(request.content, stage1_results, stage2_results, chairman_model=chairman_model, attachments=request.attachments, mounted_paths=mounted_paths if mounted_paths else None, allow_writes=request.allow_writes)
            yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3_result})}\n\n"

            # Wait for title generation if it was started
            if title_task:
                title = await title_task
                storage.update_conversation_title(conversation_id, title)
                yield f"data: {json.dumps({'type': 'title_complete', 'data': {'title': title}})}\n\n"

            # Save complete assistant message
            storage.add_assistant_message(
                conversation_id,
                stage1_results,
                stage2_results,
                stage3_result
            )

            # Send completion event
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        except Exception as e:
            # Send error event
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

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
    """Fetch available models from OpenRouter."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
            )
            response.raise_for_status()
            data = response.json()
            return {
                "models": [
                    {
                        "id": m["id"],
                        "name": m.get("name", m["id"]),
                        "description": m.get("description", ""),
                        "context_length": m.get("context_length", 0),
                        "pricing": m.get("pricing", {"prompt": "0", "completion": "0"}),
                    }
                    for m in data.get("data", [])
                ]
            }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch models from OpenRouter: {str(e)}")


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

    storage.update_conversation_models(
        conversation_id,
        request.council_models,
        request.chairman_model
    )
    return {
        "council_models": request.council_models,
        "chairman_model": request.chairman_model
    }


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation."""
    deleted = storage.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": True}


@app.put("/api/conversations/{conversation_id}/archive")
async def archive_conversation(conversation_id: str, request: ArchiveConversationRequest):
    """Archive or unarchive a conversation."""
    try:
        conversation = storage.archive_conversation(conversation_id, request.archived)
    except ValueError:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"id": conversation_id, "archived": request.archived}


@app.get("/api/conversations/{conversation_id}/export")
async def export_conversation(conversation_id: str, format: str = "markdown"):
    """Export a conversation in the specified format."""
    from fastapi.responses import Response

    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if format == "json":
        content = json.dumps(conversation, indent=2)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{conversation_id}.json"'}
        )

    elif format == "markdown":
        content = _conversation_to_markdown(conversation)
        return Response(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{conversation.get("title", "conversation").replace(" ", "_")}.md"'}
        )

    elif format == "pdf":
        pdf_bytes = _conversation_to_pdf(conversation)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{conversation.get("title", "conversation").replace(" ", "_")}.pdf"'}
        )

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}. Use markdown, json, or pdf.")


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
            story.append(Paragraph(msg["content"][:2000], styles['BodyWrap']))
            story.append(HRFlowable(width="80%", thickness=1, color='#e0e0e0'))
            story.append(Spacer(1, 0.2 * inch))

        elif msg["role"] == "assistant":
            story.append(Paragraph("LLM Council", styles['StageHeader']))

            if msg.get("stage1"):
                story.append(Paragraph("Stage 1: Individual Responses", styles['StageHeader']))
                for resp in msg["stage1"]:
                    model = resp.get("model", "unknown")
                    story.append(Paragraph(f"<b>{model}</b>", styles['ModelName']))
                    text = resp.get("response", "")[:3000]
                    story.append(Paragraph(text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")[:2000], styles['BodyWrap']))
                    story.append(HRFlowable(width="60%", thickness=0.5, color='#e0e0e0'))

            if msg.get("stage3"):
                story.append(Paragraph("Stage 3: Final Council Answer", styles['StageHeader']))
                model = msg["stage3"].get("model", "unknown")
                story.append(Paragraph(f"<b>Chairman: {model}</b>", styles['ModelName']))
                text = msg["stage3"].get("response", "")[:3000]
                story.append(Paragraph(text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")[:2000], styles['BodyWrap']))

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
    """Write a file to disk. Chairman-only operation requiring user approval."""
    try:
        return filesystem.write_file(request.path, request.content)
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
    storage.update_conversation_mounts(conversation_id, request.mounted_paths)
    # Restore mounts in the filesystem module
    filesystem.restore_mounts(request.mounted_paths)
    return {"mounted_paths": request.mounted_paths}


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)