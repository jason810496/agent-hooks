# Configuration

Agent Hooks is configured primarily through CLI flags and environment variables.

!!! tip "Recommended config split"
    **Use CLI flags for per-caller choices** like `--provider`, and **use environment variables for local defaults** like log paths, project root, AppleScript behavior, and Codex policy settings.

## Provider Selection

- `--provider claude-code|codex`
- `AGENT_HOOK_PROVIDER`

Use the explicit CLI flag when you want the most predictable behavior. If you do not set one, Agent Hooks will try to infer the provider from the incoming payload.

## AppleScript Control

- `AGENT_HOOK_DISABLE_OSASCRIPT`
- `CLAUDE_HOOK_DISABLE_OSASCRIPT`

Accepted true values:

- `1`
- `true`
- `yes`
- `on`

Accepted false values:

- `0`
- `false`
- `no`
- `off`

!!! note "Testing mode"
    Set `AGENT_HOOK_DISABLE_OSASCRIPT=1` when you want to validate callback behavior without opening macOS dialogs or notifications.

## Dialog Controls

- `AGENT_HOOK_DIALOG_FONT_SIZE`

Set this to a positive point size when you want larger or smaller macOS permission dialog text. Leave it unset to use the default `13` point dialog font size.

Smoke test the setting with a local permission dialog:

```bash
printf '%s\n' '{"hook_event_name":"PermissionRequest","tool_name":"Bash","tool_input":{"command":"git status"}}' \
  | AGENT_HOOK_DIALOG_FONT_SIZE=18 agent-hooks callback --provider claude-code
```

## Project Root And Paths

- `AGENT_HOOK_PROJECT_ROOT`
- `AGENT_HOOK_LOG_DIR`
- `AGENT_HOOK_APP_LOG_PATH`
- `AGENT_HOOK_INPUT_AUDIT_LOG_PATH`
- `AGENT_HOOK_RESPONSE_AUDIT_LOG_PATH`

Relative paths are resolved from `AGENT_HOOK_PROJECT_ROOT`. If you do not set it, the package default project root is used.

!!! note "Path resolution"
    **Relative log paths are anchored to `AGENT_HOOK_PROJECT_ROOT`.** If your logs end up somewhere unexpected, this is usually the first setting to check.

## App Log Controls

- `AGENT_HOOK_APP_LOG_LEVEL`
- `AGENT_HOOK_APP_LOG_FORMAT`
- `AGENT_HOOK_APP_LOG_MAX_BYTES`
- `AGENT_HOOK_APP_LOG_BACKUP_COUNT`

## Shared Log Rotation Controls

- `AGENT_HOOK_LOG_MAX_BYTES`
- `AGENT_HOOK_LOG_BACKUP_COUNT`

These act as fallbacks when a log-specific max-bytes or backup-count env var is not set.

## Input Audit Log Controls

- `AGENT_HOOK_INPUT_AUDIT_LOG_MAX_BYTES`
- `AGENT_HOOK_INPUT_AUDIT_LOG_BACKUP_COUNT`

## Response Audit Log Controls

- `AGENT_HOOK_RESPONSE_AUDIT_LOG_MAX_BYTES`
- `AGENT_HOOK_RESPONSE_AUDIT_LOG_BACKUP_COUNT`

## Codex `execpolicy`

- `AGENT_HOOK_CODEX_EXECPOLICY_MODEL`
- `AGENT_HOOK_CODEX_EXECPOLICY_RULES`

The current default model is `5.4-mini` and the default rules path is `~/.codex/rules/default.rules`.

!!! info "Important for Codex users"
    These settings control the **pre-check that can suppress repeated permission dialogs for already-allowed Bash commands**. If the behavior seems off, verify both the model and the rules path.

## Recommended Pattern

Use CLI flags for provider choice and environment variables for persistent local defaults, especially:

- project root
- log paths
- AppleScript enable or disable
- Codex rules path
