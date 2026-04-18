# Codex

This page documents the current Codex implementation in Agent Hooks.

## Quick Setup

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

This gives Codex a local permission dialog for Bash tool calls plus local stop notifications through the same callback command.

If your Codex build already has hooks enabled by default, keep the `hooks.json` example above and skip this stanza.

!!! tip "Why the example matches only Bash"
    The built-in Codex UX is strongest around `PreToolUse` permission mediation for shell commands. Start there, then broaden the matcher later if your workflow needs more coverage.

## Raw Event Coverage

The Codex adapter normalizes these raw events:

- `SessionStart`
- `PreToolUse`
- `PostToolUse`
- `UserPromptSubmit`
- `Stop`

`PreToolUse` is normalized into the shared `PermissionRequest` event so Codex can reuse the same permission route used by Claude.

## Built-in App Behavior

The built-in callback app currently behaves like this:

- `PreToolUse`: permission dialog handling
- `Stop`: stop notification handling
- `SessionStart`: empty response
- `PostToolUse`: empty response
- `UserPromptSubmit`: empty response

This means Codex event registration is broader than the current UI behavior exposed by the built-in app.

## Permission Handling

The Codex built-in permission dialog offers:

- `Deny`
- `Allow Once`

There is no built-in persistent `Always Allow` path for Codex permission requests today.

Response behavior is also intentionally narrow:

- `Deny` emits `hookSpecificOutput.permissionDecision = "deny"`
- `Allow Once` returns an empty JSON object

## `execpolicy` Shortcut

For Codex `PreToolUse` events where:

- the provider is Codex
- the normalized event is a permission request
- `tool_name == "Bash"`

Agent Hooks checks the Bash command against:

```bash
codex execpolicy check -c model="5.4-mini" --rules ~/.codex/rules/default.rules -- <command ...>
```

If the top-level result is `allow`, the dialog is skipped and the callback returns immediately.

Current env vars:

- `AGENT_HOOK_CODEX_EXECPOLICY_MODEL`
- `AGENT_HOOK_CODEX_EXECPOLICY_RULES`

## Response Rendering

The Codex renderer is event-sensitive:

- some events accept `continue`
- permission responses are carried through `hookSpecificOutput`
- stop responses can use `decision`, `reason`, and `systemMessage`
- Codex responses do not automatically include Claude-style `suppressOutput`

## Current Limitations

- No built-in persistent allow behavior for Codex permission requests
- `SessionStart`, `PostToolUse`, and `UserPromptSubmit` are currently no-op routes in the built-in app
- The `execpolicy` shortcut is only for Bash commands
- The shortcut only auto-skips on top-level `allow`
- The current implementation does not expose an environment variable for changing the `codex` binary path

## Practical Takeaway

Codex support is already strong enough for:

- local Bash permission mediation
- stop notifications
- custom Codex hook apps built on the normalized event model

If you want richer session-start, post-tool-use, or user-prompt-submit behavior, use a custom `AgentHook` app.
