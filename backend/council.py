"""3-stage LLM Council orchestration."""

from typing import List, Dict, Any, Tuple, Optional
from .openrouter import query_models_parallel, query_model
from .config import get_council_models, get_chairman_model
from . import filesystem

# Maximum size for inline text/json attachments (100KB)
MAX_INLINE_ATTACHMENT_CHARS = 100_000


def _build_fs_context(mounted_paths: List[str] = None) -> str:
    """Build a filesystem context summary for injection into prompts."""
    if not mounted_paths:
        return ""

    lines = ["\n\n--- Mounted Filesystem Context ---"]
    for path in mounted_paths:
        try:
            entries = filesystem.list_directory(path)
            lines.append(f"\nFolder: {path}")
            for entry in entries[:50]:
                prefix = "[DIR] " if entry["type"] == "directory" else "      "
                size_str = f" ({entry['size']} bytes)" if entry.get("size") else ""
                lines.append(f"  {prefix}{entry['name']}{size_str}")
            if len(entries) > 50:
                lines.append(f"  ... and {len(entries) - 50} more entries")
        except Exception:
            lines.append(f"\nFolder: {path} (unable to read)")

    lines.append("--- End Filesystem Context ---\n")
    return "\n".join(lines)


def format_user_message(content: str, attachments: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Format user message with optional attachments for multimodal queries."""
    if attachments is None or len(attachments) == 0:
        return {"role": "user", "content": content}

    message_content = [{"type": "text", "text": content}]

    for att in attachments:
        if att["type"] == "image":
            url = att["data"]
            if not url.startswith("data:"):
                url = f"data:{att['mimeType']};base64,{url}"
            message_content.append({
                "type": "image_url",
                "image_url": {"url": url}
            })
        elif att["type"] == "file":
            if att["mimeType"].startswith("text/") or att["mimeType"] == "application/json":
                try:
                    import base64
                    data = att["data"]
                    if "," in data:
                        data = data.split(",")[1]
                    decoded_bytes = base64.b64decode(data)
                    decoded_text = decoded_bytes.decode('utf-8')
                    # Truncate oversized inline content
                    if len(decoded_text) > MAX_INLINE_ATTACHMENT_CHARS:
                        decoded_text = decoded_text[:MAX_INLINE_ATTACHMENT_CHARS] + "\n...[truncated]..."
                    filename_label = f"File: {att.get('filename', 'Attached File')}\n"
                    message_content.append({
                        "type": "text",
                        "text": f"\n--- {filename_label} ---\n{decoded_text}\n---------------\n"
                    })
                except Exception as e:
                    print(f"Error decoding text file: {e}")
                    url = att["data"]
                    if not url.startswith("data:"):
                        url = f"data:{att['mimeType']};base64,{url}"
                    message_content.append({
                        "type": "file",
                        "file": {"url": url, "type": att["mimeType"]}
                    })
            else:
                url = att["data"]
                if not url.startswith("data:"):
                    url = f"data:{att['mimeType']};base64,{url}"
                message_content.append({
                    "type": "file",
                    "file": {"url": url, "type": att["mimeType"]}
                })

    return {"role": "user", "content": message_content}


async def stage1_collect_responses(user_query: str, models: Optional[List[str]] = None, attachments: Optional[List[Dict[str, Any]]] = None, mounted_paths: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Stage 1: Collect individual responses from all council models.

    Args:
        user_query: The user's question
        models: Optional list of model IDs to use (defaults to config)
        attachments: Optional file/image attachments
        mounted_paths: Optional list of mounted folder paths for context

    Returns:
        List of dicts with 'model' and 'response' keys
    """
    council_models = models if models is not None else get_council_models()
    fs_context = _build_fs_context(mounted_paths)
    query_with_context = user_query + fs_context if fs_context else user_query
    messages = [format_user_message(query_with_context, attachments)]

    # Query all models in parallel
    responses = await query_models_parallel(council_models, messages)

    # Format results
    stage1_results = []
    for model, response in responses.items():
        if response is not None:  # Only include successful responses
            stage1_results.append({
                "model": model,
                "response": response.get('content', '')
            })

    return stage1_results


async def stage2_collect_rankings(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    models: Optional[List[str]] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
    mounted_paths: Optional[List[str]] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """
    Stage 2: Each model ranks the anonymized responses.

    Args:
        user_query: The original user query
        stage1_results: Results from Stage 1

    Returns:
        Tuple of (rankings list, label_to_model mapping)
    """
    # Create anonymized labels for responses (Response A, Response B, etc.)
    labels = [chr(65 + i) for i in range(len(stage1_results))]  # A, B, C, ...

    # Create mapping from label to model name
    label_to_model = {
        f"Response {label}": result['model']
        for label, result in zip(labels, stage1_results)
    }

    # Build the ranking prompt
    responses_text = "\n\n".join([
        f"Response {label}:\n{result['response']}"
        for label, result in zip(labels, stage1_results)
    ])

    ranking_prompt = f"""You are evaluating different responses to the following question:

Question: {user_query}

Here are the responses from different models (anonymized):

{responses_text}

Your task:
1. First, evaluate each response individually. For each response, explain what it does well and what it does poorly.
2. Then, at the very end of your response, provide a final ranking.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Do not add any other text or explanations in the ranking section

Example of the correct format for your ENTIRE response:

Response A provides good detail on X but misses Y...
Response B is accurate but lacks depth on Z...
Response C offers the most comprehensive answer...

FINAL RANKING:
1. Response C
2. Response A
3. Response B

Now provide your evaluation and ranking:"""

    messages = [format_user_message(ranking_prompt, attachments)]

    # Get rankings from all council models in parallel
    council_models = models if models is not None else get_council_models()
    responses = await query_models_parallel(council_models, messages)

    # Format results
    stage2_results = []
    for model, response in responses.items():
        if response is not None:
            full_text = response.get('content', '')
            parsed = parse_ranking_from_text(full_text)
            stage2_results.append({
                "model": model,
                "ranking": full_text,
                "parsed_ranking": parsed
            })

    return stage2_results, label_to_model


async def stage3_synthesize_final(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    chairman_model: Optional[str] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
    mounted_paths: Optional[List[str]] = None,
    allow_writes: bool = False
) -> Dict[str, Any]:
    """
    Stage 3: Chairman synthesizes final response.

    Args:
        user_query: The original user query
        stage1_results: Individual model responses from Stage 1
        stage2_results: Rankings from Stage 2
        chairman_model: Optional chairman model ID (defaults to config)

    Returns:
        Dict with 'model' and 'response' keys
    """
    chairman = chairman_model if chairman_model is not None else get_chairman_model()
    # Build comprehensive context for chairman
    stage1_text = "\n\n".join([
        f"Model: {result['model']}\nResponse: {result['response']}"
        for result in stage1_results
    ])

    stage2_text = "\n\n".join([
        f"Model: {result['model']}\nRanking: {result['ranking']}"
        for result in stage2_results
    ])

    fs_context = _build_fs_context(mounted_paths)

    write_instruction = ""
    if allow_writes and mounted_paths:
        write_instruction = """

IMPORTANT - FILE WRITE CAPABILITY:
You have the ability to propose file writes to the user's mounted directories. If the user's question involves creating, modifying, or generating files, you may include write proposals at the END of your response in the following JSON format:

```proposed_writes
[
  {"path": "/absolute/path/to/file.ext", "content": "file content here", "description": "Brief description of what this file does"}
]
```

Only propose writes that are directly relevant to the user's request. The user will review and approve each proposed write before it is executed."""

    chairman_prompt = f"""You are the Chairman of an LLM Council. Multiple AI models have provided responses to a user's question, and then ranked each other's responses.

Original Question: {user_query}
{fs_context}
STAGE 1 - Individual Responses:
{stage1_text}

STAGE 2 - Peer Rankings:
{stage2_text}

Your task as Chairman is to synthesize all of this information into a single, comprehensive, accurate answer to the user's original question. Consider:
- The individual responses and their insights
- The peer rankings and what they reveal about response quality
- Any patterns of agreement or disagreement
{write_instruction}
Provide a clear, well-reasoned final answer that represents the council's collective wisdom:"""

    messages = [format_user_message(chairman_prompt, attachments)]

    # Query the chairman model
    response = await query_model(chairman, messages)

    if response is None:
        # Fallback: use top-ranked Stage 1 answer if chairman fails
        if stage1_results:
            # Pick the top-ranked answer if aggregate rankings exist
            top_result = stage1_results[0]
            return {
                "model": top_result["model"],
                "response": top_result.get("response", ""),
                "fallback": "chairman_failed",
                "note": "Chairman model failed; showing top Stage 1 response as fallback."
            }
        return {
            "model": chairman,
            "response": "Error: Unable to generate final synthesis.",
            "fallback": "chairman_failed"
        }

    result = {
        "model": chairman,
        "response": response.get('content', '')
    }

    # Parse proposed writes from chairman response
    if allow_writes and mounted_paths:
        proposed = _parse_proposed_writes(result["response"])
        if proposed:
            result["proposed_writes"] = proposed

    return result


def _parse_proposed_writes(response_text: str) -> List[Dict[str, Any]]:
    """Extract proposed_writes JSON block from chairman response."""
    import json
    import re

    match = re.search(r'```proposed_writes\s*\n(.*?)\n```', response_text, re.DOTALL)
    if match:
        try:
            writes = json.loads(match.group(1))
            if isinstance(writes, list):
                return [w for w in writes if isinstance(w, dict) and 'path' in w and 'content' in w]
        except json.JSONDecodeError:
            pass
    return []


def parse_ranking_from_text(ranking_text: str) -> List[str]:
    """
    Parse the FINAL RANKING section from the model's response.

    Args:
        ranking_text: The full text response from the model

    Returns:
        List of response labels in ranked order
    """
    import re

    # Look for "FINAL RANKING:" section
    if "FINAL RANKING:" in ranking_text:
        # Extract everything after "FINAL RANKING:"
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            ranking_section = parts[1]
            # Try to extract numbered list format (e.g., "1. Response A")
            # This pattern looks for: number, period, optional space, "Response X"
            numbered_matches = re.findall(r'\d+\.\s*Response [A-Z]', ranking_section)
            if numbered_matches:
                # Extract just the "Response X" part
                return [re.search(r'Response [A-Z]', m).group() for m in numbered_matches]

            # Fallback: Extract all "Response X" patterns in order
            matches = re.findall(r'Response [A-Z]', ranking_section)
            return matches

    # Fallback: try to find any "Response X" patterns in order
    matches = re.findall(r'Response [A-Z]', ranking_text)
    return matches


def calculate_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str]
) -> List[Dict[str, Any]]:
    """
    Calculate aggregate rankings across all models.

    Args:
        stage2_results: Rankings from each model
        label_to_model: Mapping from anonymous labels to model names

    Returns:
        List of dicts with model name and average rank, sorted best to worst
    """
    from collections import defaultdict

    # Track positions for each model
    model_positions = defaultdict(list)

    for ranking in stage2_results:
        ranking_text = ranking['ranking']

        # Parse the ranking from the structured format
        parsed_ranking = parse_ranking_from_text(ranking_text)

        for position, label in enumerate(parsed_ranking, start=1):
            if label in label_to_model:
                model_name = label_to_model[label]
                model_positions[model_name].append(position)

    # Calculate average position for each model
    aggregate = []
    for model, positions in model_positions.items():
        if positions:
            avg_rank = sum(positions) / len(positions)
            aggregate.append({
                "model": model,
                "average_rank": round(avg_rank, 2),
                "rankings_count": len(positions)
            })

    # Sort by average rank (lower is better)
    aggregate.sort(key=lambda x: x['average_rank'])

    return aggregate


async def generate_conversation_title(user_query: str) -> str:
    """
    Generate a short title for a conversation based on the first user message.

    Args:
        user_query: The first user message

    Returns:
        A short title (3-5 words)
    """
    title_prompt = f"""Generate a very short title (3-5 words maximum) that summarizes the following question.
The title should be concise and descriptive. Do not use quotes or punctuation in the title.

Question: {user_query}

Title:"""

    messages = [{"role": "user", "content": title_prompt}]

    # Use gemini-2.5-flash for title generation (fast and cheap)
    response = await query_model("google/gemini-2.5-flash", messages, timeout=30.0)

    if response is None:
        # Fallback to a generic title
        return "New Conversation"

    title = response.get('content', 'New Conversation').strip()

    # Clean up the title - remove quotes, limit length
    title = title.strip('"\'')

    # Truncate if too long
    if len(title) > 50:
        title = title[:47] + "..."

    return title


async def run_full_council(
    user_query: str,
    council_models: Optional[List[str]] = None,
    chairman_model: Optional[str] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
    mounted_paths: Optional[List[str]] = None,
    allow_writes: bool = False
) -> Tuple[List, List, Dict, Dict]:
    """
    Run the complete 3-stage council process.

    Args:
        user_query: The user's question
        council_models: Optional list of council model IDs
        chairman_model: Optional chairman model ID
        attachments: Optional list of file/image attachments for multimodal queries

    Returns:
        Tuple of (stage1_results, stage2_results, stage3_result, metadata)
    """
    # Stage 1: Collect individual responses
    stage1_results = await stage1_collect_responses(user_query, models=council_models, attachments=attachments, mounted_paths=mounted_paths)

    # If no models responded successfully, return error
    if not stage1_results:
        return [], [], {
            "model": "error",
            "response": "All models failed to respond. Please try again."
        }, {}

    # Stage 2: Collect rankings
    stage2_results, label_to_model = await stage2_collect_rankings(
        user_query, stage1_results, models=council_models, attachments=attachments, mounted_paths=mounted_paths
    )

    # Calculate aggregate rankings
    aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)

    # Stage 3: Synthesize final answer
    stage3_result = await stage3_synthesize_final(
        user_query,
        stage1_results,
        stage2_results,
        chairman_model=chairman_model,
        attachments=attachments,
        mounted_paths=mounted_paths,
        allow_writes=allow_writes
    )

    # Prepare metadata
    metadata = {
        "label_to_model": label_to_model,
        "aggregate_rankings": aggregate_rankings
    }

    return stage1_results, stage2_results, stage3_result, metadata