-- OctaLedger schema, migration 0004: the attention centre ("Rückfragen-Zentrale").
--
-- An attention item is something that waits for a decision of the user, even while the
-- dashboard is closed: a gap after a lost connection, an idle period, an automatic stop, a
-- reminder. One table serves all cases (`kind`); the case-specific data lives in `payload`
-- (JSON, never secrets).
--
-- Items never change time data on their own: they only record the question and, later, the
-- user's answer. They are runtime data and are not part of a backup. Deleting a session
-- removes the questions about it.
--
-- Migrations run inside one transaction each; do not put BEGIN/COMMIT in this file.

CREATE TABLE attention_items (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL CHECK (kind IN ('gap', 'idle', 'auto_stop', 'reminder', 'break_hint')),
    created_at  TEXT NOT NULL,
    session_id  TEXT REFERENCES sessions (id) ON DELETE CASCADE,
    payload     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'resolved', 'dismissed', 'expired')),
    resolved_at TEXT,
    resolution  TEXT
);

CREATE INDEX ix_attention_status ON attention_items (status, created_at);
