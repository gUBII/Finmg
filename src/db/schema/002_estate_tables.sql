-- Migration 002: Estate inventory tables (NSWTG Plan Sections A, B, C).
--
-- managed_persons  → Section A.1 (Ron)
-- private_managers → Section A.2 (Linda)
-- significant_people → Section A.3 (consultation contacts; gift recipients seed from here)
-- accounts → Section B.1 (the 3 ANZ accounts)
-- real_estate, investments, motor_vehicles, accommodation_bonds → Section B.2-B.5
-- debts_liabilities → Section C

CREATE TABLE IF NOT EXISTS managed_persons (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    surname                 TEXT    NOT NULL,
    given_names             TEXT    NOT NULL,
    other_names             TEXT,
    dob                     TEXT,                       -- ISO date
    address_line1           TEXT,
    address_line2           TEXT,
    postcode                TEXT,
    email                   TEXT,
    phone                   TEXT,
    interpreter_required    INTEGER NOT NULL DEFAULT 0, -- bool
    interpreter_language    TEXT,
    disability_flags        TEXT,                       -- JSON array, e.g. ["physical","brain_injury"]
    has_will                TEXT    CHECK (has_will IN ('yes','no','unsure') OR has_will IS NULL),
    will_location           TEXT,
    fmo_date                TEXT,                       -- ISO date NCAT issued the Financial Management Order
    fmo_authority           TEXT,                       -- e.g. "NCAT Guardianship Division"
    d_and_a_reference       TEXT,                       -- Directions and Authorities reference
    customer_reference_number TEXT,                     -- NSWTG CRN
    created_at              TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS private_managers (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    managed_person_id        INTEGER NOT NULL REFERENCES managed_persons(id) ON DELETE CASCADE,
    surname                  TEXT    NOT NULL,
    given_name               TEXT    NOT NULL,
    relationship             TEXT,                      -- e.g. "Lifelong partner"
    address_line1            TEXT,
    address_line2            TEXT,
    postcode                 TEXT,
    home_phone               TEXT,
    mobile                   TEXT,
    email                    TEXT,
    appointment_type         TEXT    CHECK (appointment_type IN ('sole','jointly','jointly_severally') OR appointment_type IS NULL),
    remuneration_order_date  TEXT,                      -- Supreme Court order, null unless obtained
    created_at               TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at               TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_pm_managed_person ON private_managers(managed_person_id);

CREATE TABLE IF NOT EXISTS significant_people (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    managed_person_id   INTEGER NOT NULL REFERENCES managed_persons(id) ON DELETE CASCADE,
    surname             TEXT    NOT NULL,
    given_name          TEXT    NOT NULL,
    relationship        TEXT,                           -- son, daughter-in-law, niece's child, etc.
    address_line1       TEXT,
    address_line2       TEXT,
    postcode            TEXT,
    home_phone          TEXT,
    mobile              TEXT,
    email               TEXT,
    consultation_status TEXT    CHECK (consultation_status IN ('active','estranged','deceased') OR consultation_status IS NULL) DEFAULT 'active',
    notes               TEXT,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_sp_managed_person ON significant_people(managed_person_id);

CREATE TABLE IF NOT EXISTS accounts (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    managed_person_id    INTEGER NOT NULL REFERENCES managed_persons(id) ON DELETE CASCADE,
    institution          TEXT    NOT NULL,            -- e.g. "ANZ"
    account_number       TEXT    NOT NULL UNIQUE,
    bsb                  TEXT,
    account_type         TEXT,                        -- "ACCESS ACCOUNT", "PROGRESS SAVER", etc.
    role_label           TEXT    CHECK (role_label IN ('living','spending','savings','other') OR role_label IS NULL),
    ownership            TEXT    CHECK (ownership IN ('sole','joint') OR ownership IS NULL) DEFAULT 'sole',
    inception_date       TEXT,                        -- ISO date; see [[finmg-account-inception-dates]]
    current_balance      REAL,
    balance_as_of_date   TEXT,
    notes                TEXT,
    created_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at           TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_acc_managed_person ON accounts(managed_person_id);

CREATE TABLE IF NOT EXISTS real_estate (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    managed_person_id   INTEGER NOT NULL REFERENCES managed_persons(id) ON DELETE CASCADE,
    address             TEXT    NOT NULL,
    postcode            TEXT,
    ownership           TEXT    CHECK (ownership IN ('sole','joint_tenant','tenants_in_common') OR ownership IS NULL),
    occupancy           TEXT    CHECK (occupancy IN ('managed_person','tenant','vacant') OR occupancy IS NULL),
    value               REAL,
    valuation_date      TEXT,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS investments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    managed_person_id   INTEGER NOT NULL REFERENCES managed_persons(id) ON DELETE CASCADE,
    type                TEXT,                       -- shares, term deposit, super, bond, etc.
    description         TEXT,
    ownership           TEXT,
    units               REAL,
    amount              REAL,
    last_review_date    TEXT,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS motor_vehicles (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    managed_person_id   INTEGER NOT NULL REFERENCES managed_persons(id) ON DELETE CASCADE,
    type                TEXT,
    model               TEXT,
    year                INTEGER,
    ownership           TEXT,
    value               REAL,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS accommodation_bonds (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    managed_person_id   INTEGER NOT NULL REFERENCES managed_persons(id) ON DELETE CASCADE,
    facility_name       TEXT,
    facility_address    TEXT,
    date_of_entry       TEXT,
    paid_unpaid         TEXT    CHECK (paid_unpaid IN ('paid','unpaid') OR paid_unpaid IS NULL),
    amount              REAL,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS debts_liabilities (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    managed_person_id   INTEGER NOT NULL REFERENCES managed_persons(id) ON DELETE CASCADE,
    lender              TEXT,
    type                TEXT,                       -- mortgage, credit card, personal loan, etc.
    term                TEXT,                       -- "25 years", "interest-only", etc.
    amount              REAL,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);
