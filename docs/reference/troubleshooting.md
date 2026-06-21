# Troubleshooting

This page collects macOS-specific behavior that can make the built-in callback look
broken when it is actually working as designed.

## Notifications Do Not Appear In Focus / Do Not Disturb / Work Mode

Agent Hooks posts notifications (for `Stop`, `StopFailure`, and `Notification`
events) by running `osascript`'s `display notification`. macOS does not attribute
those notifications to your terminal or to Agent Hooks. It attributes them to the
**Script Editor** app (`com.apple.ScriptEditor2`), because that is the host that
executes the AppleScript.

That matters for Focus filters: while a Focus mode such as **Do Not Disturb** or
**Work** is active, macOS silences every app that is not on that mode's allow list.
Since the notifications come from Script Editor, you must allow Script Editor through
the active Focus mode.

To let Agent Hooks notifications break through a Focus mode:

1. Open **System Settings → Focus**.
2. Select the Focus you use (for example **Do Not Disturb** or **Work**).
3. Under **Allowed Notifications**, open the **Apps** (or **Allowed Apps**) list.
4. Add **Script Editor**.

Also confirm notifications are enabled for Script Editor at all:

1. Open **System Settings → Notifications**.
2. Select **Script Editor**.
3. Turn on **Allow Notifications** (and pick the alert style you want).

!!! note "Why Script Editor?"
    `display notification` is always delivered on behalf of the scripting host, not
    the calling process. From the command line that host is Script Editor, so its
    notification and Focus permissions govern whether you see Agent Hooks
    notifications.

!!! tip "Quick check"
    Run a notification directly to confirm delivery, independent of Claude Code or
    Codex:

    ```bash
    osascript -e 'display notification "hello" with title "Agent Hooks"'
    ```

    If this is silent while a Focus mode is on but appears once you disable Focus,
    the fix is the Script Editor allow-list step above.

## Claude Code Response Seems Blocked After A Turn (Stop Hook)

### Symptom

After Claude Code finishes a turn, the response appears to hang or arrive late, and
the delay lines up with having a `Stop` hook wired to `agent-hooks callback`.

### Cause

Claude Code runs `Stop` hooks synchronously and waits for them to finish before the
turn ends. For `Stop` events the built-in callback only posts a notification through
`osascript`. On most setups that returns instantly, but on some macOS
configurations notification delivery is slow or stalls entirely, for example:

- a Focus mode is suppressing the notification (see the section above),
- notification permission for Script Editor has never been established, or
- the macOS notification daemon (`usernoted`) is busy.

When the `osascript` call stalls, the hook does not return, so Claude Code keeps
waiting and the response looks blocked. This is a macOS configuration difference
rather than a decision the hook makes: the built-in `Stop` handler never returns a
`block` decision.

### Built-in safeguard

To keep a stalled notification from holding up a turn, notification `osascript`
calls are run with a timeout. If the call does not finish in time, Agent Hooks gives
up on the notification, records the failure in the application log, and still emits
the normal hook response so Claude Code can continue.

The timeout defaults to `10` seconds and is configurable with
`AGENT_HOOK_NOTIFICATION_TIMEOUT` (see
[Configuration](configuration.md#notification-timeout)). Set it to `0` to wait
indefinitely (the pre-safeguard behavior).

!!! note "Interactive dialogs are never time-limited"
    The timeout applies only to notifications. Permission and AskUserQuestion
    dialogs block on purpose while they wait for your answer, so they are never cut
    off by this setting.

### Remedies

- Allow **Script Editor** through your Focus mode and enable its notifications, as
  described above. This addresses the most common cause.
- If you do not need notifications at all, disable AppleScript for the callback with
  `AGENT_HOOK_DISABLE_OSASCRIPT=1`. The callback then skips `osascript` entirely and
  returns immediately.
- Leave the notification timeout at its default so a future stall cannot block a
  turn for more than a few seconds.
