-- OctaLedger schema, migration 0003: control mode, integrations, face actions and job outbox.
--
-- A tracker can run in one of two modes: 'time' (faces are activities, the default) or
-- 'control' (faces are actions that switch a light, publish a message ...). Existing trackers
-- stay in 'time'.
--
-- Secrets (tokens, passwords) are NEVER stored here: `integrations.config` holds only
-- non-secret settings; secrets live in a separate file in the user profile.
--
-- `integration_jobs` is an outbox: a job is written in the same transaction as the raw event
-- that triggered it, so a trigger is neither lost nor sent twice (unique idempotency key).
-- Jobs are runtime data and are not part of a backup.
--
-- Migrations run inside one transaction each; do not put BEGIN/COMMIT in this file.

ALTER TABLE devices
    ADD COLUMN mode TEXT NOT NULL DEFAULT 'time' CHECK (mode IN ('time', 'control'));

CREATE TABLE integrations (
    id         TEXT PRIMARY KEY,
    kind       TEXT NOT NULL CHECK (length(kind) BETWEEN 1 AND 40),
    name       TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 100),
    config     TEXT NOT NULL,
    enabled    INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX ux_integrations_name ON integrations (name COLLATE NOCASE);

CREATE TABLE face_actions (
    device_id      TEXT NOT NULL REFERENCES devices (id) ON DELETE CASCADE,
    face           INTEGER NOT NULL CHECK (face BETWEEN 1 AND 8),
    integration_id TEXT NOT NULL REFERENCES integrations (id) ON DELETE RESTRICT,
    label          TEXT NOT NULL CHECK (length(label) BETWEEN 1 AND 100),
    params         TEXT NOT NULL,
    revision       INTEGER NOT NULL CHECK (revision >= 1),
    PRIMARY KEY (device_id, face)
);

CREATE TABLE integration_jobs (
    id               TEXT PRIMARY KEY,
    idempotency_key  TEXT NOT NULL UNIQUE,
    integration_id   TEXT NOT NULL REFERENCES integrations (id) ON DELETE CASCADE,
    device_id        TEXT REFERENCES devices (id) ON DELETE SET NULL,
    face             INTEGER CHECK (face IS NULL OR face BETWEEN 1 AND 8),
    label            TEXT NOT NULL,
    params           TEXT NOT NULL,
    status           TEXT NOT NULL CHECK (status IN ('pending', 'done', 'failed', 'expired')),
    attempts         INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error       TEXT,
    created_at       TEXT NOT NULL,
    expires_at       TEXT NOT NULL,
    next_attempt_at  TEXT NOT NULL,
    finished_at      TEXT
);
-- The dispatcher looks for due pending jobs ordered by creation time.
CREATE INDEX ix_jobs_due ON integration_jobs (status, next_attempt_at);
CREATE INDEX ix_jobs_integration ON integration_jobs (integration_id, status);
