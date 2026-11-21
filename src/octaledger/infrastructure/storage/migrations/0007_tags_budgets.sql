-- OctaLedger schema, migration 0007: tags, note templates, budgets and hourly rates.
--
-- Everything is kept in separate tables (instead of new columns on activities/projects) so the
-- existing records and the backup format of those entities stay untouched; all five tables are
-- part of the JSON backup (schema 3, section `tables`).
--
-- tags / session_tags: free labels on entries (n:m). activity_tags: tags that a new entry of an
--   activity gets automatically. activity_notes: a note template per activity.
-- project_billing: optional budget (minutes), hourly rate (cents) and billable flag per project.
--
-- Migrations run inside one transaction each; do not put BEGIN/COMMIT in this file.

CREATE TABLE tags (
    id    TEXT PRIMARY KEY,
    name  TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 50),
    color TEXT NOT NULL CHECK (length(color) = 7)
);
CREATE UNIQUE INDEX ux_tags_name ON tags (name COLLATE NOCASE);

CREATE TABLE session_tags (
    session_id TEXT NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    tag_id     TEXT NOT NULL REFERENCES tags (id) ON DELETE CASCADE,
    PRIMARY KEY (session_id, tag_id)
);
CREATE INDEX ix_session_tags_tag ON session_tags (tag_id);

CREATE TABLE activity_tags (
    activity_id TEXT NOT NULL REFERENCES activities (id) ON DELETE CASCADE,
    tag_id      TEXT NOT NULL REFERENCES tags (id) ON DELETE CASCADE,
    PRIMARY KEY (activity_id, tag_id)
);

CREATE TABLE activity_notes (
    activity_id TEXT PRIMARY KEY REFERENCES activities (id) ON DELETE CASCADE,
    template    TEXT NOT NULL CHECK (length(template) BETWEEN 1 AND 500)
);

CREATE TABLE project_billing (
    project_id        TEXT PRIMARY KEY REFERENCES projects (id) ON DELETE CASCADE,
    budget_minutes    INTEGER CHECK (budget_minutes IS NULL OR budget_minutes BETWEEN 1 AND 6000000),
    hourly_rate_cents INTEGER CHECK (hourly_rate_cents IS NULL OR hourly_rate_cents BETWEEN 0 AND 100000000),
    billable          INTEGER NOT NULL DEFAULT 0 CHECK (billable IN (0, 1))
);
