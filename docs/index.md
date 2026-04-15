# Agent Hooks

No more swipe-and-sweep context switching for multi-session AI coding.

Agent Hooks gives Claude Code and Codex one local callback layer. You get a macOS-ready callback CLI out of the box, plus a FastAPI-like `AgentHook` framework when you need custom behavior.

- Support both `claude-code` and `codex`
- Keep hook UX local on macOS with the system `osascript` binary
- Build custom apps with decorator routes such as `@app.permission()`
- Avoid runtime Python package dependencies in the library itself
- Keep raw inputs, rendered outputs, and app logs under one local logging model

## Start Here

If you want the fastest path, install the tool and point your provider at the built-in callback command:

```bash
uv tool install agent-hooks
```

```bash
agent-hooks callback --provider claude-code
```

```bash
agent-hooks callback --provider codex
```

If you want to build your own hook app, start with [AgentHook](framework/agenthook.md) and then run it with [`agent-hooks run`](cli/custom-apps.md).

## Docs Map

- [Overview](overview.md): what Agent Hooks is and how the package is split
- [Features](features.md): what the project does today
- [macOS Quickstart](getting-started/macos-quickstart.md): install, wire up, and smoke-test the built-in callback
- [Built-in Callback](cli/builtin-callback.md): the out-of-box CLI behavior
- [AgentHook](framework/agenthook.md): the callback framework
- [Architecture Overview](architecture/overview.md): end-to-end callback flow
- [Claude Code](providers/claude-code.md) and [Codex](providers/codex.md): provider-specific implementation details and limitations

## Scope

Agent Hooks currently supports only two providers:

- Claude Code
- Codex

The docs intentionally stay aligned with the current implementation rather than promising future providers.
