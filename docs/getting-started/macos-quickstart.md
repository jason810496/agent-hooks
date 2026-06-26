# macOS Quickstart

This guide is for the out-of-box path: install Agent Hooks, point your provider at the built-in callback command, and verify that the local callback loop works on macOS.

!!! note "Platform assumption"
    This quickstart is written for **macOS with local AppleScript dialogs and notifications enabled**. If you only want to test payload parsing, you can temporarily disable AppleScript and still validate the callback flow.

## Prerequisites

- macOS
- `uv`
- Claude Code or Codex

## Quick Setup

=== "Claude Code"
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

=== "Codex"
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

If you are working from the repository instead of the published tool, you can also run the package through `uv run`, but the documented default is the installable CLI.

!!! tip "Recommended wiring"
    **Use `--provider` directly in the provider config** unless you have a specific reason to drive provider selection through environment variables. It makes the callback target easier to inspect later.

!!! tip "Live Sessions dashboard"
    Running the native menu-bar app (`--ui swift-ui`) adds a **Sessions** panel that lists every Claude Code / Codex session with a live status dot, current tool call, and round timer. Pass `--ui swift-ui` on every hook command and add `SessionStart` / `UserPromptSubmit` hooks so it can track activity. See the root `README.md` ("Live sessions panel") and `macos/README.md`.

## Smoke Test The Callback Locally

=== "Claude Code"
    Claude-style permission request:

    ```bash
    printf '%s\n' '{"hook_event_name":"PermissionRequest","tool_name":"Bash","tool_input":{"command":"git status"}}' | agent-hooks callback --provider claude-code
    ```

=== "Codex"
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

!!! info "Good test strategy"
    Start with **AppleScript disabled** if you want to verify parsing, provider routing, and response rendering without opening dialogs. Re-enable it once the command path looks correct.

## What To Expect

- macOS permission events open a dialog
- stop events can produce notifications
- responses are written to `stdout`
- logs are written under `logs/` by default

!!! note "If the callback looks quiet"
    Some events intentionally return empty responses. That does **not** necessarily mean the callback failed. Check the local logs if you need to confirm what was received and rendered.

!!! warning "Notifications missing, or the response looks blocked?"
    If notifications never appear while a **Focus / Do Not Disturb / Work** mode is active, or a Claude Code turn seems to hang after it finishes, see [Troubleshooting](../reference/troubleshooting.md). Both are usually macOS notification-permission settings rather than callback failures.

If you need custom behavior instead of the built-in app, move on to [Custom Apps](../cli/custom-apps.md).
