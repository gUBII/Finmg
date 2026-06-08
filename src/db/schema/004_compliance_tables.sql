-- Migration 004: Compliance + audit tables.
--
-- consultation_log → Section F + ongoing log of consultations with significant people
-- acknowledgements → Section G — the 7 ticked boxes
-- submissions → annual Plan, Change-in-Estate, Annual Accounts artefacts
-- submission_attachments → SHA-tracked file references for each submission
-- gifts → Appendix A B + ongoing gift ledger with §76 checks
-- notifications_log → Handbook §3 Step 4 (notifying banks/Centrelink/ATO)
-- audit_log → immutable append-only mutation log; enforced by triggers below

CREATE TABLE IF NOT EXISTS consultation_log (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    managed_person_id    INTEGER NOT NULL REFERENCES managed_persons(id) ON DELETE CASCADE,
    date                 TEXT    NOT NULL,
    consulted_person_id  INTEGER REFERENCES significant_people(id),
    decision_topic       TEXT    NOT NULL,
    summary              TEXT,
    attachments_json     TEXT,                       -- JSON array of attachment_id strings
    created_at           TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_consult_person_date ON consultation_log(managed_person_id, date);

CREATE TABLE IF NOT EXISTS submissions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    managed_person_id   INTEGER NOT NULL REFERENCES managed_persons(id) ON DELETE CASCADE,
    type                TEXT    NOT NULL CHECK (type IN ('initial_plan','annual_accounts','change_in_estate')),
    trigger_subsection  TEXT,                        -- Appendix A row letter (A..R), nullable
    status              TEXT    NOT NULL CHECK (status IN ('draft','submitted','approved','rejected')) DEFAULT 'draft',
    generated_pdf_path  TEXT,
    generated_pdf_sha   TEXT,
    submitted_at        TEXT,
    submitted_by        TEXT,
    ncat_reference      TEXT,
    ncat_decision_at    TEXT,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_submission_person_type ON submissions(managed_person_id, type);

CREATE TABLE IF NOT EXISTS acknowledgements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id   INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    ack_number      INTEGER NOT NULL CHECK (ack_number BETWEEN 1 AND 7),
    ticked_at       TEXT,
    ticked_by       TEXT,
    UNIQUE (submission_id, ack_number)
);

CREATE TABLE IF NOT EXISTS submission_attachments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id   INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    filename        TEXT    NOT NULL,
    sha             TEXT    NOT NULL,
    description     TEXT,
    attached_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS gifts (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    managed_person_id        INTEGER NOT NULL REFERENCES managed_persons(id) ON DELETE CASCADE,
    recipient_id             INTEGER REFERENCES significant_people(id),
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

CREATE INDEX IF NOT EXISTS idx_gifts_person_recipient ON gifts(managed_person_id, recipient_id);

CREATE TABLE IF NOT EXISTS notifications_log (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    managed_person_id          INTEGER NOT NULL REFERENCES managed_persons(id) ON DELETE CASCADE,
    organisation_name          TEXT    NOT NULL,
    contact_method             TEXT,                  -- email, letter, phone, in-person
    letter_template_used       TEXT,
    sent_at                    TEXT,
    sent_by                    TEXT,
    acknowledgement_received_at TEXT,
    notes                      TEXT,
    created_at                 TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Immutable append-only audit log. Triggers below prevent UPDATE / DELETE.
CREATE TABLE IF NOT EXISTS audit_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user   TEXT,
    actor_role   TEXT,                                -- 'private_manager', 'system', etc.
    action       TEXT    NOT NULL,                    -- 'insert', 'update', 'delete'
    table_name   TEXT    NOT NULL,
    row_id       INTEGER,
    before_json  TEXT,
    after_json   TEXT,
    reason       TEXT,
    timestamp    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_table_row ON audit_log(table_name, row_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);

CREATE TRIGGER IF NOT EXISTS audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only; UPDATE not permitted');
END;

CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only; DELETE not permitted');
END;
