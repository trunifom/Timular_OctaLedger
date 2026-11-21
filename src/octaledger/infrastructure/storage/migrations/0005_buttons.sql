-- OctaLedger schema, migration 0005: the cube's button.
--
-- 1. raw_events accepts the new kind 'button' (detail = 'short' or 'long'). SQLite cannot alter
--    a CHECK constraint, so the table is rebuilt and its rows are copied unchanged.
-- 2. device_buttons assigns an action to a button press per device. Without a row nothing
--    happens ("none" is the default), so the feature is off until the user chooses.
--
-- Migrations run inside one transaction each; do not put BEGIN/COMMIT in this file.

CREATE TABLE raw_events_new (
    id            TEXT PRIMARY KEY,
    device_id     TEXT NOT NULL REFERENCES devices (id) ON DELETE RESTRICT,
    kind          TEXT NOT NULL
                  CHECK (kind IN ('baseline', 'face_change', 'neutral',
                                  'disconnect', 'reconnect', 'invalid', 'button')),
    raw_value     INTEGER CHECK (raw_value IS NULL OR raw_value BETWEEN 0 AND 8),
    sequence      INTEGER NOT NULL CHECK (sequence >= 0),
    connection_id TEXT NOT NULL,
    received_at   TEXT NOT NULL,
    detail        TEXT
);
INSERT INTO raw_events_new (id, device_id, kind, raw_value, sequence, connection_id,
                            received_at, detail)
    SELECT id, device_id, kind, raw_value, sequence, connection_id, received_at, detail
    FROM raw_events;
DROP TABLE raw_events;
ALTER TABLE raw_events_new RENAME TO raw_events;
CREATE INDEX ix_raw_events_device_time ON raw_events (device_id, received_at);

CREATE TABLE device_buttons (
    device_id TEXT NOT NULL REFERENCES devices (id) ON DELETE CASCADE,
    press     TEXT NOT NULL CHECK (press IN ('short', 'long')),
    action    TEXT NOT NULL CHECK (action IN ('pause_resume', 'stop', 'start_last')),
    PRIMARY KEY (device_id, press)
);
