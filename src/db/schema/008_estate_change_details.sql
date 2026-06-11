-- Migration 008: Change-in-Estate workflow details (S8).
--
-- A Change-in-Estate proposal is a `submissions` row with
-- type='change_in_estate' and trigger_subsection = the Appendix-A letter
-- (A..R, registry in src/config/appendix_a.json). This table carries the
-- per-proposal substance the submissions row has no columns for: what is
-- proposed, how much it costs, whether Linda confirmed the estate can afford
-- it, and the recorded views of family / significant people (form §9.1).
--
-- One detail row per submission (UNIQUE submission_id); attachments reuse
-- submission_attachments; status lifecycle lives on submissions.status.

CREATE TABLE IF NOT EXISTS estate_change_details (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id            INTEGER NOT NULL UNIQUE REFERENCES submissions(id) ON DELETE CASCADE,
    description              TEXT    NOT NULL,
    amount                   REAL,
    affordability_confirmed  INTEGER NOT NULL DEFAULT 0,   -- 0/1 boolean
    views_json               TEXT,                          -- JSON array of {name, relationship, view}
    notes                    TEXT,
    created_at               TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at               TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_estate_change_submission
    ON estate_change_details(submission_id);
