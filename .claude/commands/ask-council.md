```bash
---
description: Consult the LLM Council for a second opinion on complex problems
argument-hint:
---

# Consult the LLM Council

You are invoking the LLM Council - a multi-model deliberation system that provides expert second opinions on complex problems.

## User's Query

$ARGUMENTS

## Your Task

1. **Analyze the user's query** and identify relevant files in the codebase
2. **Construct a comprehensive council request** following the guidelines below
3. **Execute the council CLI** with the appropriate files
4. **Wait for the Chairman's Verdict** before proceeding
5. **Print the FULL council response** to the user (do not summarize or truncate)
6. **Ask user for confirmation** before implementing any suggested changes

## Execution Command

Run the council CLI using `python3` with **absolute paths**:

```bash
python3 scripts/council_cli.py "CONSTRUCTED_QUERY" --files /absolute/path/to/project/file1 /absolute/path/to/project/file2
```

**IMPORTANT**:
- Use `python3` (or the project venv python)
- Always use the full absolute path prefix for all files
- Set a timeout of at least 180000ms (3 minutes) as the council process takes time
- The backend must be running on localhost:8001

## Query Construction Guidelines

When constructing the query for the council, you **MUST**:

### 1. Be Generous with Context
- **Identify and include** all relevant code files in the `--files` argument
- Search the codebase to find files related to the user's problem
- Include config files if relevant to the error

### 2. Explain the History
- Include any context from the conversation about what has been tried
- Mention any error messages or unexpected behavior
- "Tried approach X but got error Y. Then tried Z but it caused W."

### 3. Frame the Question Clearly
- State the user's suspicions if mentioned
- Explicitly note openness to alternative approaches
- "However, open to any new impulses or radically different approaches."

## Understanding the Council Process

The Council triggers a 3-Stage Process (takes 20-40 seconds):

1. **Stage 1 - Exploration**: Multiple LLMs analyze the problem independently
2. **Stage 2 - Peer Review**: Models blindly review and rank each other's solutions
3. **Stage 3 - Synthesis**: The "Chairman" composes a final authoritative answer

## After Council Response

**MANDATORY - NO EXCEPTIONS**:

You MUST pass through the COMPLETE, UNALTERED council response to the user. This is non-negotiable.

### What you MUST do:
- Print the ENTIRE "CHAIRMAN'S VERDICT" section verbatim
- Include ALL markdown content, code examples, tables, and recommendations
- Preserve the EXACT formatting as received from the council
- Show EVERYTHING - every single line of the response
- Then use the full response for your further work on the topic

### What you MUST NOT do:
- DO NOT summarize the council's response
- DO NOT paraphrase or reword any part of it
- DO NOT truncate or shorten the response
- DO NOT add your own interpretation before showing the full response
- DO NOT say "here are the key points" or "in summary"

### Why this matters:

The user is consulting the LLM Council specifically to get a SECOND OPINION from multiple AI models. Your job is to be a transparent conduit - pass the council's advice through COMPLETELY so the user receives the full benefit of the multi-model deliberation. Any summarization defeats the purpose of consulting the council.

### After printing the full response:

1. Ask the user what they would like to do next
2. Wait for user confirmation before implementing any suggested changes

## Example Query Construction

If user asks: "Why is my login returning 422?"

Construct query like:

```
"I am trying to fix the '422 Unprocessable Entity' error in the login flow.

CONTEXT:
[Include relevant conversation history]

SUSPICION:
[Include user's theories if any]

Please review the attached files and suggest a fix or debugging strategy. Open to refactoring if the approach is flawed."
```

Then execute with relevant files (using absolute paths):

```bash
python3 scripts/council_cli.py "..." --files /absolute/path/to/project/src/auth/login.py /absolute/path/to/project/src/auth/service.py
```
