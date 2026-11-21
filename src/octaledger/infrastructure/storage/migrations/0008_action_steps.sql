-- OctaLedger schema, migration 0008: action chains (several steps per face).
--
-- face_action_steps holds every step of a face's chain (position 0 is the first). Existing
-- single actions are copied as step 0, so nothing changes for them. The table face_actions stays
-- as the mirror of step 0 (backups of older versions keep working, and a face without a row here
-- falls back to it).
--
-- integration_jobs learns which chain and step a job belongs to, so a new turn can cancel the
-- steps that were not sent yet and a failed step can cancel the ones after it.
--
-- Migrations run inside one transaction each; do not put BEGIN/COMMIT in this file.

CREATE TABLE face_action_steps (
    device_id         TEXT NOT NULL REFERENCES devices (id) ON DELETE CASCADE,
    face              INTEGER NOT NULL CHECK (face BETWEEN 1 AND 8),
    position          INTEGER NOT NULL CHECK (position BETWEEN 0 AND 9),
    integration_id    TEXT NOT NULL REFERENCES integrations (id) ON DELETE RESTRICT,
    label             TEXT NOT NULL CHECK (length(label) BETWEEN 1 AND 100),
    params            TEXT NOT NULL,
    delay_ms          INTEGER NOT NULL DEFAULT 0 CHECK (delay_ms BETWEEN 0 AND 300000),
    continue_on_error INTEGER NOT NULL DEFAULT 0 CHECK (continue_on_error IN (0, 1)),
    enabled           INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    condition         TEXT,
    PRIMARY KEY (device_id, face, position)
);

INSERT INTO face_action_steps (device_id, face, position, integration_id, label, params)
    SELECT device_id, face, 0, integration_id, label, params FROM face_actions;

ALTER TABLE integration_jobs ADD COLUMN chain_id TEXT;
ALTER TABLE integration_jobs ADD COLUMN step INTEGER NOT NULL DEFAULT 0;
ALTER TABLE integration_jobs ADD COLUMN continue_on_error INTEGER NOT NULL DEFAULT 0
    CHECK (continue_on_error IN (0, 1));
CREATE INDEX ix_jobs_chain ON integration_jobs (chain_id, step);
