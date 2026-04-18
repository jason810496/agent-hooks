# Features

## Strong Defaults

- One installable CLI command, `agent-hooks`
- One built-in callback target, `agent-hooks callback`
- One custom-app runner, `agent-hooks run`
- One normalized event model across supported providers

!!! note "Why this matters"
    **The package is optimized for local-first setup.** You can start with the built-in callback, then move to a custom `AgentHook` app only when you actually need custom routing or provider-specific logic.

## macOS-Ready Out of the Box

- Uses the system `osascript` binary for dialogs and notifications
- Requires no extra native package manager installs on macOS
- Skips AppleScript execution cleanly on unsupported platforms or when disabled

## Provider Support

- Claude Code support
- Codex support
- Provider auto-detection when payload markers are available
- Explicit provider selection with `--provider` or `AGENT_HOOK_PROVIDER`

!!! tip "Recommended"
    **Prefer explicit provider selection** for real setups. Auto-detection is convenient, but `--provider` or `AGENT_HOOK_PROVIDER` makes callback behavior more predictable.

## Framework Ergonomics

- FastAPI-like decorator routes
- Typed event models per route
- Injection for `CallbackRequest` and `DisplayTransport`
- Custom response models supported when they satisfy the response protocol
- Middleware support for short-circuiting or augmenting dispatch

## Built-in Behavior

- Claude notifications and permission dialogs
- Claude stop and stop-failure notifications
- Codex pre-tool-use permission dialogs
- Codex stop notifications
- Codex `execpolicy` shortcut for already-allowed Bash commands

!!! info "Built-in behavior is intentionally narrow"
    The built-in app handles the most useful local workflows first: **permission prompts, notifications, and safe short-circuiting for allowed Codex Bash commands**. If you need richer automation, use the framework layer.

## Logging and Auditability

- Rotating application log
- Raw input audit log
- Rendered response audit log
- Configurable log file paths, sizes, and backup counts

!!! note "Operational visibility"
    **Every callback run can be audited locally.** This is useful when you need to verify what the provider sent, what the callback rendered, and why a dialog or response looked the way it did.

## Packaging

- Zero runtime Python package dependencies
- Docs dependencies isolated into a dedicated `docs` dependency group
- Apache 2.0 licensed
