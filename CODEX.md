# CODEX.md — Agent Instructions for Codex

## Role
**RELEASE_GOVERNOR** — Task dispatch, accept/reject, merge decisions.

## Quality Gates to Enforce
- g1: All pytest tests pass
- g2: All source files compile (py_compile)
- g3: Parsed totals match expected (verified by tests)
- g5: Transaction count integrity

## Acceptance Criteria
- 3 PDFs parse with exact total matches
- 5 monthly Excel workbooks generated from template
- Streamlit UI functional with login-gated routed views
- Category assignment with manual override capability
- Internal transfers correctly flagged
