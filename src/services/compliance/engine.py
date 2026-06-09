"""Compliance engine — evaluate registered rules and grade findings by mode.

Each rule's effective mode comes from `compliance_settings` (default `warn`;
`enforce` is opt-in). `off` rules are skipped. `enforce` findings are the ones
that hard-block submission. Mode changes are written to the immutable audit_log.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from src.db.queries_compliance import (
    get_compliance_setting,
    insert_audit,
    upsert_compliance_setting,
)
from src.models.compliance import AuditEntry, ComplianceSetting
from src.services.compliance.rules import (
    Finding,
    Rule,
    RuleContext,
    all_rules,
    get_rule,
)

OFF = "off"
WARN = "warn"
ENFORCE = "enforce"
_VALID_MODES = {OFF, WARN, ENFORCE}
DEFAULT_MODE = WARN


@dataclass(frozen=True)
class GradedFinding:
    finding: Finding
    mode: str                       # effective mode (warn|enforce)
    kind: str = "state"             # 'state' | 'forecast' (from the rule)


@dataclass(frozen=True)
class ComplianceResult:
    graded: tuple[GradedFinding, ...]

    @property
    def blocking(self) -> list[GradedFinding]:
        """Findings under an `enforce` rule — these hard-block submission."""
        return [g for g in self.graded if g.mode == ENFORCE]

    @property
    def warnings(self) -> list[GradedFinding]:
        return [g for g in self.graded if g.mode == WARN]

    @property
    def state_findings(self) -> list[GradedFinding]:
        return [g for g in self.graded if g.kind == "state"]

    @property
    def forecast_findings(self) -> list[GradedFinding]:
        """Forward-looking early-warning findings (the 'forecast' panel)."""
        return [g for g in self.graded if g.kind == "forecast"]

    @property
    def is_blocked(self) -> bool:
        return bool(self.blocking)


def effective_mode(conn: sqlite3.Connection, rule_key: str) -> str:
    """The rule's current mode: the saved setting, else the default (warn)."""
    setting = get_compliance_setting(conn, rule_key)
    return setting.mode if setting is not None else DEFAULT_MODE


def _thresholds(conn: sqlite3.Connection, rule_key: str) -> dict:
    setting = get_compliance_setting(conn, rule_key)
    if setting is None or not setting.threshold_json:
        return {}
    try:
        return json.loads(setting.threshold_json)
    except (ValueError, TypeError):
        return {}


def evaluate_compliance(
    conn: sqlite3.Connection,
    managed_person_id: int,
    period_start: str | None = None,
    period_end: str | None = None,
    as_of: str | None = None,
    rules: list[Rule] | None = None,
) -> ComplianceResult:
    """Run every non-`off` rule and grade its findings by effective mode.

    `as_of` is the projection anchor for forecast rules (defaults to period_end).
    """
    rules = rules if rules is not None else all_rules()
    graded: list[GradedFinding] = []
    for rule in rules:
        mode = effective_mode(conn, rule.key)
        if mode == OFF:
            continue
        ctx = RuleContext(
            conn=conn,
            managed_person_id=managed_person_id,
            period_start=period_start,
            period_end=period_end,
            as_of=as_of,
            thresholds=_thresholds(conn, rule.key),
        )
        for finding in rule.evaluate(ctx):
            graded.append(GradedFinding(finding=finding, mode=mode, kind=rule.kind))
    return ComplianceResult(graded=tuple(graded))


def set_rule_mode(
    conn: sqlite3.Connection,
    rule_key: str,
    mode: str,
    recorded_by: str | None = None,
    threshold_json: str | None = None,
) -> None:
    """Persist a rule's toggle (off/warn/enforce) and audit the change."""
    if mode not in _VALID_MODES:
        raise ValueError(f"invalid mode {mode!r}; expected one of {sorted(_VALID_MODES)}")
    if get_rule(rule_key) is None:
        raise ValueError(f"unknown rule {rule_key!r}")
    previous = get_compliance_setting(conn, rule_key)
    upsert_compliance_setting(
        conn, ComplianceSetting(rule_key=rule_key, mode=mode, threshold_json=threshold_json)
    )
    insert_audit(
        conn,
        AuditEntry(
            action="update",
            table_name="compliance_settings",
            actor_user=recorded_by,
            actor_role="private_manager",
            before_json=json.dumps({"mode": previous.mode}) if previous else None,
            after_json=json.dumps({"mode": mode}),
            reason=f"compliance rule {rule_key} set to {mode}",
        ),
    )
