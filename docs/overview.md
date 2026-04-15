# Overview

Agent Hooks is a local hook callback package with two layers:

1. A built-in callback CLI for users who want a working local callback target immediately.
2. A callback framework for users who want to program their own hook behavior.

## Why It Exists

Multi-session AI coding tends to break flow in the same places:

- permission prompts appear in separate sessions
- provider payloads differ
- local hook responses need provider-specific wire shapes
- stop and notification events want OS-local behavior, not more terminal noise

Agent Hooks normalizes those problems into one package.

## Two Products in One Package

## Built-in CLI

The built-in app is exposed as `agent_hooks.cli_app.app:app` and run through:

```bash
agent-hooks callback
```

This path is designed for local-first usage on macOS:

- permission dialogs
- notifications
- provider-aware response rendering
- rotating logs and audit logs

## Framework

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

## Current Provider Scope

Agent Hooks currently supports:

- `claude-code`
- `codex`

Anything beyond those two providers is out of scope for the current codebase and docs set.
