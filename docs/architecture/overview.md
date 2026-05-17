# Architecture Overview

Agent Hooks is a local callback runner. There is no background daemon and no network service involved in the normal callback path.

## End-to-End Flow

```text
stdin JSON
  -> provider selection / inference
  -> normalized HookPayload
  -> provider middleware
  -> app middleware
  -> registered route or fallback handler
  -> macOS transport when needed
  -> provider-specific stdout JSON
  -> application + audit logs
```

## Processing Stages

## 1. Read And Parse Input

The runner reads the raw callback body from `stdin`, parses JSON, and records parse errors without crashing the callback entrypoint.

## 2. Select The Provider

The provider can come from:

- an explicit CLI argument
- runtime config
- auto-detection from the payload

## 3. Normalize The Payload

Each provider adapter maps its raw JSON into the shared `HookPayload` model so the rest of the app can reason about normalized events.

## 4. Apply Middleware

Provider middleware runs first, then app middleware.

This is where the Codex `execpolicy` shortcut lives.

## 5. Dispatch

The callback is dispatched through either:

- a registered `AgentHook` route
- or the fallback handler

The default fallback handler owns the generic built-in permission and notification flow.

## 6. Transport

When the chosen behavior needs local UI, the transport layer uses AppleScript to:

- show dialogs
- send notifications

## 7. Render Response

The final response is converted back into the provider-specific wire shape and written to `stdout`.

## 8. Log Everything Important

The runner writes:

- an app log record
- a raw input audit record
- a rendered response audit record

This keeps local callback runs debuggable without adding external infrastructure.
