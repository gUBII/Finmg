"""Gap / audit engine.

Given an artifact spec + context, classify every data-bearing field as:

- ``filled``       — a resolver produced a value.
- ``gap``          — blank, and no rationale recorded → Linda must fill it or
                     record why it is N/A.
- ``rationalised`` — blank, but a rationale is on record (at the field key or the
                     section key) → an accepted N/A.

Noise control:
- Checkbox fields are informational, never gaps (blank just means "not ticked").
- Empty repeat-group rows are ignored (Ron having no investments is not 4 gaps).
  Only *present* rows (where the source returned data) contribute their columns.

Rationale capture writes ``artifact_field_rationales`` and an immutable
``audit_log`` entry, so every accepted N/A on an NCAT submission is traceable.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from src.db.queries_compliance import (
    insert_audit,
    list_field_rationales,
    upsert_field_rationale,
)
from src.models.compliance import AuditEntry, FieldRationale
from src.services.artifacts.fill import resolve_artifact
from src.services.artifacts.resolvers import Ctx, get_resolver
from src.services.artifacts.spec import ArtifactSpec, Section

GAP = "gap"
FILLED = "filled"
RATIONALISED = "rationalised"


@dataclass(frozen=True)
class SectionAudit:
    key: str
    title: str
    filled: int
    gaps: tuple[str, ...]
    rationalised: tuple[str, ...]

    @property
    def total(self) -> int:
        return self.filled + len(self.gaps) + len(self.rationalised)

    @property
    def completeness(self) -> float:
        """Fraction resolved (filled + rationalised both count as resolved)."""
        if self.total == 0:
            return 1.0
        return (self.filled + len(self.rationalised)) / self.total


@dataclass(frozen=True)
class AuditReport:
    artifact_key: str
    sections: tuple[SectionAudit, ...] = field(default_factory=tuple)

    @property
    def gaps(self) -> list[str]:
        return [g for s in self.sections for g in s.gaps]

    @property
    def total_fields(self) -> int:
        return sum(s.total for s in self.sections)

    @property
    def completeness(self) -> float:
        total = self.total_fields
        if total == 0:
            return 1.0
        resolved = sum(s.filled + len(s.rationalised) for s in self.sections)
        return resolved / total

    @property
    def is_complete(self) -> bool:
        return not self.gaps


def _present_row_count(group, ctx: Ctx) -> int:
    """How many rows the group's source actually yields (capped at max_rows)."""
    source_fn = get_resolver(group.source)
    rows = source_fn(ctx, **group.source_args) or []
    return min(len(rows), group.max_rows)


def _meaningful_fields(section: Section, ctx: Ctx) -> list[str]:
    """Gap-eligible field names: scalar bindings + scalar columns of present rows.

    Checkboxes and empty repeat rows are excluded.
    """
    out: list[str] = []
    for b in section.bindings:
        if b.type != "checkbox":
            out.append(b.field)
    for group in section.repeat_groups:
        present = _present_row_count(group, ctx)
        for i in range(1, present + 1):
            for col in group.columns:
                if col.type != "checkbox":
                    out.append(col.field_for_row(i))
    return out


def audit_artifact(
    conn: sqlite3.Connection, spec: ArtifactSpec, ctx: Ctx
) -> AuditReport:
    """Resolve the spec and classify every data field filled/gap/rationalised."""
    values, _blanks = resolve_artifact(spec, ctx)
    rationales = list_field_rationales(conn, spec.key, ctx.managed_person_id)
    rationalised_keys = {r.field_key for r in rationales}

    section_audits: list[SectionAudit] = []
    for section in spec.sections:
        section_rationalised = section.key in rationalised_keys
        filled = 0
        gaps: list[str] = []
        rationalised: list[str] = []
        for fname in _meaningful_fields(section, ctx):
            if fname in values:
                filled += 1
            elif fname in rationalised_keys or section_rationalised:
                rationalised.append(fname)
            else:
                gaps.append(fname)
        section_audits.append(
            SectionAudit(
                key=section.key,
                title=section.title,
                filled=filled,
                gaps=tuple(gaps),
                rationalised=tuple(rationalised),
            )
        )
    return AuditReport(artifact_key=spec.key, sections=tuple(section_audits))


def record_rationale(
    conn: sqlite3.Connection,
    artifact_key: str,
    field_key: str,
    managed_person_id: int,
    rationale: str,
    recorded_by: str | None = None,
) -> int:
    """Record (or replace) a rationale for an intentionally-blank field/section.

    `field_key` may be a single field name or a section key (a section-level
    rationale clears every gap in that section). Writes an audit_log entry.
    """
    reason = (rationale or "").strip()
    if not reason:
        raise ValueError("rationale must be non-empty")
    rid = upsert_field_rationale(
        conn,
        FieldRationale(
            artifact_key=artifact_key,
            field_key=field_key,
            managed_person_id=managed_person_id,
            rationale=reason,
            recorded_by=recorded_by,
        ),
    )
    insert_audit(
        conn,
        AuditEntry(
            action="insert",
            table_name="artifact_field_rationales",
            row_id=rid,
            actor_user=recorded_by,
            actor_role="private_manager",
            after_json=json.dumps(
                {"artifact_key": artifact_key, "field_key": field_key, "rationale": reason}
            ),
            reason=f"N/A rationale for {artifact_key}:{field_key}",
        ),
    )
    return rid
