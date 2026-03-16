# IACP — Inter-Agent Communication Protocol

This project uses IACP for multi-agent collaboration between Claude, Gemini, and Codex.

## Protocol Files
- `PROTOCOL.md` — Message contract and communication format
- `ROLE_MATRIX.md` — Agent role assignments
- `TEMPLATES.md` — Dispatch and result message templates
- `GATES.md` — Quality gates (Python-adapted)

## Agent Roles
| Role | Agent | File |
|------|-------|------|
| IMPLEMENTATION_LEAD | Claude | CLAUDE.md |
| INDEPENDENT_VERIFIER | Gemini | GEMINI.md |
| RELEASE_GOVERNOR | Codex | CODEX.md |

## Communication
Agents communicate via the `handoff/` directory.
