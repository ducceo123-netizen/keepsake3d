PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS sessions (
 id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, design_id TEXT NOT NULL,
 design_version TEXT NOT NULL, state TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, expires_at TEXT NOT NULL, consent_at TEXT,
 params_json TEXT, appearance_json TEXT, job_id TEXT, checksum TEXT, error_json TEXT
);
CREATE TABLE IF NOT EXISTS photos (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 private_path TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
 sha256 TEXT NOT NULL, created_at TEXT NOT NULL, synthetic INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS build_jobs (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 revision INTEGER NOT NULL, state TEXT NOT NULL, input_hash TEXT NOT NULL,
 idempotency_key TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL, finished_at TEXT, error_code TEXT,
 UNIQUE(session_id,idempotency_key)
);
CREATE TABLE IF NOT EXISTS artifacts (
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES build_jobs(id) ON DELETE CASCADE,
 kind TEXT NOT NULL, private_path TEXT NOT NULL, sha256 TEXT NOT NULL,
 revision INTEGER NOT NULL, metadata_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS qa_reports (
 job_id TEXT PRIMARY KEY REFERENCES build_jobs(id) ON DELETE CASCADE, report_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 action TEXT NOT NULL, created_at TEXT NOT NULL, detail_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS photos_session ON photos(session_id);
CREATE INDEX IF NOT EXISTS jobs_session ON build_jobs(session_id);
