# Features

## Strong Defaults

- One installable CLI command, `agent-hooks`
- One built-in callback target, `agent-hooks callback`
- One custom-app runner, `agent-hooks run`
- One normalized event model across supported providers

## macOS-Ready Out of the Box

- Uses the system `osascript` binary for dialogs and notifications
- Requires no extra native package manager installs on macOS
- Skips AppleScript execution cleanly on unsupported platforms or when disabled

## Provider Support

- Claude Code support
- Codex support
- Provider auto-detection when payload markers are available
- Explicit provider selection with `--provider` or `AGENT_HOOK_PROVIDER`

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

## Logging and Auditability

- Rotating application log
- Raw input audit log
- Rendered response audit log
- Configurable log file paths, sizes, and backup counts

## Packaging

- Zero runtime Python package dependencies
- Docs dependencies isolated into a dedicated `docs` dependency group
- Apache 2.0 licensed
