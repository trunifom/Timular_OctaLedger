-- OctaLedger schema, migration 0013: read-outs of a cube (AP-56).
--
-- A snapshot is what one read-out returned: either the "data sheet" (every characteristic the cube
-- offers, with the raw value of the readable ones) or a short accelerometer recording. The list
-- of readings is kept as JSON in `payload` (a few kilobytes). Snapshots belong to the cube and go
-- with it; the application keeps the newest twenty per cube.
--
-- Migrations run inside one transaction each; do not put BEGIN/COMMIT in this file.

CREATE TABLE device_snapshots (
    id        TEXT PRIMARY KEY,
    device_id TEXT NOT NULL REFERENCES devices (id) ON DELETE CASCADE,
    taken_at  TEXT NOT NULL,
    kind      TEXT NOT NULL CHECK (kind IN ('datasheet', 'accelerometer')),
    payload   TEXT NOT NULL
);
CREATE INDEX ix_device_snapshots_device_time ON device_snapshots (device_id, taken_at);
