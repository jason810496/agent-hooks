# macOS Quickstart

This guide is for the out-of-box path: install Agent Hooks, point your provider at the built-in callback command, and verify that the local callback loop works on macOS.

## Prerequisites

- macOS
- `uv`
- Claude Code or Codex

## Install

```bash
uv tool install agent-hooks
```

If you are working from the repository instead of the published tool, you can also run the package through `uv run`, but the documented default is the installable CLI.

## Wire Up The Built-in Callback

Use one of the following callback commands in your provider config.

Claude Code:

```bash
agent-hooks callback --provider claude-code
```

Codex:

```bash
agent-hooks callback --provider codex
```

You can also keep the callback command generic and select the provider through the environment:

```bash
AGENT_HOOK_PROVIDER=claude-code agent-hooks callback
```

## Smoke Test The Callback Locally

Claude-style permission request:

```bash
printf '%s\n' '{"hook_event_name":"PermissionRequest","tool_name":"Bash","tool_input":{"command":"git status"}}' | agent-hooks callback --provider claude-code
```

Codex-style pre-tool-use request:

```bash
printf '%s\n' '{"hook_event_name":"PreToolUse","cwd":"/tmp/project","model":"gpt-5.4","permission_mode":"default","session_id":"session-1","tool_input":{"command":"git status"},"tool_name":"Bash","tool_use_id":"tool-1","transcript_path":null,"turn_id":"turn-1"}' | agent-hooks callback --provider codex
```

## Disable AppleScript Temporarily

If you want to test parsing and rendering without opening dialogs or notifications:

```bash
AGENT_HOOK_DISABLE_OSASCRIPT=1 agent-hooks callback --provider codex
```

Accepted truthy values include `1`, `true`, `yes`, and `on`.

## What To Expect

- macOS permission events open a dialog
- stop events can produce notifications
- responses are written to `stdout`
- logs are written under `logs/` by default

If you need custom behavior instead of the built-in app, move on to [Custom Apps](../cli/custom-apps.md).
