# Examples

This directory contains runnable `AgentHook` apps that show different callback patterns without adding extra dependencies.

## Included Apps

| File | Provider | Focus |
| --- | --- | --- |
| `minimal_permission.py` | Claude Code, Codex | Smallest provider-neutral permission app |
| `command_policy_middleware.py` | Claude Code, Codex | Middleware short-circuiting for safe and risky Bash commands |
| `repo_boundary_guard.py` | Claude Code, Codex | Deny filesystem access that escapes `cwd` or touches sensitive local paths |
| `branch_protection_guard.py` | Claude Code, Codex | Deny risky Git commands against protected branches |
| `sensitive_data_exfiltration_guard.py` | Claude Code, Codex | Deny remote transfer commands that reference sensitive files |
| `stop_notifier.py` | Claude Code, Codex | Custom transport-backed notifications for stop and error events |
| `claude_permission_suggestion_filter.py` | Claude Code | Apply only reviewed Claude permission suggestions as session rules |
| `codex_session_journal.py` | Codex | File-backed lifecycle journaling across separate callback runs |
| `codex_repo_context.py` | Codex | Add repository context at `SessionStart` |
| `codex_prompt_guard.py` | Codex | Block risky or low-signal prompts at `UserPromptSubmit` |
| `codex_test_before_stop.py` | Codex | Block `Stop` until a test-like command has been recorded |
| `audit_exporter.py` | Claude Code, Codex | Write compact normalized hook records to a custom JSONL audit file |

## Running An Example

Run an example file directly with the built-in loader:

```bash
uv run agent-hooks run minimal_permission.py --app-dir examples --provider codex
```

You can also pass hook JSON from stdin:

```bash
uv run agent-hooks run command_policy_middleware.py --app-dir examples --provider codex < examples/sample_payloads/codex_pre_tool_use_safe.json
```

If you want to exercise callback behavior without opening native macOS UI, disable AppleScript:

```bash
AGENT_HOOK_DISABLE_OSASCRIPT=1 uv run agent-hooks run command_policy_middleware.py --app-dir examples --provider codex < examples/sample_payloads/codex_pre_tool_use_unknown.json
```

Claude-specific examples use the same loader pattern:

```bash
AGENT_HOOK_DISABLE_OSASCRIPT=1 uv run agent-hooks run claude_permission_suggestion_filter.py --app-dir examples --provider claude-code < examples/sample_payloads/claude_permission_request_safe_suggestion.json
```

## Sample Payloads

`sample_payloads/` includes small JSON fixtures for the current examples:

- `claude_permission_request.json`
- `claude_permission_request_outside_root.json`
- `claude_permission_request_risky_suggestion.json`
- `claude_permission_request_safe_suggestion.json`
- `claude_notification_permission_prompt.json`
- `claude_stop.json`
- `claude_stop_failure.json`
- `codex_pre_tool_use_safe.json`
- `codex_pre_tool_use_unknown.json`
- `codex_pre_tool_use_git_push_main.json`
- `codex_pre_tool_use_exfiltration.json`
- `codex_session_start.json`
- `codex_user_prompt_submit_safe.json`
- `codex_user_prompt_submit_blocked.json`
- `codex_post_tool_use.json`
- `codex_post_tool_use_test.json`
- `codex_stop.json`

The Codex samples use `"cwd": "."` so they work from the repository root. If you run them from another project, update `cwd` first.

## Notes

- These are teaching examples, not production-ready policies. Narrow or harden them before using them across many repos.
- `branch_protection_guard.py`, `repo_boundary_guard.py`, and `sensitive_data_exfiltration_guard.py` are strongest when the provider hook matcher is scoped to the Bash or file tools you actually use.
- `stop_notifier.py` is intended for `Notification`, `Stop`, and `StopFailure` callbacks rather than permission mediation.
- `claude_permission_suggestion_filter.py` only uses Claude session rules for reviewed Bash suggestions.
- `codex_session_journal.py` writes JSONL files under `.agent-hooks/session-journal/` by default.
- `codex_test_before_stop.py` writes per-session state under `.agent-hooks/test-before-stop/` by default.
- `audit_exporter.py` writes compact JSONL audit records under `.agent-hooks/audit-export/` by default while still falling back to the built-in processor.
- Set `AGENT_HOOK_SESSION_JOURNAL_DIR` to move the journal somewhere else.
- `codex_repo_context.py` is intentionally conservative and only reads a short preview from a few common project files.
