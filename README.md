# Agent Hooks

`agent-hooks` has two high-level goals:

1. Provide a FastAPI-like framework for building hook callbacks for AI coding tools such as Claude Code, Codex, and Gemini CLI.
2. Provide an out-of-the-box CLI app so a user can install the package with `uv tool install agent-hooks` and set `agent-hooks callback` as the hook callback command. The built-in app shows AppleScript dialogs on macOS for permission prompts.
3. Provide a CLI runner for custom hook apps with `agent-hooks run`, using either FastAPI-style file discovery or uvicorn-style import strings.

## Package layout

Framework code lives at the first package level under `agent_hooks/`.

- `agent_hooks/router.py`: FastAPI-like decorator router such as `@app.permission()`.
- `agent_hooks/middleware.py`: Middleware pipeline used by router dispatch and provider-specific behavior.
- `agent_hooks/runner.py`: Generic callback runtime for loading and executing a router or handler.
- `agent_hooks/models.py`: Core, provider-neutral response and payload models. Provider-specific raw fields remain under `payload.raw`.
- `agent_hooks/providers/`: Provider-specific adapters, payload detection, presentation, permission-response mapping, and optional middlewares, organized into `claude_code/` and `codex/` subpackages.
- `agent_hooks/processor.py`: Default processing flow that delegates provider-owned behavior through the selected adapter.

The built-in CLI app lives under `agent_hooks/cli_app/`.

- `agent_hooks/cli_app/app.py`: Built-in AppleScript-backed app instance with explicit decorator routes for notification, permission, stop, and stop-failure events.
- `agent_hooks/cli_app/cli.py`: CLI entrypoint for `agent-hooks callback` and `agent-hooks run`.
- `agent_hooks/__main__.py`: Thin module entrypoint that exposes the built-in CLI app.

## Install

```bash
uv tool install agent-hooks
```

After installation, configure your AI coding tool to invoke:

```bash
agent-hooks callback
```

Select the hook protocol provider with either `--provider` or `AGENT_HOOK_PROVIDER`:

```bash
agent-hooks callback --provider codex
```

```bash
AGENT_HOOK_PROVIDER=claude-code agent-hooks callback
```

The built-in CLI app is intended to work out of the box on macOS by showing AppleScript dialogs for permission requests.
For Codex `PreToolUse` Bash commands, it first runs `codex execpolicy check -c model="5.4-mini" --rules ~/.codex/rules/default.rules -- <command ...>`.
If the top-level `decision` is `allow`, the hook auto-approves and skips the dialog. You can override the binary, model, or rules path with `AGENT_HOOK_CODEX_EXECPOLICY_BINARY`, `AGENT_HOOK_CODEX_EXECPOLICY_MODEL`, and `AGENT_HOOK_CODEX_EXECPOLICY_RULES`.

To run your own hook app from the CLI, you can either point at a Python file:

```bash
agent-hooks run main.py
```

Or use an explicit import string with an app directory, similar to uvicorn:

```bash
agent-hooks run main:app --app-dir .
```

Both CLI entrypoints accept `--provider claude-code|codex`.

## Framework usage

Create your own hook app with a FastAPI-like interface:

```python
from __future__ import annotations

from agent_hooks import AgentHook, HookProvider, PermissionRequestEvent, build_permission_response
from agent_hooks.enums import DialogButton

app = AgentHook(provider=HookProvider.CODEX)


@app.permission()
def permission_handler(hook_event: PermissionRequestEvent):
    return build_permission_response(DialogButton.ALLOW_ONCE, hook_event)
```

You can execute a callback against a router instance directly:

```python
from agent_hooks.runner import run_callback

run_callback(app)
```

Or load it by module path:

```python
from agent_hooks.runner import run_callback

run_callback("my_hooks:app")
```

The CLI `run` command supports the same import-string style:

```bash
agent-hooks run my_hooks:app --app-dir .
```

The normalized router model is provider-neutral. For example, Claude `PermissionRequest` and Codex `PreToolUse` both route through `@app.permission()`.

Any custom response model is acceptable as long as it fits the hook response protocol: it must expose `suppress_output`, `hook_specific_output`, and `as_payload()`.

## Built-in CLI app

The built-in app is exposed from `agent_hooks.cli_app.app` as:

- `app`

The built-in CLI uses `cli_app.app:app` as its default callback target, and that app is implemented with explicit route decorators rather than router fallback.
