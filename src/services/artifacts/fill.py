"""Render an ArtifactSpec to a filled PDF (and report what was left blank).

`resolve_artifact` walks the spec, calling resolvers, and returns the
field→value map plus the list of fields left blank (the audit engine in P4
reuses this). `fill_artifact` writes those values into the template AcroForm via
pypdf and returns the PDF bytes.
"""

from __future__ import annotations

import io

import pypdf

from src.services.artifacts.resolvers import Ctx, get_resolver
from src.services.artifacts.spec import ArtifactSpec, Binding, Column
from dataclasses import dataclass


@dataclass(frozen=True)
class FilledArtifact:
    key: str
    pdf_bytes: bytes
    resolved: dict[str, str]      # field name → value written (non-blank only)
    blanks: list[str]             # field names whose resolver yielded nothing


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _apply_scalar(values, blanks, field_name, value) -> None:
    if _is_blank(value):
        blanks.append(field_name)
    else:
        values[field_name] = str(value)


def _apply_checkbox(values, blanks, field_name, truthy, on_state) -> None:
    if truthy:
        if not on_state:
            raise ValueError(f"checkbox {field_name!r} has no on_state")
        values[field_name] = on_state
    else:
        blanks.append(field_name)


def _resolve_binding(ctx: Ctx, b: Binding, values, blanks) -> None:
    fn = get_resolver(b.resolver)
    value = fn(ctx, **b.args)
    if b.type == "checkbox":
        _apply_checkbox(values, blanks, b.field, value, b.on_state)
    else:
        _apply_scalar(values, blanks, b.field, value)


def _resolve_column(ctx: Ctx, col: Column, field_name: str, values, blanks) -> None:
    fn = get_resolver(col.resolver)
    value = fn(ctx, **col.args)
    if col.type == "checkbox":
        _apply_checkbox(values, blanks, field_name, value, col.on_state)
    else:
        _apply_scalar(values, blanks, field_name, value)


def resolve_artifact(spec: ArtifactSpec, ctx: Ctx) -> tuple[dict[str, str], list[str]]:
    """Resolve all bindings → (field→value map, list of blank field names)."""
    values: dict[str, str] = {}
    blanks: list[str] = []

    for section in spec.sections:
        for binding in section.bindings:
            _resolve_binding(ctx, binding, values, blanks)

        for group in section.repeat_groups:
            source_fn = get_resolver(group.source)
            rows = source_fn(ctx, **group.source_args) or []
            for i in range(1, group.max_rows + 1):
                row = rows[i - 1] if (i - 1) < len(rows) else None
                row_ctx = ctx.with_row(row)
                for col in group.columns:
                    field_name = col.field_for_row(i)
                    if row is None:
                        blanks.append(field_name)
                    else:
                        _resolve_column(row_ctx, col, field_name, values, blanks)

    return values, blanks


def fill_artifact(spec: ArtifactSpec, ctx: Ctx) -> FilledArtifact:
    """Resolve the spec against `ctx` and fill the template AcroForm."""
    values, blanks = resolve_artifact(spec, ctx)

    reader = pypdf.PdfReader(str(spec.template_path))
    writer = pypdf.PdfWriter()
    writer.append(reader)
    # NeedAppearances so viewers render the filled values.
    writer.set_need_appearances_writer(True)
    for page in writer.pages:
        writer.update_page_form_field_values(page, values)

    buf = io.BytesIO()
    writer.write(buf)
    return FilledArtifact(
        key=spec.key,
        pdf_bytes=buf.getvalue(),
        resolved=values,
        blanks=blanks,
    )
