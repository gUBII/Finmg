-- Migration 003: Forecast tables (NSWTG Plan Sections D + E).
--
-- forecast_categories → reference list of Section D + E rows
-- forecasts → actual-vs-forecast per category per period, with Linda overrides
-- one_off_events → Section E rows surfaced from transactions or manually added

CREATE TABLE IF NOT EXISTS forecast_categories (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    section        TEXT    NOT NULL CHECK (section IN (
                       'D_income',
                       'D_expenditure',
                       'E_one_off_receipt',
                       'E_one_off_expenditure'
                   )),
    category_name  TEXT    NOT NULL,
    display_order  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (section, category_name)
);

CREATE INDEX IF NOT EXISTS idx_fc_section_order ON forecast_categories(section, display_order);

CREATE TABLE IF NOT EXISTS forecasts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    managed_person_id   INTEGER NOT NULL REFERENCES managed_persons(id) ON DELETE CASCADE,
    period_start        TEXT    NOT NULL,            -- ISO date
    period_end          TEXT    NOT NULL,
    category_id         INTEGER NOT NULL REFERENCES forecast_categories(id),
    actual_value        REAL,                        -- computed from transactions (trailing 12m)
    forecast_value      REAL,                        -- Linda's value, defaults to actual
    override_reason     TEXT,                        -- required if forecast_value != actual_value
    last_updated_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (managed_person_id, period_start, period_end, category_id)
);

CREATE INDEX IF NOT EXISTS idx_forecast_person_period ON forecasts(managed_person_id, period_start, period_end);

CREATE TABLE IF NOT EXISTS one_off_events (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    managed_person_id     INTEGER NOT NULL REFERENCES managed_persons(id) ON DELETE CASCADE,
    event_type            TEXT    NOT NULL CHECK (event_type IN ('receipt','expenditure')),
    event_description     TEXT    NOT NULL,
    status                TEXT    NOT NULL CHECK (status IN ('anticipated','proposed','completed')),
    amount                REAL,
    date_occurred         TEXT,                       -- ISO date, nullable until completed
    linked_transaction_id INTEGER REFERENCES transactions(id),
    notes                 TEXT,
    created_at            TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at            TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_one_off_person_status ON one_off_events(managed_person_id, status);
