# FinMg v3 — NCAT-Defensible Private Manager Dashboard

**Status:** PROPOSAL · 2026-06-08
**Author:** Claude (Implementation Lead) for Farhan
**Supersedes:** the implicit "monthly budget tool" framing of v2; preserves all v2 plumbing

---

## 1. Vision

> **Produce a complete, NCAT-defensible Private Manager's Plan that Linda can submit annually, where every dollar value is traceable to either bank data or a logged Linda input.**

The dashboard is not a budgeting app that incidentally helps with NCAT. It is a **regulatory submission system** that incidentally also produces a monthly budget Excel. Reframing the priorities collapses a lot of optionality and tells us what to build first.

### What we now know (post-2026-06-08)

- The prior Plan submission was a placeholder. Disability ticked, consultation "Yes", Linda's signature, and a handwritten gift table. Everything else blank — including the three ANZ accounts.
- NCAT has effectively zero estate inventory or forecast on file for Renato Gentili.
- Linda is the sole user. Ron is the subject. Farhan is the developer.
- All five reference docs (handbook, blank form, submitted plan, account mapping memory, financial-parse-verify rule) live in `data/reference_docs/` and project memory.

---

## 2. Build order — three phases, eight sprints

Numbered for tracking, sized so each sprint produces a working artefact even if subsequent ones slip.

### Phase 1 — First Real Submission (MVP)
**Goal:** Linda can produce a complete, signature-ready Private Manager's Plan PDF that NCAT will accept.

| # | Sprint | Outcome | Estimated effort |
|---|---|---|---|
| **S1** | Schema migration | New tables in place; existing transactions FK to accounts | 1–2 days |
| **S2** | Identity & contacts | Section A populated; Ron + Linda + significant people seeded from gift table | 2–3 days |
| **S3** | Estate inventory | Section B (accounts auto-populated, manual real estate/vehicles/investments) + Section C (debts) | 2–3 days |
| **S4** | Forecast engine + UI | Section D: trailing 12-month actuals per category, Linda overrides, reason audit | 3–5 days |
| **S5** | Submission generator | Fill the blank NSWTG PDF programmatically; produce signature-ready file + attachments index | 3–5 days |

**Phase 1 done = Linda can file the first real Plan.**

### Phase 2 — Day-to-Day Operations
**Goal:** Linda runs household finances inside the dashboard, with every action logged at NCAT-grade.

| # | Sprint | Outcome | Estimated effort |
|---|---|---|---|
| **S6** | Gifts ledger + Section 76 checker | Pre-populated from gift table; tracks actuals vs estimate; §76 reasonableness flag | 2–3 days |
| **S7** | One-off events + Consultation log | Section E populated automatically from large unusual transactions; Linda logs consultations keyed to significant people | 3–4 days |

### Phase 3 — Compliance Scaffolding
**Goal:** Everything NCAT might ask about under §116 is one click away.

| # | Sprint | Outcome | Estimated effort |
|---|---|---|---|
| **S8** | Change-in-Estate workflow + Audit log viewer + Annual accounts export | The 12 trigger types each render their Appendix-A subsection; immutable audit log of all mutations; annual lodgement export | 4–6 days |

**Total estimate:** ~3–5 weeks of focused dev time across all 8 sprints.

---

## 3. Data model (concrete tables)

### Keep as-is from v2

- `uploaded_pdfs` — source-file metadata + SHA hash
- `transactions` — raw transactions (adds `account_id` FK)
- `category_overrides` — manual category changes (existing audit)

### New tables (v3)

```sql
-- IDENTITY & CONTACTS (Section A)
managed_persons (
  id, surname, given_names, other_names, dob, address_line1,
  address_line2, postcode, email, phone, interpreter_required,
  interpreter_language, disability_flags (JSON: physical|brain_injury|...),
  has_will (yes|no|unsure), will_location, fmo_date, fmo_authority,
  d_and_a_reference, customer_reference_number
)

private_managers (
  id, managed_person_id (FK), surname, given_name, relationship,
  address_line1, address_line2, postcode, home_phone, mobile, email,
  appointment_type (sole|jointly|jointly_severally),
  remuneration_order_date  -- null unless Supreme Court order obtained
)

significant_people (
  id, managed_person_id (FK), surname, given_name, relationship,
  address_line1, address_line2, postcode, home_phone, mobile, email,
  consultation_status (active|estranged|deceased),
  notes
)

-- ESTATE INVENTORY (Section B + C)
accounts (
  id, managed_person_id (FK), institution, account_number, bsb,
  account_type (access|progress_saver|term_deposit|...),
  role_label (living|spending|savings),         -- our internal mapping
  ownership (sole|joint), inception_date,
  current_balance, balance_as_of_date,
  notes
)

real_estate (
  id, managed_person_id (FK), address, postcode,
  ownership (sole|joint_tenant|tenants_in_common),
  occupancy (managed_person|tenant|vacant), value, valuation_date
)

investments (
  id, managed_person_id (FK), type, description, ownership,
  units, amount, last_review_date
)

motor_vehicles (
  id, managed_person_id (FK), type, model, year, ownership, value
)

accommodation_bonds (
  id, managed_person_id (FK), facility_name, facility_address,
  date_of_entry, paid_unpaid, amount
)

debts_liabilities (
  id, managed_person_id (FK), lender, type, term, amount
)

-- FORECAST (Section D + E)
forecast_categories (
  id, section ('D_income'|'D_expenditure'|'E_one_off_receipt'|'E_one_off_expenditure'),
  category_name, display_order
)

forecasts (
  id, managed_person_id (FK), period_start, period_end,
  category_id (FK), actual_value, forecast_value,
  override_reason, last_updated_at
)

one_off_events (
  id, managed_person_id (FK), event_type (receipt|expenditure),
  event_description, status (anticipated|proposed|completed),
  amount, date_occurred,
  linked_transaction_id (FK, nullable) -- when surfaced from data
)

-- CONSULTATION + COMPLIANCE
consultation_log (
  id, managed_person_id (FK), date, consulted_person_id (FK significant_people),
  decision_topic, summary, attachments_json
)

acknowledgements (
  id, submission_id (FK), ack_number (1..7), ticked_at, ticked_by
)

submissions (
  id, managed_person_id (FK), type ('initial_plan'|'annual_accounts'|'change_in_estate'),
  trigger_subsection (A..R, nullable), status (draft|submitted|approved|rejected),
  generated_pdf_path, generated_pdf_sha, submitted_at, submitted_by,
  ncat_reference, ncat_decision_at
)

submission_attachments (
  id, submission_id (FK), filename, sha, description, attached_at
)

-- GIFTS (App.A B)
gifts (
  id, managed_person_id (FK), recipient_id (FK significant_people),
  occasion (birthday|christmas|easter|fathers_day|mothers_day|valentines|wedding|other),
  occasion_date, planned_amount, actual_amount, actual_transaction_id (FK, nullable),
  section_76_assessment ('compliant'|'flagged'|'over_limit')
)

-- NOTIFICATIONS (handbook §3 Step 4)
notifications_log (
  id, managed_person_id (FK), organisation_name, contact_method,
  letter_template_used, sent_at, sent_by, acknowledgement_received_at
)

-- IMMUTABLE AUDIT
audit_log (
  id, actor_user, actor_role, action, table_name, row_id,
  before_json, after_json, reason, timestamp
)
```

All FK referencing `managed_persons` (currently 1 row — Ron) is future-proofing for the multi-managed-person case. SQLite is fine for now per `[[project_finmg]]` memory.

---

## 4. UI module layout (top-level views)

Each is a new file under `src/views/` unless noted. The existing v2 views are kept and re-purposed.

| # | View | Maps to NSWTG Plan section | New / existing | Phase |
|---|---|---|---|---|
| 1 | `home.py` (was `dashboard.py`) | Status overview | Existing — repurpose | S1 |
| 2 | `identity.py` | Section A | NEW | S2 |
| 3 | `inventory.py` | Section B + C | NEW | S3 |
| 4 | `forecast.py` | Section D | NEW | S4 |
| 5 | `one_off.py` | Section E | NEW | S7 |
| 6 | `consultation.py` | Section F + standalone log | NEW | S7 |
| 7 | `gifts.py` | App.A B + ongoing ledger | NEW | S6 |
| 8 | `changes.py` | App.A C–R | NEW | S8 |
| 9 | `submission.py` | Section G + signature + PDF gen | NEW | S5 |
| 10 | `transactions.py` | Bookkeeping detail | Existing — enhance | S4 |
| 11 | `upload.py` | Bookkeeping input | Existing — enhance | S3 |
| 12 | `export.py` | Renato's budget Excel | Existing — repurpose | side-effect of S4 |
| 13 | `audit.py` | All NCAT-audit-relevant changes | NEW | S8 |
| 14 | `annual_accounts.py` | Handbook §5.4 | NEW | S8 |
| 15 | `notifications.py` | Handbook §3 Step 4 | NEW | S8 |

Sidebar nav grouped by purpose:
- **Submission preparation:** Identity, Inventory, Forecast, One-off, Consultation, Gifts, Changes, Submission
- **Day-to-day bookkeeping:** Home, Upload, Transactions, Export
- **Compliance:** Audit, Annual accounts, Notifications

---

## 5. New service layer (`src/services/`)

Functional, testable, no UI dependencies. Drives both the UI views and the export pipeline.

| Service | Responsibility |
|---|---|
| `forecast_engine.py` | trailing 12-month aggregates per Section D category → suggested forecast → Linda overrides → returns final forecast values + override audit |
| `submission_generator.py` | take the populated estate + forecast data, fill the blank NSWTG Plan PDF (or overlay onto template if it's not an AcroForm), produce signature-ready output |
| `compliance_checker.py` | gates submission — verifies all required fields are filled, all 7 acknowledgements ticked, signature date present, gift forecast within §76, etc. |
| `audit_logger.py` | decorator + context-manager pattern; every mutation funnels through this. Writes to `audit_log` table. |
| `notification_letter.py` | renders the Appendix-1 letter template per third party (bank, Centrelink, ATO, etc.) |
| `section76_checker.py` | for any proposed gift, checks against §76 — recipient relationship class, seasonal/event nature, amount-vs-estate-size ratio. |
| `inception_detector.py` | per-account first-transaction-date detection (handles the "card didn't exist until Aug 2025" case per `[[finmg-account-inception-dates]]`) |
| `oneoff_surfacer.py` | scans transactions for outliers (e.g. > $5,000 outside recurring pattern) and surfaces them for explicit one-off event capture |

---

## 6. Hard architectural calls (decisions made, not options)

| Question | Decision | Why |
|---|---|---|
| Frontend framework? | **Stay Streamlit.** | Complexity is in workflow/data, not UI flash. Streamlit handles forms + state + multi-page nav. |
| Storage? | **SQLite stays** at `data/finmg.db`. | Single-user, gitignored, WAL enabled, FK enforced. Postgres migration to Neon is in `[[project_finmg]]` as a *future* item, not blocking. |
| PDF generation? | **`pypdf` first, fall back to `reportlab` overlay** | If the NSWTG blank template is an AcroForm, pypdf fills directly. If not, reportlab overlays text on each page. We'll spike both in S5. |
| Auth? | **Keep existing SHA-256 single-user login** | Adequate for single-operator system. Add session-timeout if NCAT requires it later. |
| Multi-user? | **Out of scope for v3.** | Linda is sole operator. Multi-manager support is *modelled* in schema (private_managers can have N rows) but *not* exposed in UI yet. |
| Categories? | **Rebuild around Section D rows + Renato's monthly template** | Current categories were budget-focused; need to map to NSWTG categories (Section D) AND Renato's monthly Excel template. Many-to-one mapping in `categories.json`. |
| Tests? | **Keep pytest + extend coverage to services** | Existing 49 passing tests stay. New service files each get a test module. |
| Audit log immutability? | **Append-only table; no DELETE permitted via service layer** | Enforced in `audit_logger.py`. Direct DB access can still mutate but that's a "trusted operator" boundary. |
| File storage for attachments? | **`data/attachments/<submission_id>/<sha>.<ext>`** | Keep gitignored. SHA-based to dedup and detect tampering. |

---

## 7. What we keep, what we change, what we add

### Keep (from FinMg v2)

- `src/auth/auth.py` — login gate
- `src/db/database.py` — SQLite init
- `src/parser/pdf_extractor.py` and `header_parser.py` — PDF → transactions
- `src/pipeline/categoriser.py`, `merger.py`, `month_splitter.py`, `excel_writer.py` — existing categorisation + Excel output (still valuable; becomes ONE downstream of forecast data)
- `src/views/upload.py`, `transactions.py`, `export.py`, `login.py` — kept, enhanced

### Change

- `src/app.py` — sidebar nav restructured into the three groupings above
- `src/views/dashboard.py` → renamed `home.py`, becomes a "submission readiness" + monthly-overview view
- `src/db/queries.py` — extends to cover the new tables. Consider splitting into per-domain query modules (`queries_estate.py`, `queries_forecast.py`, etc.) once it grows.
- `src/config/categories.json` — extended to include Section D mapping per category

### Add

- `src/services/` (entire new directory — see §5)
- `src/views/identity.py`, `inventory.py`, `forecast.py`, `one_off.py`, `consultation.py`, `gifts.py`, `changes.py`, `submission.py`, `audit.py`, `annual_accounts.py`, `notifications.py`
- `src/db/schema/` (new schema migration files — runs once)
- `templates/letters/` — Appendix-1 notification letter template
- `templates/pfm_plan_blank.pdf` — reference to the NSWTG blank template (copy from `data/reference_docs/`)
- `tests/services/` and `tests/views/` matching new code

### Throw away

Nothing material. Everything in v2 maps cleanly to a v3 role.

---

## 8. Sprint 1 (S1) — what to build first

This is what I want green light for. Concrete.

### S1 deliverables

1. **`src/db/schema/002_estate_tables.sql`** — managed_persons, private_managers, significant_people, accounts, real_estate, investments, motor_vehicles, accommodation_bonds, debts_liabilities
2. **`src/db/schema/003_forecast_tables.sql`** — forecast_categories, forecasts, one_off_events
3. **`src/db/schema/004_compliance_tables.sql`** — consultation_log, acknowledgements, submissions, submission_attachments, gifts, notifications_log, audit_log
4. **`src/db/migrations.py`** — runs schemas in order; idempotent; backs up `finmg.db` before each new migration
5. **`src/models/estate.py`, `compliance.py`, `forecast.py`** — dataclass DTOs matching the tables
6. **`src/db/queries_estate.py`, `queries_compliance.py`, `queries_forecast.py`** — bare CRUD wrappers
7. **`tests/test_migrations.py`, `tests/test_estate_queries.py`** etc. — TDD per `[[feedback]]` and `tdd-workflow` rule
8. **Seed script** — populates Ron's managed_persons row + Linda's private_managers row + significant people derived from the gift table on `03_PFM_ron_submitted_plan.pdf` pages 16–17 + the three ANZ accounts
9. **Existing `transactions` table** — ALTER TABLE to add `account_id` FK; backfill from existing data (we know which file came from which account)

### S1 acceptance criteria

- `python3 -m pytest tests/` passes (49 existing + new tests)
- `python3 src/db/migrations.py` runs cleanly on a fresh DB and on the existing `finmg.db` without data loss
- `python3 scripts/seed.py` populates the new tables idempotently
- `sqlite3 data/finmg.db ".schema"` shows all new tables present and FK-correct
- Streamlit app still starts and the existing views still work

---

## 9. What I need from you before starting S1

1. **Green light on the v3 framing.** This rewrites the project's mission statement from "monthly budget app" to "NCAT submission system". If you'd rather narrow the scope (e.g. "just do the forecast view first, leave the submission generator for later"), say so now.

2. **The blank NSWTG Plan PDF as a template** — we already have it at `data/reference_docs/02_PFM_first_submission_template.pdf`. I'll spike whether it's an AcroForm in S5. No action from you needed unless you have a newer official template.

3. **Confirm the FMO + Directions and Authorities** are stored somewhere Linda can access — these go into `managed_persons` fields. If Linda has digital copies, drop them on Desktop; if not, we'll record what she remembers.

4. **Order question:** I'd recommend **S1 → S2 → S3 → S4 → S5** straight through to get to "first real submission" as fast as possible. Alternative is **S1 → S3 → S4** (skip Identity for now, do it last) — gets to a working forecast view a few days sooner but pushes the submission deliverable back. Your call.

---

## 10. Cross-references

- Reference docs: `data/reference_docs/01_PFM_handbook.md`, `02_PFM_first_submission_template.md`, `03_PFM_ron_submitted_plan.md`
- Existing project plan: `ProjectManagement.md` (v2 CSV ingestion plan — keep as historical context)
- Memory anchors: `[[finmg-purpose-ncat]]`, `[[finmg-account-mapping]]`, `[[user-operator]]`, `[[feedback-financial-parse-verify]]`, `[[finmg-account-inception-dates]]`
- Handbook quick-ref: §4.6 (gifts), §5.2 (bank accounts), §5.4 (annual lodgement), §6 (assets), Appendix 2 (when to use Change-in-Estate form)
