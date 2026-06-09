-- Migration 006: Compliance engine settings + artifact gap rationales.
--
-- compliance_settings      → per-rule toggle (off/warn/enforce) + tunable
--                            thresholds for forecast/anomaly rules. Default
--                            mode is 'warn'; 'enforce' is opt-in (hard-block at
--                            submission). One row per rule_key (upsert).
-- artifact_field_rationales → when an artifact field/section is intentionally
--                            blank (N/A), Linda records WHY here instead of
--                            filling it. `field_key` may be a single PDF field
--                            name OR a section/group key (group-level rationale
--                            is the default; field-level is the exception).

CREATE TABLE IF NOT EXISTS compliance_settings (
    rule_key        TEXT    PRIMARY KEY,
    mode            TEXT    NOT NULL CHECK (mode IN ('off','warn','enforce')) DEFAULT 'warn',
    threshold_json  TEXT,                       -- JSON object of tunable params, nullable
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS artifact_field_rationales (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    artifact_key        TEXT    NOT NULL,        -- 'annual_accounts' | 'plan' | ...
    field_key           TEXT    NOT NULL,        -- PDF field name OR section/group key
    managed_person_id   INTEGER NOT NULL REFERENCES managed_persons(id) ON DELETE CASCADE,
    rationale           TEXT    NOT NULL,
    recorded_by         TEXT,
    recorded_at         TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (artifact_key, field_key, managed_person_id)
);

CREATE INDEX IF NOT EXISTS idx_rationale_artifact_person
    ON artifact_field_rationales(artifact_key, managed_person_id);
