-- OctaLedger schema, migration 0006: target working time and absences.
--
-- work_schedule: the target minutes per weekday, versioned by "valid from" so a change (for
--   example part-time from a date) never alters earlier balances. One row per start date.
-- absences: vacation, sick days, own holidays ... A whole absence day has target 0 unless
--   target_minutes says otherwise (for example a half holiday). Dates are local calendar dates.
--
-- Both tables are user data and part of the JSON backup (schema 3).
-- Migrations run inside one transaction each; do not put BEGIN/COMMIT in this file.

CREATE TABLE work_schedule (
    valid_from  TEXT PRIMARY KEY CHECK (valid_from GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    mon_minutes INTEGER NOT NULL CHECK (mon_minutes BETWEEN 0 AND 1440),
    tue_minutes INTEGER NOT NULL CHECK (tue_minutes BETWEEN 0 AND 1440),
    wed_minutes INTEGER NOT NULL CHECK (wed_minutes BETWEEN 0 AND 1440),
    thu_minutes INTEGER NOT NULL CHECK (thu_minutes BETWEEN 0 AND 1440),
    fri_minutes INTEGER NOT NULL CHECK (fri_minutes BETWEEN 0 AND 1440),
    sat_minutes INTEGER NOT NULL CHECK (sat_minutes BETWEEN 0 AND 1440),
    sun_minutes INTEGER NOT NULL CHECK (sun_minutes BETWEEN 0 AND 1440)
);

CREATE TABLE absences (
    id             TEXT PRIMARY KEY,
    start_date     TEXT NOT NULL CHECK (start_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    end_date       TEXT NOT NULL CHECK (end_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    kind           TEXT NOT NULL CHECK (kind IN ('vacation', 'sick', 'holiday_custom', 'other')),
    target_minutes INTEGER CHECK (target_minutes IS NULL OR target_minutes BETWEEN 0 AND 1440),
    note           TEXT CHECK (note IS NULL OR length(note) <= 500),
    CHECK (end_date >= start_date)
);
CREATE INDEX ix_absences_dates ON absences (start_date, end_date);
