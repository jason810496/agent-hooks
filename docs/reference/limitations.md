# Limitations

This page is intentionally blunt. It describes current implementation limits, not roadmap aspirations.

## Platform Limits

- The built-in local UI is macOS-oriented because it uses `osascript`.
- On non-macOS platforms, AppleScript actions are skipped rather than replaced with another UI backend.

## Provider Limits

- Only two providers are supported today: Claude Code and Codex.
- The docs do not promise Gemini, OpenAI Responses hooks, or other future adapters that are not in the current codebase.

## Claude Code Limits

- The Claude matcher recognizes more raw Claude event names than the adapter currently normalizes into first-class events.
- The built-in app is focused on notifications, permission requests, stop, and stop-failure behavior.
- The Swift UI free-text bar feeds the user's text back to the model via documented fields: a correction denies with `permissionDecisionReason` (`PreToolUse`/AskUserQuestion) or `decision.message` (`PermissionRequest`); an "Allow + note" attaches `additionalContext`. Because `additionalContext` is only valid on `PreToolUse`-wire events, the "Allow + note" affordance is offered only on AskUserQuestion cards, not on plain permission cards.

## Codex Limits

- The built-in app registers `SessionStart`, `PostToolUse`, and `UserPromptSubmit`, which return empty responses to the provider. `SessionStart` and `UserPromptSubmit` are recorded for the Swift UI Sessions panel (`--ui swift-ui`); `PostToolUse` is still unused.
- Codex permission handling has no built-in persistent `Always Allow` path.
- The `execpolicy` shortcut applies only to Bash permission requests.
- The shortcut only short-circuits when the top-level result is `allow`.
- The current implementation does not expose an env var for changing the `codex` binary path used for `execpolicy`.

## Framework Limits

- The framework normalizes shared event semantics, but provider-specific raw payload details still matter for advanced cases.
- Route dependencies support only one resolution level. Nested `Depends(...)` declarations are rejected during route registration.
- If you need raw provider fields that are not lifted into the shared models, you must read `payload.raw`.

## Packaging Limits

- The library itself has zero runtime Python package dependencies, but your custom hook app can of course introduce its own dependencies.
- The MkDocs site adds docs-only dependencies through the `docs` dependency group. That does not change the runtime dependency story for the package itself.
