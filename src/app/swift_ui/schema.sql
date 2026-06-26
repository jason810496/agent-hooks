-- Canonical SQLite schema shared by the Python hook process and the Swift app.
-- Both sides run this idempotently (CREATE ... IF NOT EXISTS) and gate on
-- ``PRAGMA user_version``. Keep this file in sync with the Swift copy.

PRAGMA journal_mode = WAL;       -- concurrent readers + serialized fast writes

-- requests: written by the Python hook process (one row per PermissionRequest /
-- AskUserQuestion hook). The owning process polls ``responses`` for an answer.
CREATE TABLE IF NOT EXISTS requests (
  request_uid      TEXT PRIMARY KEY,   -- uuid4 minted by Python
  kind             TEXT NOT NULL,      -- 'permission' | 'permission_choice' | 'ask_user_question'
  status           TEXT NOT NULL DEFAULT 'pending',
                                       -- pending | answered | cancelled | abandoned | expired
  queue            TEXT NOT NULL,      -- git toplevel of cwd (worktree root), fallback cwd
  cwd              TEXT NOT NULL,
  session_id       TEXT,
  provider         TEXT NOT NULL,      -- 'claude-code' | 'codex'
  tool_name        TEXT,
  tool_use_id      TEXT,
  title            TEXT,               -- dialog/picker title
  summary          TEXT,               -- formatted tool detail shown on the card
  tool_input_json  TEXT,               -- ToolInput.raw (incl. AskUserQuestion 'questions')
  options_json     TEXT,               -- renderable options for the card (see SQLiteTransport)
  suggestions_json TEXT,               -- raw permission_suggestions (audit/debug)
  transcript_path  TEXT,
  owner_pid        INTEGER NOT NULL,   -- orphan detection
  owner_host       TEXT,
  created_at_ms    INTEGER NOT NULL,
  heartbeat_at_ms  INTEGER NOT NULL,   -- refreshed by Python while it polls
  expires_at_ms    INTEGER             -- optional max-defer deadline
);
CREATE INDEX IF NOT EXISTS idx_requests_queue_status ON requests (queue, status);

-- responses: written by the Swift app (one row answers one request). The presence
-- of a row is the signal that the request was answered.
CREATE TABLE IF NOT EXISTS responses (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  request_uid    TEXT NOT NULL REFERENCES requests (request_uid),
  selected_index INTEGER,             -- chosen option index (dialog button / picker choice)
  answers_json   TEXT,                -- AskUserQuestion answers: {"question": "a, b"}
  cancelled      INTEGER NOT NULL DEFAULT 0,
  responder      TEXT NOT NULL,       -- 'swift_ui' | 'self'
  created_at_ms  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_responses_request ON responses (request_uid);

-- notifications: non-blocking buffer (Notification / Stop / StopFailure events).
CREATE TABLE IF NOT EXISTS notifications (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  queue         TEXT NOT NULL,
  session_id    TEXT,
  kind          TEXT,                 -- 'notification' | 'stop' | 'stop_failure'
  title         TEXT,
  subtitle      TEXT,
  message       TEXT,
  created_at_ms INTEGER NOT NULL,
  seen_at_ms    INTEGER
);

-- settings: key/value tuning read by the Swift settings page (batching thresholds).
CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT
);

-- daemon: single row the Swift app heartbeats so hooks can detect liveness.
CREATE TABLE IF NOT EXISTS daemon (
  id              INTEGER PRIMARY KEY CHECK (id = 1),
  pid             INTEGER,
  host            TEXT,
  version         TEXT,
  heartbeat_at_ms INTEGER NOT NULL
);

-- sessions: one row per Claude Code / Codex session, upserted by the Python hook on
-- every event. ``status`` is the round state; the Swift app derives live/dead from
-- ``session_pid``/``session_host`` (process liveness) plus transcript mtime, so aliveness
-- is never persisted and cannot go stale.
CREATE TABLE IF NOT EXISTS sessions (
  session_id        TEXT NOT NULL,
  provider          TEXT NOT NULL,       -- 'claude-code' | 'codex'
  queue             TEXT NOT NULL,       -- git toplevel of cwd (worktree root), fallback cwd
  cwd               TEXT NOT NULL,
  model             TEXT,
  transcript_path   TEXT,
  session_pid       INTEGER,             -- os.getppid() of the hook = the agent process
  session_host      TEXT,                -- socket.gethostname()
  status            TEXT NOT NULL,       -- working | idle | failed
  last_event        TEXT,                -- raw_event_name of the last update
  tool_name         TEXT,                -- last known tool
  round_started_ms  INTEGER,             -- set on UserPromptSubmit/SessionStart, cleared on Stop
  last_round_ms     INTEGER,             -- duration of the last completed round
  error_text        TEXT,                -- StopFailure detail
  updated_at_ms     INTEGER NOT NULL,
  PRIMARY KEY (session_id, provider)
);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions (updated_at_ms);

PRAGMA user_version = 2;
