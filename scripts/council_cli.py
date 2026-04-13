#!/usr/bin/env python3
"""
LLM Council CLI Interface

Allows interacting with the LLM Council backend from the command line,
useful for integration with tools like Claude Code slash commands.

Usage:
    python3 council_cli.py "Why is this code failing?" --files src/main.py src/utils.py

Requires the FastAPI backend to be running on localhost:8001.
"""

import argparse
import sys
import os
import json
import httpx
from typing import Optional

API_BASE = "http://localhost:8001/api"


def create_conversation() -> str:
    """Create a new conversation and return its ID."""
    try:
        response = httpx.post(f"{API_BASE}/conversations", json={}, timeout=30.0)
        response.raise_for_status()
        return response.json()["id"]
    except Exception as e:
        print(f"Error creating conversation: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Consult the LLM Council")
    parser.add_argument("query", help="The question for the council")
    parser.add_argument("--files", nargs="*", help="List of files to attach as context")
    parser.add_argument("--conversation-id", help="Continue an existing conversation")

    args = parser.parse_args()

    # 1. Setup conversation
    conversation_id = args.conversation_id
    if not conversation_id:
        conversation_id = create_conversation()
        print(f"Created conversation: {conversation_id}", file=sys.stderr)

    # 2. Send message stream
    payload = {"content": args.query}

    if args.files:
        import base64
        import mimetypes
        attachments = []
        for filepath in args.files:
            try:
                with open(filepath, 'rb') as f:
                    file_data = base64.b64encode(f.read()).decode('utf-8')
                mime_type = mimetypes.guess_type(filepath)[0] or 'application/octet-stream'
                is_image = mime_type.startswith('image/')
                attachments.append({
                    "filename": os.path.basename(filepath),
                    "mimeType": mime_type,
                    "data": f"data:{mime_type};base64,{file_data}",
                    "type": "image" if is_image else "file",
                })
            except FileNotFoundError:
                print(f"Warning: File not found: {filepath}", file=sys.stderr)
            except IOError as e:
                print(f"Warning: Could not read file {filepath}: {e}", file=sys.stderr)
        if attachments:
            payload["attachments"] = attachments

    print("\n--- Consulting the Council ---\n")

    try:
        url = f"{API_BASE}/conversations/{conversation_id}/message/stream"

        with httpx.stream("POST", url, json=payload, timeout=httpx.Timeout(connect=30.0, read=None, write=30.0, pool=30.0)) as response:
            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    if line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            event = json.loads(data_str)
                            event_type = event.get("type")

                            if event_type == "stage1_start":
                                print("\n[Stage 1] Collecting individual opinions...", end="", flush=True)

                            elif event_type == "stage1_complete":
                                print(" Done.")
                                results = event.get("data", [])
                                for res in results:
                                    print(f"  - {res['model']}")

                            elif event_type == "stage2_start":
                                print("\n[Stage 2] Peer review and ranking...", end="", flush=True)

                            elif event_type == "stage2_complete":
                                print(" Done.")
                                metadata = event.get("metadata", {})
                                rankings = metadata.get("aggregate_rankings", [])
                                if rankings:
                                    print("  Agreed quality ranking:")
                                    for r in rankings:
                                        print(f"    {r['average_rank']}. {r['model']}")

                            elif event_type == "stage3_start":
                                print("\n[Stage 3] Synthesizing final answer...", end="", flush=True)

                            elif event_type == "stage3_complete":
                                print(" Done.\n")
                                result = event.get("data", {})
                                print("=" * 60)
                                print(f"CHAIRMAN'S VERDICT ({result.get('model', 'Unknown')})")
                                print("=" * 60)
                                print(result.get("response", ""))
                                print("\n" + "=" * 60)

                            elif event_type == "title_complete":
                                title = event.get("data", {}).get("title", "")
                                print(f"Conversation titled: {title}", file=sys.stderr)

                            elif event_type == "error":
                                print(f"\nError: {event.get('message')}")

                        except json.JSONDecodeError:
                            pass

    except KeyboardInterrupt:
        print("\nRequest cancelled.")
    except Exception as e:
        print(f"\nError consulting council: {e}")


if __name__ == "__main__":
    main()
