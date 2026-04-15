# Built-in Callback

The built-in callback command is:

```bash
agent-hooks callback
```

It resolves to the built-in app instance at `agent_hooks.cli_app.app:app`.

## Provider Selection

The built-in callback can determine its provider in three ways:

1. an explicit `--provider` CLI argument
2. `AGENT_HOOK_PROVIDER`
3. provider inference from the incoming payload when the payload has unique markers

If you know which provider is calling the hook, using `--provider` keeps the setup explicit.

## Built-in Event Behavior

## Claude Code

The built-in app handles:

- `Notification`
- `PermissionRequest`
- `Stop`
- `StopFailure`

Those events are rendered into local notifications or dialogs when appropriate.

## Codex

The built-in app registers:

- `SessionStart`
- `PreToolUse`
- `PostToolUse`
- `UserPromptSubmit`
- `Stop`

Current built-in behavior is intentionally narrow:

- `PreToolUse` gets permission dialogs
- `Stop` gets notifications
- `SessionStart`, `PostToolUse`, and `UserPromptSubmit` return empty responses

## Codex `execpolicy` Shortcut

For Codex `PreToolUse` requests where `tool_name == "Bash"`, Agent Hooks can skip the dialog if local Codex policy has already allowed the command.

The middleware runs:

```bash
codex execpolicy check -c model="5.4-mini" --rules ~/.codex/rules/default.rules -- <command ...>
```

If the top-level JSON `decision` is `allow`, the built-in callback returns an empty response immediately.

Current environment knobs:

- `AGENT_HOOK_CODEX_EXECPOLICY_MODEL`
- `AGENT_HOOK_CODEX_EXECPOLICY_RULES`

## macOS Behavior

The built-in callback uses `osascript` for dialogs and notifications.

- On macOS, it opens real local UI
- On non-macOS platforms, AppleScript actions are skipped
- If `AGENT_HOOK_DISABLE_OSASCRIPT=1`, AppleScript actions are skipped even on macOS

## Logging

Every callback run writes:

- an application log entry
- a raw input audit record
- a rendered response audit record

See [Logging](../reference/logging.md) for the file layout and configuration knobs.
