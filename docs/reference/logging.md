# Logging

Agent Hooks writes three log streams per callback run.

## Default Files

By default, logs live under `logs/`:

- `logs/hooks.log`
- `logs/hooks.raw.log`
- `logs/hooks.response.log`

## What Each Log Contains

## Application Log

`hooks.log` contains the structured application record for each callback run, including:

- provider
- raw hook event name
- session id
- cwd
- tool name
- parse errors
- transport results
- response-size metadata
- configuration warnings
- processing errors

## Raw Input Audit Log

`hooks.raw.log` stores the raw callback input captured from `stdin`.

This is useful when:

- provider payloads change
- you are debugging normalization
- you want a precise record of what the hook received

## Response Audit Log

`hooks.response.log` stores the fully rendered response written back to the provider.

This is useful when:

- you are debugging provider wire compatibility
- you want to inspect the exact JSON emitted to `stdout`

## Rotation

All three files use rotating-file settings.

Defaults:

- max bytes: `5 * 1024 * 1024`
- backup count: `5`

These can be overridden globally or per log file through environment variables documented in [Configuration](configuration.md).

## Privacy Note

The raw input audit log can contain prompts, tool inputs, filesystem paths, and other provider-supplied context. Treat it as sensitive local development data.
