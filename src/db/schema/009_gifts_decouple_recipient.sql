-- Migration 009: Decouple gifts from significant_people.
--
-- Gifts now own their recipient identity directly via recipient_name +
-- recipient_relation. The recipient_id FK into significant_people is removed
-- entirely: Section A.3 (significant_people = consultation contacts) and the
-- §76 gift ledger are independent surfaces — no shared lookup, no FK between
-- them. A gift recipient is no longer required to be a significant person.
--
-- SQLite cannot DROP a column that participates in a foreign key, so the table
-- is rebuilt. Nothing references gifts.id, so the rebuild is self-contained.
-- recipient_name / recipient_relation are backfilled from the legacy
-- "planned for <name> [ — <relation>]" string previously carried in notes.

ALTER TABLE gifts RENAME TO gifts_old;

CREATE TABLE gifts (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    managed_person_id        INTEGER NOT NULL REFERENCES managed_persons(id) ON DELETE CASCADE,
    recipient_name           TEXT,
    recipient_relation       TEXT,
    occasion                 TEXT    CHECK (occasion IN (
                                'birthday','christmas','easter',
                                'fathers_day','mothers_day','valentines',
                                'wedding','other'
                             ) OR occasion IS NULL),
    occasion_date            TEXT,
    planned_amount           REAL,
    actual_amount            REAL,
    actual_transaction_id    INTEGER REFERENCES transactions(id),
    section_76_assessment    TEXT    CHECK (section_76_assessment IN ('compliant','flagged','over_limit') OR section_76_assessment IS NULL),
    notes                    TEXT,
    created_at               TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at               TEXT    NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO gifts (
    id, managed_person_id, recipient_name, recipient_relation,
    occasion, occasion_date, planned_amount, actual_amount,
    actual_transaction_id, section_76_assessment, notes, created_at, updated_at
)
SELECT
    id,
    managed_person_id,
    -- recipient_name: the "planned for" tail, trimmed before any " — relation"
    CASE
        WHEN instr(notes, 'planned for ') > 0 THEN
            TRIM(
                CASE
                    WHEN instr(substr(notes, instr(notes, 'planned for ') + 12), ' — ') > 0
                        THEN substr(
                                substr(notes, instr(notes, 'planned for ') + 12),
                                1,
                                instr(substr(notes, instr(notes, 'planned for ') + 12), ' — ') - 1
                             )
                    ELSE substr(notes, instr(notes, 'planned for ') + 12)
                END
            )
        ELSE NULL
    END,
    -- recipient_relation: the text after the first " — " in the "planned for" tail
    CASE
        WHEN instr(notes, 'planned for ') > 0
             AND instr(substr(notes, instr(notes, 'planned for ') + 12), ' — ') > 0
            THEN TRIM(
                    substr(
                        substr(notes, instr(notes, 'planned for ') + 12),
                        instr(substr(notes, instr(notes, 'planned for ') + 12), ' — ') + 3
                    )
                 )
        ELSE NULL
    END,
    occasion, occasion_date, planned_amount, actual_amount,
    actual_transaction_id, section_76_assessment, notes, created_at, updated_at
FROM gifts_old;

DROP TABLE gifts_old;

CREATE INDEX IF NOT EXISTS idx_gifts_managed_person ON gifts(managed_person_id);
