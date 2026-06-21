# AgentHook

`AgentHook` is the core router type for custom callback apps.

It provides a decorator-based API for registering hook handlers while keeping provider-specific parsing and response rendering below the app layer.

<p class="ah-lead">
Think "FastAPI for hook callbacks": you implement business logic against typed event objects, and Agent Hooks handles provider payload normalization plus provider-specific response wire shapes.
</p>

<div class="ah-feature-grid">
  <div class="ah-feature-card">
    <h3>Decorator routes</h3>
    <p>Register behavior with handlers like <code>@app.permission()</code>, <code>@app.stop()</code>, and <code>@app.notification()</code>.</p>
  </div>
  <div class="ah-feature-card">
    <h3>Typed event injection</h3>
    <p>Write against <code>PermissionRequestEvent</code>, <code>StopEvent</code>, <code>CallbackRequest</code>, and <code>DisplayTransport</code> instead of raw JSON.</p>
  </div>
  <div class="ah-feature-card">
    <h3>Reusable dependencies</h3>
    <p>Factor shared context into one-level <code>Depends(...)</code> helpers without dropping down to raw payload plumbing.</p>
  </div>
  <div class="ah-feature-card">
    <h3>Unified schema</h3>
    <p>Claude <code>PermissionRequest</code> and Codex <code>PreToolUse</code> both arrive as the same normalized permission event.</p>
  </div>
</div>

## What You Write Vs What Agent Hooks Handles

| You write | Agent Hooks handles |
| --- | --- |
| business rules for allow, deny, notify, or stop behavior | provider detection and payload parsing |
| typed handlers with route decorators | mapping raw provider event names into normalized events |
| generic responses like `HookResponse(...)` | rendering the correct provider response JSON |
| a button choice like `DialogButton.ALLOW_ONCE` | building provider-specific permission payloads |

## Minimal Example

```python
from __future__ import annotations

from agent_hooks import (
    AgentHook,
    HookResponse,
    PermissionRequestEvent,
    StopEvent,
    build_permission_response,
)
from agent_hooks.enums import DialogButton

app = AgentHook()


@app.permission()
def permission_handler(hook_event: PermissionRequestEvent):
    if hook_event.tool_name == "Bash" and hook_event.tool_input.command.startswith("git status"):
        return build_permission_response(DialogButton.ALLOW_ONCE, hook_event)
    return build_permission_response(DialogButton.DENY, hook_event)


@app.stop()
def stop_handler(hook_event: StopEvent) -> HookResponse:
    return HookResponse(
        suppress_output=False,
        system_message=f"Handled locally for {hook_event.provider.value}.",
    )
```

`build_permission_response()` lets you choose the policy outcome once and have Agent Hooks render the right provider-specific permission response. `HookResponse(...)` is the generic top-level response model for non-permission events.

## One-Level Dependencies

You can extract reusable handler inputs with `Depends(...)`:

```python
from agent_hooks import CallbackRequest, Depends


def build_command(request: CallbackRequest) -> str:
    return request.payload.tool_input.command


@app.permission()
def permission_handler(command: str = Depends(build_command)):
    ...
```

Dependency callables can receive the same built-in injections as route handlers, but nested dependencies are not supported.

Yield-based dependencies are also supported for resource lifecycles. If a dependency yields one value, that value is injected and the generator is resumed for cleanup after the handler completes.

## Running The Router

Directly:

```python
from agent_hooks.runner import run_callback

run_callback(app)
```

Through the CLI:

```bash
agent-hooks run my_hooks.py --app-dir . --provider codex
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

## Response Primitives

Out-of-the-box response building is intentionally small and typed:

- `HookResponse` for generic top-level response fields such as `continue_`, `stop_reason`, `system_message`, `decision`, and `reason`
- `build_permission_response(DialogButton, hook_event)` when you want Agent Hooks to generate the correct provider-specific permission payload
- `AppleScriptDialogResponse` as the concrete normalized permission-response model returned by `build_permission_response()`

## Fallback Handler

`AgentHook` defaults to `fallback_handler=DefaultHookHandler()`.

That means:

- if a route is registered, the route runs
- if a route is missing, the default fallback handler can still handle supported built-in behavior

Set `fallback_handler=None` if you want your router to fully own the events it registers and return empty responses for everything else.

You can also pass your own fallback handler object:

```python
from agent_hooks import AgentHook, DefaultHookHandler

app = AgentHook(fallback_handler=DefaultHookHandler())
```

## Provider Default

You can optionally bind a default provider at router construction time:

```python
app = AgentHook(provider=HookProvider.CLAUDE_CODE)
```

That provider becomes the default for parsing and response rendering unless the CLI or runtime config overrides it.
