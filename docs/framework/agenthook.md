# AgentHook

`AgentHook` is the core router type for custom callback apps.

It provides a decorator-based API for registering hook handlers while keeping the provider-specific parsing and response rendering below the app layer.

## Minimal Example

```python
from __future__ import annotations

from agent_hooks import AgentHook, HookProvider, PermissionRequestEvent, build_permission_response
from agent_hooks.enums import DialogButton

app = AgentHook(provider=HookProvider.CODEX)


@app.permission()
def permission_handler(hook_event: PermissionRequestEvent):
    return build_permission_response(DialogButton.ALLOW_ONCE, hook_event)
```

## Running The Router

Directly:

```python
from agent_hooks.runner import run_callback

run_callback(app)
```

Through the CLI:

```bash
agent-hooks run my_hooks:app --app-dir . --provider codex
```

## Route Decorators

`AgentHook` exposes the following route decorators:

- `notification()`
- `permission()`
- `pre_tool_use()`
- `session_start()`
- `user_prompt_submit()`
- `post_tool_use()`
- `stop()`
- `stop_failure()`
- `middleware()`

`pre_tool_use()` is an alias for `permission()`, which keeps Codex `PreToolUse` aligned with the provider-neutral permission event model.

## Fallback Processor

`AgentHook` defaults to `fallback_to_default_processor=True`.

That means:

- if a route is registered, the route runs
- if a route is missing, the default processor can still handle supported built-in behavior

Set `fallback_to_default_processor=False` if you want your router to fully own the events it registers and return empty responses for everything else.

## Provider Default

You can optionally bind a default provider at router construction time:

```python
app = AgentHook(provider=HookProvider.CLAUDE_CODE)
```

That provider becomes the default for parsing and response rendering unless the CLI or runtime config overrides it.
