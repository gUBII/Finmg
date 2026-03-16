# IACP Message Templates

## Dispatch Template
```
[CODEX] → [CLAUDE]
TYPE: DISPATCH
TASK: <task_id>
DESCRIPTION: <what to do>
GATE: <which gate(s) apply>
DEADLINE: <if any>
---
<detailed instructions>
```

## Result Template
```
[CLAUDE] → [CODEX]
TYPE: RESULT
TASK: <task_id>
STATUS: COMPLETE | BLOCKED | PARTIAL
GATE: <gate results>
---
<summary of work done>
<any issues or notes>
```

## Verification Template
```
[GEMINI] → [CODEX]
TYPE: RESULT
TASK: verify_<task_id>
STATUS: PASS | FAIL
GATE: <gate tested>
---
<verification details>
<discrepancies if any>
```
