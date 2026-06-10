-- 007 — one_off_dismissals: Section E candidate triage.
--
-- The one-off detector (src/services/one_off.py) surfaces large unusual
-- transactions as candidate Section E events. When Linda reviews one and
-- decides it is NOT a one-off event, the dismissal is recorded here so the
-- detector stops resurfacing it. Confirmed candidates instead become
-- one_off_events rows (linked via linked_transaction_id).

CREATE TABLE IF NOT EXISTS one_off_dismissals (
    transaction_id INTEGER PRIMARY KEY REFERENCES transactions(id) ON DELETE CASCADE,
    reason         TEXT,
    recorded_by    TEXT,
    recorded_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
