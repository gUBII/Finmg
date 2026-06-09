"""Compliance rule registry — sourced from the NSWTG Private Manager's Handbook.

Each Rule has an `evaluate(ctx) -> list[Finding]` that inspects current DB state
(or, for `kind="forecast"`, projected data) and returns zero or more findings.
Rules carry a `handbook_ref` so every flag is traceable to the operating manual.

Modes (off/warn/enforce) are NOT stored on the rule — they live per-rule in
`compliance_settings` and are applied by `engine.py`. Default is `warn`.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

from src.db.queries_compliance import list_gifts
from src.db.queries_estate import (
    get_managed_person,
    list_accounts,
    list_investments,
)

STATE = "state"
FORECAST = "forecast"


@dataclass(frozen=True)
class RuleContext:
    conn: sqlite3.Connection
    managed_person_id: int
    period_start: str | None = None
    period_end: str | None = None
    as_of: str | None = None        # projection anchor for forecast rules (default: today/period_end)
    thresholds: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Finding:
    rule_key: str
    title: str
    detail: str
    handbook_ref: str
    subject: str | None = None      # the entity that triggered it (e.g. an account no.)


@dataclass(frozen=True)
class Rule:
    key: str
    title: str
    category: str                   # 'separation'|'gift'|'will'|'investment'|'cie'|'onboarding'
    handbook_ref: str
    evaluate: Callable[[RuleContext], list[Finding]]
    kind: str = STATE
    recommend_enforce: bool = False  # advisory only; default mode is still 'warn'


_REGISTRY: dict[str, Rule] = {}


def register(rule: Rule) -> Rule:
    if rule.key in _REGISTRY:
        raise ValueError(f"duplicate rule: {rule.key}")
    _REGISTRY[rule.key] = rule
    return rule


def all_rules() -> list[Rule]:
    return list(_REGISTRY.values())


def get_rule(key: str) -> Rule | None:
    return _REGISTRY.get(key)


# ---------------------------------------------------------------------------
# Rule evaluators
# ---------------------------------------------------------------------------

def _eval_account_separation(ctx: RuleContext) -> list[Finding]:
    """§5.2 — every account/investment must be held in the managed person's name
    alone (ownership 'sole'). A joint account is a comingling red flag."""
    out = []
    for acc in list_accounts(ctx.conn, ctx.managed_person_id):
        if acc.ownership and acc.ownership != "sole":
            out.append(Finding(
                rule_key="R-SEP-01",
                title="Account not held in managed person's name alone",
                detail=f"Account {acc.account_number} ({acc.institution}) has ownership "
                       f"'{acc.ownership}'. Handbook §5.2 requires sole ownership.",
                handbook_ref="§5.2",
                subject=acc.account_number,
            ))
    return out


def _eval_gift_section76(ctx: RuleContext) -> list[Finding]:
    """§4.6 / Act §76 — gifts must be reasonable and seasonal. Any gift assessed
    'flagged' or 'over_limit' needs attention."""
    out = []
    for g in list_gifts(ctx.conn, ctx.managed_person_id):
        if g.section_76_assessment in ("flagged", "over_limit"):
            amount = g.actual_amount if g.actual_amount is not None else g.planned_amount
            out.append(Finding(
                rule_key="R-GIFT-76",
                title=f"Gift may breach Act §76 ({g.section_76_assessment})",
                detail=f"Gift for occasion '{g.occasion}' of ${amount or 0:.2f} is "
                       f"assessed '{g.section_76_assessment}'. Confirm it is reasonable "
                       f"under Act §76 or seek NSWTG approval.",
                handbook_ref="§4.6",
                subject=str(g.id),
            ))
    return out


def _eval_will_safeguarded(ctx: RuleContext) -> list[Finding]:
    """§4.8 — the manager should safeguard the Will. If a Will exists but its
    location is unrecorded, or Will status is unknown, flag it."""
    mp = get_managed_person(ctx.conn, ctx.managed_person_id)
    if mp is None:
        return []
    if mp.has_will in (None, "unsure"):
        return [Finding(
            rule_key="R-WILL-01",
            title="Managed person's Will status unknown",
            detail="Whether the managed person has a Will is not recorded. The "
                   "manager should read and safeguard the Will (§4.8); its terms "
                   "affect estate decisions.",
            handbook_ref="§4.8",
        )]
    if mp.has_will == "yes" and not mp.will_location:
        return [Finding(
            rule_key="R-WILL-01",
            title="Will exists but its location is not recorded",
            detail="A Will exists but no safeguarding location is recorded. Record "
                   "where the Will is held (§4.8).",
            handbook_ref="§4.8",
        )]
    return []


def _eval_investment_review(ctx: RuleContext) -> list[Finding]:
    """§6.1 — investments must be reviewed at least annually."""
    out = []
    cutoff = None
    if ctx.period_end:
        try:
            cutoff = date.fromisoformat(ctx.period_end) - timedelta(days=365)
        except ValueError:
            cutoff = None
    for inv in list_investments(ctx.conn, ctx.managed_person_id):
        stale = inv.last_review_date is None
        if not stale and cutoff is not None:
            try:
                stale = date.fromisoformat(inv.last_review_date) < cutoff
            except (ValueError, TypeError):
                stale = True
        if stale:
            out.append(Finding(
                rule_key="R-INVEST-REVIEW",
                title="Investment not reviewed in the last 12 months",
                detail=f"Investment '{inv.description or inv.type}' has no review within "
                       f"12 months. §6.1 requires an annual review, confirmed when "
                       f"lodging accounts.",
                handbook_ref="§6.1",
                subject=str(inv.id),
            ))
    return out


def _eval_fmo_recorded(ctx: RuleContext) -> list[Finding]:
    """§2-§3 — no duties may commence until the FMO + Directions & Authorities
    are in place. Flag if those references are not recorded."""
    mp = get_managed_person(ctx.conn, ctx.managed_person_id)
    if mp is None:
        return []
    out = []
    if not mp.fmo_date:
        out.append(Finding(
            rule_key="R-FMO-01",
            title="Financial Management Order date not recorded",
            detail="The FMO date is not on file. It establishes the manager's "
                   "authority and the review/expiry timeline (§2).",
            handbook_ref="§2",
        ))
    if not mp.d_and_a_reference:
        out.append(Finding(
            rule_key="R-FMO-01",
            title="Directions & Authorities reference not recorded",
            detail="The Directions & Authorities document is the operational "
                   "permission set; no reference is recorded (§3 Step 2).",
            handbook_ref="§3",
        ))
    return out


def _eval_oneoff_needs_cie(ctx: RuleContext) -> list[Finding]:
    """§14 — one-off events that are anticipated/proposed may require a
    Change-in-Estate submission for NSWTG approval."""
    rows = ctx.conn.execute(
        "SELECT id, event_description, status, amount FROM one_off_events "
        "WHERE managed_person_id = ? AND status IN ('anticipated','proposed')",
        (ctx.managed_person_id,),
    ).fetchall()
    out = []
    for r in rows:
        out.append(Finding(
            rule_key="R-CIE-ONEOFF",
            title="One-off event may require a Change-in-Estate submission",
            detail=f"'{r['event_description']}' (${(r['amount'] or 0):.2f}, status "
                   f"{r['status']}) may be a §14 trigger requiring NSWTG approval "
                   f"before proceeding.",
            handbook_ref="§14",
            subject=str(r["id"]),
        ))
    return out


# ---------------------------------------------------------------------------
# Forecast / anomaly rules (kind="forecast") — flag trouble BEFORE it lands.
# Thresholds are tunable per rule via compliance_settings.threshold_json.
# ---------------------------------------------------------------------------

def _project_to_period(amount: float, period_start: str, as_of: str, period_end: str) -> float | None:
    """Linearly extrapolate `amount` accrued over [period_start, as_of] to the
    whole [period_start, period_end] window. None if the window is degenerate.
    """
    try:
        start = date.fromisoformat(period_start)
        anchor = date.fromisoformat(as_of)
        end = date.fromisoformat(period_end)
    except (TypeError, ValueError):
        return None
    days_elapsed = (anchor - start).days + 1
    period_days = (end - start).days + 1
    if days_elapsed <= 0 or period_days <= 0:
        return None
    return amount * period_days / days_elapsed


def _anchor(ctx: RuleContext) -> str | None:
    return ctx.as_of or ctx.period_end


def _sum_transactions(ctx: RuleContext, column: str, *, category: str | None, end: str) -> float:
    sql = (
        f"SELECT COALESCE(SUM({column}), 0) AS t FROM transactions "
        "WHERE COALESCE(is_internal_transfer, 0) = 0"
    )
    params: list = []
    if ctx.period_start:
        sql += " AND date >= ?"
        params.append(ctx.period_start)
    sql += " AND date <= ?"
    params.append(end)
    if category is not None:
        sql += " AND category = ?"
        params.append(category)
    return float(ctx.conn.execute(sql, params).fetchone()["t"] or 0.0)


def _eval_fc_gift_section76(ctx: RuleContext) -> list[Finding]:
    """Project gift spend to the period end and flag if it will breach the §76
    reasonableness ceiling before it actually does."""
    anchor = _anchor(ctx)
    if not (ctx.period_start and ctx.period_end and anchor):
        return []
    limit = float(ctx.thresholds.get("annual_limit", 1500.0))
    gifts = list_gifts(ctx.conn, ctx.managed_person_id)
    ytd = sum(
        (g.actual_amount if g.actual_amount is not None else (g.planned_amount or 0.0))
        for g in gifts
        if g.occasion_date and ctx.period_start <= g.occasion_date <= anchor
    )
    if ytd <= 0:
        return []
    projected = _project_to_period(ytd, ctx.period_start, anchor, ctx.period_end)
    if projected is not None and projected > limit:
        return [Finding(
            rule_key="R-FC-GIFT-76",
            title="Gifts projected to exceed the §76 reasonable limit",
            detail=f"${ytd:.2f} of gifts so far projects to ${projected:.2f} for the "
                   f"period, above the ${limit:.2f} ceiling. Slow gifting or seek "
                   f"NSWTG approval before the limit is reached (§4.6 / Act §76).",
            handbook_ref="§4.6",
        )]
    return []


def _eval_fc_category_overrun(ctx: RuleContext) -> list[Finding]:
    """For each forecast expenditure category, project actuals to period end and
    flag categories pacing over their forecast_value by more than the tolerance."""
    anchor = _anchor(ctx)
    if not (ctx.period_start and ctx.period_end and anchor):
        return []
    tol = float(ctx.thresholds.get("tolerance", 0.10))
    rows = ctx.conn.execute(
        "SELECT fc.category_name AS name, f.forecast_value AS fv "
        "FROM forecasts f JOIN forecast_categories fc ON fc.id = f.category_id "
        "WHERE f.managed_person_id = ? AND fc.section = 'D_expenditure' "
        "AND f.period_start = ? AND f.period_end = ? AND COALESCE(f.forecast_value,0) > 0",
        (ctx.managed_person_id, ctx.period_start, ctx.period_end),
    ).fetchall()
    out = []
    for r in rows:
        actual = _sum_transactions(ctx, "withdrawal", category=r["name"], end=anchor)
        if actual <= 0:
            continue
        projected = _project_to_period(actual, ctx.period_start, anchor, ctx.period_end)
        if projected is None:
            continue
        ceiling = r["fv"] * (1 + tol)
        if projected > ceiling:
            over_pct = (projected / r["fv"] - 1) * 100
            out.append(Finding(
                rule_key="R-FC-OVERRUN",
                title=f"'{r['name']}' pacing {over_pct:.0f}% over forecast",
                detail=f"${actual:.2f} spent so far projects to ${projected:.2f} vs a "
                       f"${r['fv']:.2f} forecast. Review the category or revise the "
                       f"forecast with a written reason.",
                handbook_ref="Plan §D",
                subject=r["name"],
            ))
    return out


def _eval_fc_drawdown(ctx: RuleContext) -> list[Finding]:
    """Project net cash flow; flag if the estate is on track to draw down beyond
    a threshold over the period (sustainability early-warning)."""
    anchor = _anchor(ctx)
    if not (ctx.period_start and ctx.period_end and anchor):
        return []
    limit = float(ctx.thresholds.get("drawdown_limit", 0.0))
    deposits = _sum_transactions(ctx, "deposit", category=None, end=anchor)
    withdrawals = _sum_transactions(ctx, "withdrawal", category=None, end=anchor)
    net = deposits - withdrawals
    if net >= 0:
        return []
    projected = _project_to_period(net, ctx.period_start, anchor, ctx.period_end)
    if projected is not None and projected < -abs(limit):
        return [Finding(
            rule_key="R-FC-DRAWDOWN",
            title="Estate projected to draw down over the period",
            detail=f"Net cash flow of ${net:.2f} so far projects to ${projected:.2f} "
                   f"for the period (spending outpacing income). Review sustainability "
                   f"and whether expenditure is within day-to-day authority.",
            handbook_ref="§4.5",
        )]
    return []


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register(Rule("R-SEP-01", "Account separation (sole name)", "separation", "§5.2",
              _eval_account_separation, recommend_enforce=True))
register(Rule("R-GIFT-76", "Gift within Act §76 limits", "gift", "§4.6",
              _eval_gift_section76, recommend_enforce=True))
register(Rule("R-WILL-01", "Will read and safeguarded", "will", "§4.8",
              _eval_will_safeguarded))
register(Rule("R-INVEST-REVIEW", "Annual investment review", "investment", "§6.1",
              _eval_investment_review))
register(Rule("R-FMO-01", "FMO + Directions & Authorities recorded", "onboarding", "§2",
              _eval_fmo_recorded))
register(Rule("R-CIE-ONEOFF", "One-off events flagged for Change-in-Estate", "cie", "§14",
              _eval_oneoff_needs_cie))

# Forecast / early-warning rules (kind="forecast")
register(Rule("R-FC-GIFT-76", "Projected gift §76 breach", "gift", "§4.6",
              _eval_fc_gift_section76, kind=FORECAST))
register(Rule("R-FC-OVERRUN", "Expenditure pacing over forecast", "forecast", "Plan §D",
              _eval_fc_category_overrun, kind=FORECAST))
register(Rule("R-FC-DRAWDOWN", "Estate drawdown projection", "forecast", "§4.5",
              _eval_fc_drawdown, kind=FORECAST))
