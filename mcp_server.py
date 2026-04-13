"""Entry point for MCP server mode."""

import os
import sys
import argparse


def main():
    # Parse custom arguments
    # We use parse_known_args so that standard MCP arguments (like transport settings)
    # are preserved for mcp.run() to handle.
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--council-models", help="Comma-separated list of OpenRouter models for the council")
    parser.add_argument("--chairman-model", help="OpenRouter model for the chairman")
    args, remaining_argv = parser.parse_known_args()

    # Inject into environment variables BEFORE importing backend
    # This ensures backend.config reads these values during initialization
    if args.council_models:
        os.environ["COUNCIL_MODELS"] = args.council_models
    if args.chairman_model:
        os.environ["CHAIRMAN_MODEL"] = args.chairman_model

    # Reconstruct sys.argv without our custom args so FastMCP doesn't get confused
    sys.argv = [sys.argv[0]] + remaining_argv

    # Now import the app (which triggers config loading)
    from backend.mcp import mcp

    # Run the server
    mcp.run()


if __name__ == "__main__":
    main()
