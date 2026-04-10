# ADR 001: Data Models

- Status: Accepted
- Date: 2026-04-09

## Context

This application receives Claude Code hook callbacks and persists enough state to:

- show a UI timeline of hook activity;
- queue actionable approval requests;
- let multiple requests exist concurrently for the same session; and
- return a structured hook response back to the waiting caller.

The observed hook traffic currently includes at least:

- `PermissionRequest`
- `Notification`
- `Stop`

Only `PermissionRequest` is currently actionable and needs a durable queue item. Other hook
events should still be stored so they can appear in the UI timeline and act as an audit trail.

We intentionally do not persist a separate policy model for "Always Allow". That choice only
echoes Claude's `updatedPermissions` back to the current session.

## Decision

Use three tables only:

1. `session`
2. `hook_event`
3. `request`

Use singular table names.

### `session`

Represents a provider session such as a Claude Code session.

Suggested fields:

- `id` integer primary key
- `provider` text not null
- `provider_session_id` text not null unique
- `cwd` text
- `transcript_path` text
- `permission_mode` text
- `created_at` text not null
- `updated_at` text not null
- `last_seen_at` text not null

### `hook_event`

Append-only store for every inbound hook callback. This is the source of truth for the UI
timeline and the main audit log.

Suggested fields:

- `id` integer primary key
- `session_id` integer not null references `session(id)`
- `hook_event_name` text not null
- `payload_json` text not null
- `display_json` text
- `processing_error` text
- `created_at` text not null

Optional denormalized fields may be added later for query convenience, for example `tool_name`
or `notification_type`, but the initial design should keep the event payload in JSON.

### `request`

Stores actionable work items derived from hook events. At this stage, only
`PermissionRequest` creates a row here.

Suggested fields:

- `id` integer primary key
- `hook_event_id` integer not null unique references `hook_event(id)`
- `session_id` integer not null references `session(id)`
- `status` text not null
- `tool_name` text
- `tool_input_json` text
- `suggestions_json` text
- `answer_choice` text
- `answer_payload_json` text
- `hook_response_json` text
- `answered_by` text
- `answer_channel` text
- `answered_at` text
- `resolved_at` text
- `created_at` text not null
- `updated_at` text not null

The `request` table does not have a separate UUID-style `uid` or `qid`. The integer primary key
is sufficient for internal persistence. The one-to-one relationship with `hook_event` is enforced
through `hook_event_id unique`.

## Write Path

For every hook callback:

1. Upsert `session` using provider session identity.
2. Insert one `hook_event`.

For `PermissionRequest` only:

1. Upsert `session`.
2. Insert `hook_event`.
3. Insert `request`.

Steps 1 to 3 for `PermissionRequest` must happen in the same SQLite transaction so the queue item
and its source event are always created together.

For non-actionable events such as `Notification` and `Stop`, only persist `session` and
`hook_event`.

## Rationale

This design keeps the first version small without losing important information:

- `hook_event` gives a complete timeline for the UI.
- `request` stays focused on queued approval work.
- no separate `answers` or `deliveries` tables are needed yet.
- multiple concurrent requests per session are naturally supported.
- "Always Allow" stays session-scoped and does not introduce policy management complexity.

## Consequences

Accepted tradeoffs:

- `request` stores the current answer and final hook response, not a detailed answer history.
- delivery attempts are not modeled as first-class rows.
- provider-specific fields remain inside JSON payloads for now.

If later we need retry history, multi-channel delivery auditing, or answer edits, we can add a
fourth append-only history table without changing the basic `session` -> `hook_event` ->
`request` structure.
