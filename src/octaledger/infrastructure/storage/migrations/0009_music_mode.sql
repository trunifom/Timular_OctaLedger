-- OctaLedger schema, migration 0009: the music mode of a cube.
--
-- A cube now has three roles: 'time', 'control' and 'music'. SQLite cannot change the CHECK
-- condition of devices.mode without rebuilding the table (which would cascade-delete everything
-- that references a device), so the music role is stored as mode 'control' plus this flag; the
-- application maps the pair back to the mode 'music'. Existing cubes keep their mode (flag 0).
--
-- Migrations run inside one transaction each; do not put BEGIN/COMMIT in this file.

ALTER TABLE devices
    ADD COLUMN music INTEGER NOT NULL DEFAULT 0 CHECK (music IN (0, 1));
