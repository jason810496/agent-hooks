# Provider Adapters

Provider adapters are what let the framework stay provider-neutral while still speaking each provider's hook protocol accurately.

## Adapter Responsibilities

Each adapter defines:

- payload matching
- payload normalization
- response rendering
- notification display building
- permission dialog building
- permission response building
- optional provider middleware

## Why This Split Matters

The app layer should not need to know:

- how Claude and Codex name raw hook events
- which top-level response fields a provider accepts
- how permission decisions are encoded on the wire

The adapter layer owns those details.

## Current Adapters

## Claude Code Adapter

Responsibilities include:

- matching Claude payloads
- mapping raw Claude events into normalized event names
- building Claude-specific permission response payloads
- rendering Claude top-level fields like `suppressOutput`

## Codex Adapter

Responsibilities include:

- matching Codex payloads
- normalizing `PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `SessionStart`, and `Stop`
- rendering Codex-specific hook response payloads
- providing Codex middleware for `execpolicy`

## Shared Payoff

Because adapters isolate protocol details:

- the router can stay provider-neutral
- the built-in app can reuse the same processing path where semantics overlap
- new custom apps can focus on behavior instead of provider wire schemas

## Current Constraint

Only two adapters exist today:

- Claude Code
- Codex

If a new provider is added later, it should arrive as a new adapter rather than more conditionals spread through the router and runner.
