# Middleware

Middleware wraps dispatch around the normalized payload and the selected transport.

## Why It Exists

Middleware is the right place for behavior that should run before route logic, such as:

- auto-allow policy checks
- custom policy enforcement
- telemetry or structured audit capture
- response short-circuiting

## Middleware Order

Agent Hooks runs middleware in this order:

1. provider middleware
2. app middleware registered with `@app.middleware()`
3. the final route dispatch or default processor

That ordering lets provider behavior stay close to protocol details while leaving room for app-level customization.

## Example

```python
from __future__ import annotations

from agent_hooks import AgentHook, HookResponse
from agent_hooks.models import HookProcessingResult

app = AgentHook(fallback_to_default_processor=False)


@app.middleware()
def block_specific_bash(context, call_next):
    if context.payload.tool_name == "Bash" and context.payload.tool_input.command == "rm -rf /":
        return HookProcessingResult(display=None, transport_result=None, response=HookResponse())
    return call_next(context)


@app.permission()
def permission_handler():
    return HookResponse()
```

## Codex Built-in Middleware

The current codebase includes provider middleware for Codex `execpolicy`.

For Codex `PreToolUse` events:

- only `Bash` tool requests are checked
- the command string is tokenized with `shlex.split`
- `codex execpolicy check` is run against the configured rules file
- top-level `allow` short-circuits dispatch and returns an empty response

## Short-Circuiting

Middleware can return a `HookProcessingResult` immediately instead of calling `call_next`.

That is how the built-in Codex policy shortcut avoids opening a dialog for already-allowed commands.

## Limitation

Middleware receives normalized payloads. If you need the full provider raw structure, use `context.payload.raw`.
