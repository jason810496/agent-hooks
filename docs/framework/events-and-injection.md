# Events And Injection

Each route decorator maps to a typed event model. The router then injects values into your handler based on parameter annotations.

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
