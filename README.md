# Agent Hooks

No more swipe-and-sweep context switching for multi-session AI coding.

`agent-hooks` is a local callback layer for Claude Code and Codex. It ships with a macOS-ready callback CLI for permission dialogs and notifications, plus a FastAPI-like `AgentHook` framework for building your own hook apps without carrying a runtime dependency stack.

- One callback command for both Claude Code and Codex
- Out-of-the-box macOS UX via the system `osascript` binary
- Zero runtime Python package dependencies
- Zero extra macOS dependencies beyond what ships with macOS
- FastAPI-like decorator API for hook callback programming
- Open source under Apache 2.0

## Why Agent Hooks

When you run multiple AI coding sessions, the real friction is often local callback handling:

- repeated permission prompts across sessions
- losing focus while jumping between tool UIs and terminals
- provider-specific hook payloads and response formats
- glue code that should be framework work, not app work

Agent Hooks is the pain-killer for that loop. It gives you one local callback entrypoint, one normalized event model, one logging story, and one place to customize behavior when the built-in app is not enough.

## What Ships

`agent-hooks` is really two products in one package:

1. A built-in callback CLI for macOS. Install it with `uv tool install agent-hooks`, point your provider at `agent-hooks callback`, and get local permission dialogs and notifications immediately.
2. A FastAPI-like callback framework centered on `AgentHook`. Use decorator routes such as `@app.permission()` and `@app.stop()` to build your own custom hook app, then run it with `agent-hooks run`.

## 60-Second Quickstart

Install the tool:

```bash
uv tool install agent-hooks
```

Point your provider's hook callback command at the built-in app:

```bash
agent-hooks callback --provider claude-code
```

```bash
agent-hooks callback --provider codex
```

You can also choose the provider with `AGENT_HOOK_PROVIDER`:

```bash
AGENT_HOOK_PROVIDER=codex agent-hooks callback
```

On macOS, the built-in app uses the system `osascript` binary to show dialogs and notifications. There is no extra native dependency or background service to install.

To run your own hook app instead of the built-in one:

```bash
agent-hooks run my_hooks:app --app-dir . --provider codex
```

## Features

- Support for both `claude-code` and `codex`
- Provider auto-detection from incoming payloads when the payload carries provider-specific markers
- Provider-neutral routing where Claude `PermissionRequest` and Codex `PreToolUse` both map to `@app.permission()`
- Typed event injection for notification, permission, session start, user prompt submit, post-tool-use, stop, and stop-failure handlers
- Pluggable middleware with provider middleware and app middleware in the same dispatch chain
- Built-in rotating app logs plus raw input and rendered response audit logs
- Built-in Codex `execpolicy` shortcut so already-allowed Bash commands can skip the dialog round-trip

## Out-of-the-Box CLI

The built-in callback target is `agent_hooks.cli_app.app:app`, and the CLI exposes it as:

```bash
agent-hooks callback
```

`agent-hooks callback` is designed for the "just make it work" path:

- Claude Code gets notification, permission, stop, and stop-failure handling
- Codex gets pre-tool-use permission handling and stop notifications
- Codex `SessionStart`, `UserPromptSubmit`, and `PostToolUse` are already wired in the built-in app and currently return empty responses
- All built-in behavior stays local and writes logs under `logs/` by default

For Codex Bash permission requests, Agent Hooks can auto-allow commands that already match a local rules file by running:

```bash
codex execpolicy check -c model="5.4-mini" --rules ~/.codex/rules/default.rules -- <command ...>
```

If the top-level `decision` is `allow`, the built-in permission dialog is skipped. The current implementation supports:

- `AGENT_HOOK_CODEX_EXECPOLICY_MODEL`
- `AGENT_HOOK_CODEX_EXECPOLICY_RULES`

## `AgentHook` Callback Framework

The framework side is centered on the `AgentHook` router:

```python
from __future__ import annotations

from agent_hooks import AgentHook, HookProvider, PermissionRequestEvent, build_permission_response
from agent_hooks.enums import DialogButton

app = AgentHook(provider=HookProvider.CODEX)


@app.permission()
def permission_handler(hook_event: PermissionRequestEvent):
    return build_permission_response(DialogButton.ALLOW_ONCE, hook_event)
```

Run it directly:

```python
from agent_hooks.runner import run_callback

run_callback(app)
```

Or load it by import string or file path:

```bash
agent-hooks run my_hooks:app --app-dir .
```

```bash
agent-hooks run my_hooks.py --provider claude-code
```

Useful framework properties:

- provider-neutral event normalization
- decorator-based routing
- typed injection for event models, `CallbackRequest`, and `DisplayTransport`
- middleware short-circuiting for provider-specific behavior
- custom response models as long as they expose `suppress_output`, `hook_specific_output`, and `as_payload()`

## How It Works

At a high level, each callback run looks like this:

1. Read hook JSON from `stdin`
2. Infer or select the provider
3. Normalize the raw payload into a shared `HookPayload`
4. Run provider middleware, then app middleware
5. Dispatch to a registered route or the default processor
6. Show macOS UI with `osascript` when needed
7. Render the provider-specific response JSON to `stdout`
8. Write app, input-audit, and response-audit logs

## Provider Support

| Provider | Normalized events | Built-in app behavior | Permission behavior | Notable limits |
| --- | --- | --- | --- | --- |
| Claude Code | `Notification`, `PermissionRequest`, `Stop`, `StopFailure` | Notifications, permission dialogs, stop notifications, stop-failure notifications | `Allow Once`, `Deny`, and session-scoped `Always Allow` when permission suggestions are present | More Claude raw events are detected than the built-in app currently turns into first-class behavior |
| Codex | `SessionStart`, `PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop` | Permission dialogs for `PreToolUse`, notifications for `Stop`, empty responses for `SessionStart`, `UserPromptSubmit`, and `PostToolUse` | `Allow Once` or `Deny`; Bash requests can auto-allow through `execpolicy` | No built-in persistent `Always Allow` path for Codex permission requests |

## Documentation

The repository now includes a dedicated MkDocs site under `docs/` with pages for overview, features, CLI usage, the callback framework, architecture, provider details, configuration, logging, and limitations.

Install docs dependencies and serve the site locally:

```bash
uv sync --group docs
```

```bash
uv run --group docs mkdocs serve
```

Build the static site:

```bash
uv run --group docs mkdocs build --strict
```

## License

Agent Hooks is licensed under Apache 2.0. See [LICENSE](LICENSE).
