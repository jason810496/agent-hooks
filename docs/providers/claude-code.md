# Claude Code

This page documents the current Claude Code implementation in Agent Hooks.

## Raw Event Coverage

The Claude adapter currently normalizes these raw events into first-class shared event names:

- `Notification`
- `PermissionRequest`
- `Stop`
- `StopFailure`

The matcher also recognizes a broader set of Claude-specific raw event names so payload detection can stay correct even when the built-in app does not turn them into dedicated behavior yet.

## Built-in App Behavior

The built-in callback app gives Claude Code:

- notification rendering for `Notification`
- permission dialogs for `PermissionRequest`
- completion notifications for `Stop`
- error notifications for `StopFailure`

## Permission Handling

Claude permission responses support three dialog choices:

- `Deny`
- `Allow Once`
- `Always Allow`

`Always Allow` is session-scoped. When Claude supplies `permission_suggestions`, Agent Hooks converts them into `updatedPermissions` with destination `session`.

That means the built-in Claude flow can preview and apply session rules without inventing its own permission format.

## Response Rendering

The Claude renderer currently supports the top-level fields already modeled in the shared response:

- `suppressOutput`
- `continue`
- `stopReason`
- `systemMessage`
- `decision`
- `reason`
- `hookSpecificOutput`

For permission requests, the important block is the Claude `decision` payload inside `hookSpecificOutput`.

## Current Limitations

- The matcher recognizes more Claude raw events than the current normalization table exposes as first-class built-in behavior.
- `SessionStart`, `PostToolUse`, and `UserPromptSubmit` are not part of the Claude adapter's normalized event surface today.
- The docs site intentionally does not describe unsupported Claude behaviors that the current code does not implement.

## Practical Takeaway

If your Claude Code usage is centered on:

- local permission prompts
- notifications
- stop-state visibility

the built-in app is already useful. If you need more Claude event-specific logic, build a custom `AgentHook` app and work from the normalized payload plus `payload.raw`.
