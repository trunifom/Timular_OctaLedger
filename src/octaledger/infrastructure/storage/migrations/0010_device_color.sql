-- OctaLedger schema, migration 0010: the colour of a cube (AP-51).
--
-- Several cubes are told apart by number, name and colour. The colour is stored per cube; an empty
-- text means "not chosen yet": the application then shows the palette colour of the cube's number.
-- Existing cubes keep working unchanged.
--
-- Migrations run inside one transaction each; do not put BEGIN/COMMIT in this file.

ALTER TABLE devices
    ADD COLUMN color TEXT NOT NULL DEFAULT '';
