# Claude Code

This page documents the current Claude Code implementation in Agent Hooks.

## Quick Setup

Install the CLI:

```bash
uv tool install agent-hooks
```

Put this in `~/.claude/settings.json` for a global setup, or in `.claude/settings.json` for a project-local setup:

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
    ],
    "PreToolUse": [
      {
        "matcher": "AskUserQuestion",
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

This setup wires the built-in callback into the Claude flows Agent Hooks handles best today:

- `PermissionRequest` for local allow or deny decisions
- `Notification` with `matcher: "permission_prompt"` so attention requests also surface locally
- `Stop` and `StopFailure` for local completion or error visibility
- `PreToolUse` with `matcher: "AskUserQuestion"` so the [native picker](#askuserquestion-picker) fires for every question (including auto-allowed tool calls that skip `PermissionRequest`)

!!! tip "Why the explicit provider flag"
    Use `--provider claude-code` in the hook command even though Claude payloads are often identifiable on their own. It keeps the callback wiring explicit and easier to debug later.

## Raw Event Coverage

The Claude adapter currently normalizes these raw events into first-class shared event names:

- `Notification`
- `PermissionRequest`
- `PreToolUse` (only when `tool_name == "AskUserQuestion"`; normalized to `PermissionRequest` so the picker flow handles it)
- `Stop`
- `StopFailure`

The matcher also recognizes a broader set of Claude-specific raw event names so payload detection can stay correct even when the built-in app does not turn them into dedicated behavior yet.

## Built-in App Behavior

The built-in callback app gives Claude Code:

- notification rendering for `Notification`
- permission dialogs for `PermissionRequest`
- the [AskUserQuestion picker](#askuserquestion-picker) for `PreToolUse` on `AskUserQuestion`
- completion notifications for `Stop`
- error notifications for `StopFailure`

## Permission Handling

Claude permission requests carry `permission_suggestions` describing the session
rules the user could persist (for example "this exact command", "all `git *`
commands", or "all `Bash` commands"). Agent Hooks renders each suggestion as its own
choice instead of collapsing them behind a single `Always Allow` button.

### Permission Picker

When Claude supplies at least one `permission_suggestion`, the built-in app shows a
native `choose from list` picker whose choices are:

- `Allow once` - allow the call without persisting a rule
- one entry per suggestion, labeled with the rule(s) it would persist, shown exactly
  as Claude sent them (for example `Bash(git *)`, `Edit(src/**), Write(src/**)`, or a
  non-rule scope such as `mode: acceptEdits`)

Every entry below `Allow once` is an always-allow choice, so the labels carry no
redundant "Always allow" prefix. The picker's buttons are `Select` and `Deny`.
Selecting a rule entry returns `behavior: "allow"` with `updatedPermissions`
containing only the chosen suggestion, scoped to destination `session`. Selecting
`Allow once` allows the call with no `updatedPermissions`. Pressing `Deny` (or
dismissing the picker) denies the call.

Because only the selected suggestion is persisted, the user can pick the exact scope
they want rather than accepting every offered rule at once.

### Standard Dialog Fallback

When the picker is unavailable - non-macOS hosts, `osascript` disabled via
`AGENT_HOOK_DISABLE_OSASCRIPT=1`, or a picker transport failure - Agent Hooks falls
back to the standard `Deny` / `Allow Once` / `Always Allow` dialog. The dialog message
lists every suggestion rule so the full scope stays visible, and its session-scoped
`Always Allow` applies all offered suggestions. Permission requests that arrive without
any `permission_suggestions` use this same dialog.

That means the built-in Claude flow can preview and apply session rules without
inventing its own permission format.

### AskUserQuestion Picker

When Claude Code calls the built-in `AskUserQuestion` tool, Agent Hooks intercepts the request and shows a native macOS picker for each question instead of the standard `Allow Once` / `Always Allow` / `Deny` dialog. The picker:

- uses radio-style single selection for `multiSelect: false` questions and shift-/cmd-click multi-selection for `multiSelect: true` questions
- shows the question text and each option's `description` as the prompt body
- exposes `Submit` and `Cancel` buttons in place of the standard permission buttons

When the user clicks `Submit`, the hook responds with `permissionDecision: "allow"` (PreToolUse) or `decision: { behavior: "allow" }` (PermissionRequest) together with an `updatedInput` block that contains the original `questions` plus an `answers` map keyed by question text. Claude Code consumes those answers directly and skips its built-in TUI picker, so the user only picks once.

When the user clicks `Cancel`, the hook responds with a deny decision and the request is dropped.

#### Required hook wiring

To enable the picker, the hook must run for `AskUserQuestion` invocations. The Quick Setup snippet already includes the required entry:

```json
"PreToolUse": [
  {
    "matcher": "AskUserQuestion",
    "hooks": [
      {
        "type": "command",
        "command": "agent-hooks callback --provider claude-code"
      }
    ]
  }
]
```

`PreToolUse` is required because `AskUserQuestion` can be auto-allowed (for example when a skill's `allowed-tools` lists it), in which case `PermissionRequest` never fires and the picker would be bypassed. The matcher narrows the hook to `AskUserQuestion` so other tool calls keep their normal `PermissionRequest` flow.

If you also keep the `PermissionRequest` hook from the Quick Setup, Agent Hooks deduplicates: whichever event fires first opens the picker, and the response carries the answers back through whichever wire shape Claude Code expects for that event.

#### Fallback

If `osascript` is unavailable (non-macOS hosts, sandboxed environments, or `AGENT_HOOK_DISABLE_OSASCRIPT=1`), Agent Hooks falls back to the standard permission dialog with a text preview of the questions so the request is still actionable.

#### Try it

To exercise this picker locally, ask Claude Code something like _"Ask me a couple of multi-option questions to test the picker."_ A separate native dialog opens for each question, and the answers flow back to Claude Code without its TUI prompting again.

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
