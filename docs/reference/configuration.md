# Configuration

Agent Hooks is configured primarily through CLI flags and environment variables.

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

## Project Root And Paths

- `AGENT_HOOK_PROJECT_ROOT`
- `AGENT_HOOK_LOG_DIR`
- `AGENT_HOOK_APP_LOG_PATH`
- `AGENT_HOOK_INPUT_AUDIT_LOG_PATH`
- `AGENT_HOOK_RESPONSE_AUDIT_LOG_PATH`

Relative paths are resolved from `AGENT_HOOK_PROJECT_ROOT`. If you do not set it, the package default project root is used.

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

## Recommended Pattern

Use CLI flags for provider choice and environment variables for persistent local defaults, especially:

- project root
- log paths
- AppleScript enable or disable
- Codex rules path
