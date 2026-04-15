# Custom Apps

Use `agent-hooks run` when the built-in callback behavior is too generic for your workflow.

## Command Shapes

Python file target:

```bash
agent-hooks run main.py --provider claude-code
```

Import string target:

```bash
agent-hooks run main:app --app-dir . --provider codex
```

The import-string form is intentionally close to the style people already know from ASGI tooling.

## Minimal Example

```python
from __future__ import annotations

from agent_hooks import AgentHook, HookResponse, PermissionRequestEvent

app = AgentHook()


@app.permission()
def permission_handler(hook_event: PermissionRequestEvent) -> HookResponse:
    if hook_event.tool_name == "Bash":
        return HookResponse(suppress_output=False)
    return HookResponse()
```

Run it:

```bash
agent-hooks run my_hooks:app --app-dir . --provider claude-code
```

## When To Use A Custom App

- you want provider-specific business logic
- you want custom middleware
- you want different stop behavior
- you want to enrich responses with additional context
- you want to bypass the built-in UI completely

## Callback Target Types

The runner accepts:

- an `AgentHook` instance
- a direct callback handler
- an import string
- a Python file path

## Provider Choice Still Matters

Your custom app still needs either:

- an explicit provider
- a provider in runtime config
- or a payload that can be auto-detected cleanly

Provider selection affects both parsing and response rendering.
