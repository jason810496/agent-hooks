# Events And Injection

Each route decorator maps to a typed event model. The router then injects values into your handler based on parameter annotations.

<p class="ah-lead">
This is the layer that removes provider schema churn. You write one handler against normalized types and Agent Hooks feeds it the right data whether the raw callback came from Claude Code or Codex.
</p>

## Event Models

Common base model:

- `HookEvent`

Route-specific models:

- `NotificationEvent`
- `PermissionRequestEvent`
- `SessionStartEvent`
- `UserPromptSubmitEvent`
- `PostToolUseEvent`
- `StopEvent`
- `StopFailureEvent`

## Injection Types

The router can inject these values by annotation:

- the route's event model
- `CallbackRequest`
- `DisplayTransport`

Example:

```python
from __future__ import annotations

from agent_hooks import CallbackRequest, PermissionRequestEvent
from agent_hooks.transport import DisplayTransport


@app.permission()
def permission_handler(
    hook_event: PermissionRequestEvent,
    request: CallbackRequest,
    transport: DisplayTransport,
):
    ...
```

## Normalized Event Mapping

The key abstraction is the normalized event layer.

- Claude `PermissionRequest` becomes `PermissionRequest`
- Codex `PreToolUse` also becomes `PermissionRequest`
- Codex `SessionStart`, `UserPromptSubmit`, `PostToolUse`, and `Stop` keep their own normalized event names

That is why one handler can serve both providers when the semantics line up.

| Raw provider event | Normalized event | Decorator | Injected model |
| --- | --- | --- | --- |
| Claude `PermissionRequest` | `PermissionRequest` | `@app.permission()` | `PermissionRequestEvent` |
| Codex `PreToolUse` | `PermissionRequest` | `@app.permission()` or `@app.pre_tool_use()` | `PermissionRequestEvent` |
| Claude `Notification` | `Notification` | `@app.notification()` | `NotificationEvent` |
| Codex `Stop` | `Stop` | `@app.stop()` | `StopEvent` |

## What The Event Models Give You

Examples of common fields:

- `provider`
- `event_name`
- `raw_event_name`
- `model`
- `session_id`
- `cwd`
- `transcript_path`
- `raw`

Examples of route-specific fields:

- notification handlers get `raw_notification_type`, `title`, and `message`
- permission handlers get `permission_mode`, `prompt`, `tool_name`, `tool_use_id`, and `tool_input`
- stop-failure handlers get `error_details` and `error`

## Handler Validation

Required parameters must be injectable. If you declare an unsupported required parameter, route registration fails with a `ValueError`.

Optional parameters with defaults are allowed and left alone.

## Response Objects Pair With Injection

The injected event models are designed to pair with the built-in response helpers:

- return `HookResponse(...)` when you want to control generic top-level callback output
- return `build_permission_response(DialogButton, hook_event)` when the handler is deciding a permission request
- inspect `request.payload.raw` only when you truly need provider-specific details outside the normalized surface
