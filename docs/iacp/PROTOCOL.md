# IACP Protocol — Message Contract

## Message Format
```
[AGENT_NAME] → [TARGET_AGENT]
TYPE: DISPATCH | RESULT | QUERY | ACK
GATE: g1 | g2 | g3 | g5 (if applicable)
TIMESTAMP: ISO 8601
---
Body content
```

## Message Types
- **DISPATCH**: Task assignment from Governor to agent
- **RESULT**: Completed work from agent to Governor
- **QUERY**: Question between agents
- **ACK**: Acknowledgement of receipt

## Flow
1. Codex (Governor) dispatches tasks
2. Claude (Lead) implements and reports results
3. Gemini (Verifier) independently validates
4. Codex accepts or rejects based on gate results
