# Agent Hooks — macOS UI (0.3.0, preview)

A native menu-bar app that centralizes Claude Code / Codex permission prompts into a
Slack-like buffer. It talks to the Python `agent-hooks` hook process through a shared SQLite
database (`~/Library/Application Support/agent-hooks/queue.db`, override with
`AGENT_HOOK_DB_PATH`).

The Python side writes a normalized request row and blocks; this app shows it as a card, and
your answer is written back as a `responses` row. See `../src/agent_hooks/sqlite/schema.sql`
for the canonical contract (kept in sync with `Sources/AgentHooksUI/Schema.swift`).

## Enable it

1. Build/run this app (it must be running for `sqlite` mode to engage; otherwise the hook
   falls back to the AppleScript dialog).
2. Point `agent-hooks` at it:

   ```sh
   export AGENT_HOOK_UI=sqlite
   ```

## Build & run

Quick run during development (needs a desktop session; no Dock/Spotlight entry):

```sh
swift run --package-path macos agent-hooks-ui
swift run --package-path macos agent-hooks-ui --selftest   # headless DB health check
```

### Launch from Spotlight / Finder / Launchpad

`swift build` only produces a bare executable; Spotlight and Finder only launch `.app`
bundles. Package one:

```sh
cd macos
./scripts/build_app.sh --install     # builds and copies to ~/Applications/Agent Hooks.app
# or: ./scripts/build_app.sh         # just builds macos/build/Agent Hooks.app (drag to /Applications)
```

Then:

- **Spotlight**: `Cmd+Space`, type "Agent Hooks", press Return.
- **Finder/Launchpad**: open `~/Applications` (or `/Applications`) and double-click *Agent Hooks*.

It is a menu-bar agent (`LSUIElement`), so there is **no Dock icon** — look for the tray icon
in the right side of the menu bar and click it to open the panel. The bundle is ad-hoc signed
for local use; if macOS ever blocks it as "unidentified developer", right-click the app →
**Open** once, or allow it under System Settings → Privacy & Security.

### Quit

- **Right-click** (or control-click) the menu-bar icon → **Quit Agent Hooks**, or
- open the panel (left-click the icon) → the **•••** menu → **Quit Agent Hooks** (`Cmd+Q`).
- From a terminal: `pkill -f agent-hooks-ui`.

The app is a non-sandboxed menu-bar accessory (no Dock icon) so it can share the database file
with the Python process. It bootstraps the schema, heartbeats a `daemon` row so hooks can
detect it, polls for pending requests, and groups them per repo/worktree.

- **Permission requests** are cards in the panel; the panel auto-surfaces on a count / quiet
  threshold (Settings).
- **Notifications** (Stop / StopFailure / generic) are *not* shown in the panel — they pop up as
  toast banners from the top-right corner (batched by the same thresholds) and auto-dismiss.
- A janitor clears cards whose owning hook died: SIGTERM/SIGINT marks the request cancelled
  instantly, and an uncatchable SIGKILL is reaped within ~2s once the heartbeat goes stale and
  the pid is gone.
- Cards you answer in the agent's own TUI (instead of here) are dismissed automatically: once
  the owning session moves past a card — a newer request arrives for it, or its round ends /
  a new round starts — the card is cancelled and removed.

## Sessions panel

The panel has three views, switched from the **•••** menu (Answers / Sessions / Settings).
Clicking the menu-bar icon opens **Answers** when something is waiting on you, otherwise the
live **Sessions** dashboard.

Each session is one row with a status dot:

- 🟢 **green** — process alive and working (a round/tool is in progress)
- 🟡 **yellow** — process alive but idle
- ⚪️ **gray** — process gone (a recent session, dropped after ~5 min)
- 🔴 **red** — last round failed (positioned by liveness)

Rows are ordered green → yellow → gray and capped by the **max sessions** Settings value
(default 10). Liveness is the recorded agent pid (`os.getppid()` of the hook) probed with
`kill(pid, 0)`, with the transcript file's mtime as a "recently active → alive" fallback. The
current/last tool call and its output are read live by tailing the session `transcript_path`,
and the round timer ticks from the recorded round-start. (Claude Code's TUI token counts /
"thinking effort" are internal to its TUI and not available to hooks, so they are not shown.)

To populate the dashboard, register **`SessionStart`** and **`UserPromptSubmit`** hooks (in
addition to the permission/stop hooks) and point every hook command at `--ui swift-ui`. See the
provider config in the root `README.md`. Sessions appear only when the Swift app is running;
without it, hooks fall back to the AppleScript dialog and nothing is recorded.

## Status / not yet done

- Packaging into a signed `.app` + launch-at-login item.
- Hover-to-open (currently click-to-open; the panel still auto-surfaces on batch).
