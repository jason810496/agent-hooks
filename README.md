# Agent Hooks

<p align="center">
  <img src="docs/assets/agent-hooks-landing.svg" alt="Agent Hooks landing graphic" width="100%">
</p>

**No more swipe-and-sweep context switching for multi-session AI coding.**

Agent Hooks gives Claude Code and Codex one local callback layer: a macOS-ready CLI for native permission dialogs and notifications, plus a FastAPI-like framework when you want to own the policy in Python.

## What It Looks Like

### Claude Code

![Claude Code permission request shown as a macOS dialog](docs/assets/agent-hooks-claude-code-example.png)

Claude Code permission requests become a native local dialog with `Deny`, `Allow Once`, and session-scoped `Always Allow`.

### Codex

![Codex permission request shown as a macOS dialog](docs/assets/agent-hooks-codex-example.png)

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
agent-hooks run my_hooks:app --app-dir . --provider codex
```

One typed handler can serve Claude Code `PermissionRequest` and Codex `PreToolUse` without writing provider-specific schema glue.

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

The built-in app is exposed as `agent_hooks.cli_app.app:app` and run through:

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

If you want to build your own hook app, start with [`AgentHook`](docs/framework/agenthook.md) and then run it with [`agent-hooks run`](docs/cli/custom-apps.md).

## Docs Map

- [Features](docs/features.md)
- [macOS Quickstart](docs/getting-started/macos-quickstart.md)
- [Built-in Callback](docs/cli/builtin-callback.md)
- [AgentHook](docs/framework/agenthook.md)
- [Architecture Overview](docs/architecture/overview.md)
- [Claude Code](docs/providers/claude-code.md)
- [Codex](docs/providers/codex.md)

## Scope

Agent Hooks currently supports only two providers:

- Claude Code
- Codex

The docs stay aligned with the current implementation. They describe supported behavior that exists today, not placeholder integrations for future providers.

## License

Agent Hooks is licensed under Apache 2.0. See [LICENSE](LICENSE).
