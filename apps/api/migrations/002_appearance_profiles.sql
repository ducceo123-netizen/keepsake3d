CREATE TABLE IF NOT EXISTS appearance_profiles (
 id TEXT PRIMARY KEY,
 session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 revision INTEGER NOT NULL,
 parent_id TEXT REFERENCES appearance_profiles(id) ON DELETE SET NULL,
 input_sha256 TEXT NOT NULL,
 profile_sha256 TEXT NOT NULL,
 payload_json TEXT NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(session_id,revision),
 UNIQUE(session_id,input_sha256)
);
CREATE INDEX IF NOT EXISTS appearance_profile_session ON appearance_profiles(session_id);
