-- OctaLedger schema, migration 0002: small persistent application state.
--
-- Holds values that must survive a restart but are not business data, e.g. which tracker is
-- the active one and whether tracking is paused. Values are short UTF-8 text (JSON for
-- structured values). Migrations run inside one transaction each.

CREATE TABLE app_state (
    key        TEXT PRIMARY KEY CHECK (length(key) BETWEEN 1 AND 100),
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
