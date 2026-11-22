-- OctaLedger schema, migration 0012: a note on a job (AP-55).
--
-- With several cubes, two of them can address the same target at nearly the same moment, and a
-- new music title can replace the music of another cube. Both facts are written into this note
-- of the job (shown in the history as "Hinweis"), so nothing happens silently. Empty for every
-- job that had nothing to note, including all existing ones.
--
-- Migrations run inside one transaction each; do not put BEGIN/COMMIT in this file.

ALTER TABLE integration_jobs
    ADD COLUMN note TEXT;
