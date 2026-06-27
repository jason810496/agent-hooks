import Foundation

/// Canonical SQLite schema, kept byte-for-byte in sync with
/// ``src/agent_hooks/sqlite/schema.sql`` on the Python side. Both processes run this
/// idempotently (``CREATE ... IF NOT EXISTS``) and gate on ``PRAGMA user_version``.
enum Schema {
    static let userVersion: Int32 = 3

    static let sql = """
    PRAGMA journal_mode = WAL;

    CREATE TABLE IF NOT EXISTS requests (
      request_uid      TEXT PRIMARY KEY,
      kind             TEXT NOT NULL,
      status           TEXT NOT NULL DEFAULT 'pending',
      queue            TEXT NOT NULL,
      cwd              TEXT NOT NULL,
      session_id       TEXT,
      provider         TEXT NOT NULL,
      tool_name        TEXT,
      tool_use_id      TEXT,
      title            TEXT,
      summary          TEXT,
      tool_input_json  TEXT,
      options_json     TEXT,
      suggestions_json TEXT,
      transcript_path  TEXT,
      owner_pid        INTEGER NOT NULL,
      owner_host       TEXT,
      created_at_ms    INTEGER NOT NULL,
      heartbeat_at_ms  INTEGER NOT NULL,
      expires_at_ms    INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_requests_queue_status ON requests (queue, status);

    CREATE TABLE IF NOT EXISTS responses (
      id             INTEGER PRIMARY KEY AUTOINCREMENT,
      request_uid    TEXT NOT NULL REFERENCES requests (request_uid),
      selected_index INTEGER,
      answers_json   TEXT,
      cancelled      INTEGER NOT NULL DEFAULT 0,
      action         TEXT,
      freetext       TEXT,
      responder      TEXT NOT NULL,
      created_at_ms  INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_responses_request ON responses (request_uid);

    CREATE TABLE IF NOT EXISTS notifications (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      queue         TEXT NOT NULL,
      session_id    TEXT,
      kind          TEXT,
      title         TEXT,
      subtitle      TEXT,
      message       TEXT,
      created_at_ms INTEGER NOT NULL,
      seen_at_ms    INTEGER
    );

    CREATE TABLE IF NOT EXISTS settings (
      key   TEXT PRIMARY KEY,
      value TEXT
    );

    CREATE TABLE IF NOT EXISTS daemon (
      id              INTEGER PRIMARY KEY CHECK (id = 1),
      pid             INTEGER,
      host            TEXT,
      version         TEXT,
      heartbeat_at_ms INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS sessions (
      session_id        TEXT NOT NULL,
      provider          TEXT NOT NULL,
      queue             TEXT NOT NULL,
      cwd               TEXT NOT NULL,
      model             TEXT,
      transcript_path   TEXT,
      session_pid       INTEGER,
      session_host      TEXT,
      status            TEXT NOT NULL,
      last_event        TEXT,
      tool_name         TEXT,
      round_started_ms  INTEGER,
      last_round_ms     INTEGER,
      error_text        TEXT,
      updated_at_ms     INTEGER NOT NULL,
      PRIMARY KEY (session_id, provider)
    );
    CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions (updated_at_ms);

    PRAGMA user_version = 3;
    """
}

/// Current wall-clock time in integer milliseconds since the Unix epoch.
func nowMs() -> Int64 {
    Int64(Date().timeIntervalSince1970 * 1000)
}
