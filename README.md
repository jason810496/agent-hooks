# Agent Hooks

<p align="center">
  <img src="https://www.zhu424.dev/agent-hooks/latest/assets/agent-hooks-landing.svg" alt="Agent Hooks landing graphic" width="100%">
</p>

**No more swipe-and-sweep context switching for multi-session AI coding.**

Agent Hooks gives Claude Code and Codex one local callback layer: a macOS-ready CLI for native permission dialogs and notifications, plus a FastAPI-like framework when you want to own the policy in Python.

## Install

Use the standalone CLI. See the [Built-in CLI](https://www.zhu424.dev/agent-hooks/latest/cli/builtin-callback/) docs for wiring it into your provider config.

```bash
uv tool install agent-hooks
```

Or install it inside a Python project:

```bash
uv pip install agent-hooks
```

## What It Looks Like

### Claude Code

![Claude Code permission request shown as a macOS dialog](https://www.zhu424.dev/agent-hooks/latest/assets/agent-hooks-claude-code-example.png)

Claude Code permission requests become a native local dialog. When Claude offers permission suggestions, each one is rendered as its own choice in a picker (`Allow once` plus one entry per suggestion, shown exactly as Claude sent it) so you persist only the scope you pick; otherwise a `Deny` / `Allow Once` / session-scoped `Always Allow` dialog is shown.

### Codex

![Codex permission request shown as a macOS dialog](https://www.zhu424.dev/agent-hooks/latest/assets/agent-hooks-codex-example.png)

Codex `PreToolUse` requests become the same local dialog flow, with `Deny`, `Allow Once`, and optional `execpolicy` short-circuiting for already-allowed Bash commands.

### `AgentHook` Framework

```python
from agent_hooks import AgentHook, PermissionRequestEvent, build_permission_response
from agent_hooks.enums import DialogButton

app = AgentHook()


@app.permission()
def permission_handler(hook_event: PermissionRequestEvent):
    if hook_event.tool_name == "Bash":
        return build_permission_response(DialogButton.ALLOW_ONCE, hook_event)
    return build_permission_response(DialogButton.DENY, hook_event)
```

```bash
agent-hooks run my_hooks.py --provider codex
```

A single typed handler can serve Claude Code's `PermissionRequest` and Codex's `PreToolUse` without requiring provider-specific schema glue.

You can also factor reusable route inputs with one-level dependencies:

```python
from agent_hooks import CallbackRequest, Depends


def build_command(request: CallbackRequest) -> str:
    return request.payload.tool_input.command


@app.permission()
def permission_handler(command: str = Depends(build_command)):
    ...
```

Yield-based dependencies are also supported for scoped resources:

```python
def get_db():
    db = connect_db()
    try:
        yield db
    finally:
        db.close()


@app.permission()
def permission_handler(db = Depends(get_db)):
    ...
```

## Why It Exists

Multi-session AI coding tends to break flow in the same places:

- permission prompts appear in separate sessions
- provider payloads differ
- local hook responses need provider-specific wire shapes
- stop and notification events want OS-local behavior, not more terminal noise

Agent Hooks normalizes those problems into one package.

## Two Products In One Package

Use `agent-hooks callback` when you want a working local callback target immediately.

Use `AgentHook` when you need to define custom permission, notification, or stop behavior in Python.

### Built-in CLI

The built-in app is exposed as `app.builtin:app` and can be run with:

```bash
agent-hooks callback
```

This path is designed for local-first usage on macOS:

- permission dialogs
- notifications
- provider-aware response rendering
- rotating logs and audit logs

### Framework

The framework is centered on `AgentHook`, a decorator-based router that looks and feels closer to FastAPI than to handwritten hook glue.

You register handlers with route decorators such as:

- `@app.notification()`
- `@app.permission()`
- `@app.session_start()`
- `@app.user_prompt_submit()`
- `@app.post_tool_use()`
- `@app.stop()`
- `@app.stop_failure()`

## Provider-Neutral Core

Internally, incoming payloads are normalized into shared models before dispatch. That gives you one app-level programming model even when providers use different raw event names.

Examples:

- Claude `PermissionRequest` and Codex `PreToolUse` both route through `@app.permission()`
- both providers share the same `HookPayload` base model
- provider-specific response wire formats are handled by adapters

## Start Here

If you want the fastest path, install the tool and wire the built-in callback into your provider config.

### Claude Code

Install the CLI:

```bash
uv tool install agent-hooks
```

Put this in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PermissionRequest": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "agent-hooks callback --provider claude-code"
          }
        ]
      }
    ],
    "Notification": [
      {
        "matcher": "permission_prompt",
        "hooks": [
          {
            "type": "command",
            "command": "agent-hooks callback --provider claude-code"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "agent-hooks callback --provider claude-code"
          }
        ]
      }
    ],
    "StopFailure": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "agent-hooks callback --provider claude-code"
          }
        ]
      }
    ]
  }
}
```

This is enough to route Claude Code permission, notification, and stop events into the built-in callback.

### Codex

Install the CLI:

```bash
uv tool install agent-hooks
```

If your Codex build still requires the feature flag, add this to `~/.codex/config.toml`:

```toml
[features]
codex_hooks = true
```

Put this in `~/.codex/hooks.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "agent-hooks callback --provider codex",
            "timeout": 30
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "agent-hooks callback --provider codex",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

This is enough to route Codex Bash permission checks and stop notifications into the built-in callback.

Recommended setup: pass `--provider` explicitly in your provider config when you can. The built-in callback can infer providers from payload markers, but the explicit flag keeps local setup easier to reason about and debug.

If you want to build your own hook app, start with [`AgentHook`](https://www.zhu424.dev/agent-hooks/latest/framework/agenthook/) and then run it with [`agent-hooks run`](https://www.zhu424.dev/agent-hooks/latest/cli/custom-apps/).

## Docs Map

- [Features](https://www.zhu424.dev/agent-hooks/latest/features/)
- [macOS Quickstart](https://www.zhu424.dev/agent-hooks/latest/getting-started/macos-quickstart/)
- [Built-in Callback](https://www.zhu424.dev/agent-hooks/latest/cli/builtin-callback/)
- [AgentHook](https://www.zhu424.dev/agent-hooks/latest/framework/agenthook/)
- [Architecture Overview](https://www.zhu424.dev/agent-hooks/latest/architecture/overview/)
- [Claude Code](https://www.zhu424.dev/agent-hooks/latest/providers/claude-code/)
- [Codex](https://www.zhu424.dev/agent-hooks/latest/providers/codex/)

## Maintainers

- [Release Process](https://github.com/jason810496/agent-hooks/blob/main/scripts/release/README.md)

## Scope

Agent Hooks currently supports only two providers:

- Claude Code
- Codex

The docs stay aligned with the current implementation. They describe supported behavior that exists today, not placeholder integrations for future providers.

## License

Agent Hooks is licensed under Apache 2.0. See [LICENSE](https://github.com/jason810496/agent-hooks/blob/main/LICENSE).
