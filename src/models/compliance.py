"""Dataclass DTOs for compliance + audit tables.

Section F (consultation), Section G (acknowledgements), submissions,
gifts (Appendix A B), notifications log, and the immutable audit log.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConsultationLogEntry:
    """A single recorded consultation. Section F + ongoing log."""
    managed_person_id: int
    date: str
    decision_topic: str
    id: int | None = None
    consulted_person_id: int | None = None
    summary: str | None = None
    attachments_json: str | None = None


@dataclass(frozen=True)
class Submission:
    """A Plan, Annual Accounts, or Change-in-Estate submission to NCAT."""
    managed_person_id: int
    type: str                                 # 'initial_plan'|'annual_accounts'|'change_in_estate'
    id: int | None = None
    trigger_subsection: str | None = None     # Appendix A row letter
    status: str = "draft"                     # 'draft'|'submitted'|'approved'|'rejected'
    generated_pdf_path: str | None = None
    generated_pdf_sha: str | None = None
    submitted_at: str | None = None
    submitted_by: str | None = None
    ncat_reference: str | None = None
    ncat_decision_at: str | None = None


@dataclass(frozen=True)
class Acknowledgement:
    """One of the 7 tickboxes on Section G."""
    submission_id: int
    ack_number: int                           # 1..7
    id: int | None = None
    ticked_at: str | None = None
    ticked_by: str | None = None


@dataclass(frozen=True)
class SubmissionAttachment:
    """A file attached to a submission (gift register, FMO copy, etc.)."""
    submission_id: int
    filename: str
    sha: str
    id: int | None = None
    description: str | None = None
    attached_at: str | None = None


@dataclass(frozen=True)
class Gift:
    """A planned or actual gift; checked against Act §76 at the service layer.

    Recipient identity is gift-owned (recipient_name + recipient_relation) and
    is deliberately NOT linked to significant_people — Section A.3 consultation
    contacts and gift recipients are independent lists.
    """
    managed_person_id: int
    id: int | None = None
    recipient_name: str | None = None
    recipient_relation: str | None = None
    occasion: str | None = None
    occasion_date: str | None = None
    planned_amount: float | None = None
    actual_amount: float | None = None
    actual_transaction_id: int | None = None
    section_76_assessment: str | None = None  # 'compliant'|'flagged'|'over_limit'
    notes: str | None = None


@dataclass(frozen=True)
class NotificationLogEntry:
    """A notification sent to a third party (bank, Centrelink, ATO)."""
    managed_person_id: int
    organisation_name: str
    id: int | None = None
    contact_method: str | None = None
    letter_template_used: str | None = None
    sent_at: str | None = None
    sent_by: str | None = None
    acknowledgement_received_at: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class AuditEntry:
    """One row in the immutable audit log.

    Once written, the audit_log_no_update / audit_log_no_delete triggers in
    004_compliance_tables.sql prevent mutation. Mutations of the underlying
    domain tables must always be paired with an AuditEntry insert via the
    service layer (S2+).
    """
    action: str                               # 'insert'|'update'|'delete'
    table_name: str
    id: int | None = None
    actor_user: str | None = None
    actor_role: str | None = None
    row_id: int | None = None
    before_json: str | None = None
    after_json: str | None = None
    reason: str | None = None
    timestamp: str | None = None


@dataclass(frozen=True)
class EstateChangeDetail:
    """The substance of one Change-in-Estate proposal (S8, migration 008).

    Pairs 1:1 with a `submissions` row of type 'change_in_estate' — the
    submission carries the Appendix-A letter, status lifecycle, and NCAT
    references; this carries what is actually proposed. `views_json` is a JSON
    array of {name, relationship, view} per form §9.1.
    """
    submission_id: int
    description: str
    id: int | None = None
    amount: float | None = None
    affordability_confirmed: bool = False
    views_json: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class ComplianceSetting:
    """Per-rule toggle for the compliance engine.

    `mode` is one of 'off' | 'warn' | 'enforce'. Default for every rule is
    'warn'; 'enforce' (hard-block at submission) is opt-in. `threshold_json`
    carries tunable params for forecast/anomaly rules (e.g. pacing percentage),
    stored as a JSON object string.
    """
    rule_key: str
    mode: str = "warn"                        # 'off'|'warn'|'enforce'
    threshold_json: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class FieldRationale:
    """A recorded reason an artifact field/section is intentionally blank (N/A).

    `field_key` may be a single PDF field name or a section/group key — group
    rationale is the default, field-level the exception.
    """
    artifact_key: str
    field_key: str
    managed_person_id: int
    rationale: str
    id: int | None = None
    recorded_by: str | None = None
    recorded_at: str | None = None
