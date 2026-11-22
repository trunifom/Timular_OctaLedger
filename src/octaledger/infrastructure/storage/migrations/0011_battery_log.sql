-- OctaLedger schema, migration 0011: the battery history of a cube (AP-52).
--
-- One row per stored reading (when the value changed, and at the latest every six hours), so the
-- interface can show the course and estimate the remaining time. Rows belong to the cube and go
-- with it; history older than 400 days is pruned by the application.
--
-- Migrations run inside one transaction each; do not put BEGIN/COMMIT in this file.

CREATE TABLE battery_log (
    device_id TEXT NOT NULL REFERENCES devices (id) ON DELETE CASCADE,
    at        TEXT NOT NULL,
    percent   INTEGER NOT NULL CHECK (percent BETWEEN 0 AND 100),
    PRIMARY KEY (device_id, at)
);
