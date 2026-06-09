"""P0 de-risk: prove pypdf can fill the NSWTG AcroForm templates and that
written values survive a save → re-read cycle with the AcroForm intact.

This is the load-bearing assumption under the whole artifact engine. If this
breaks (e.g. a pypdf upgrade changes fill semantics), the generator is unsafe.
"""

from __future__ import annotations

import io
from pathlib import Path

import pypdf
import pytest

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "nswtg"
PLAN = TEMPLATE_DIR / "plan.pdf"
ACCOUNTS = TEMPLATE_DIR / "annual_accounts.pdf"


def _first_text_field(reader: pypdf.PdfReader) -> str:
    """Return the name of the first /Tx (text) field in the form."""
    for name, meta in (reader.get_fields() or {}).items():
        if meta.get("/FT") == "/Tx":
            return name
    raise AssertionError("no text field found in template")


def _fill_and_reread(template: Path, values: dict[str, str]) -> dict:
    """Fill `values` into the template, save to bytes, re-read, return fields."""
    writer = pypdf.PdfWriter()
    reader = pypdf.PdfReader(str(template))
    writer.append(reader)
    for page in writer.pages:
        writer.update_page_form_field_values(page, values)
    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    return pypdf.PdfReader(buf).get_fields() or {}


@pytest.mark.skipif(not PLAN.exists(), reason="plan template not present")
def test_plan_template_is_acroform():
    reader = pypdf.PdfReader(str(PLAN))
    assert "/AcroForm" in reader.trailer["/Root"]
    assert len(reader.get_fields() or {}) == 603


@pytest.mark.skipif(not ACCOUNTS.exists(), reason="accounts template not present")
def test_accounts_template_is_acroform():
    reader = pypdf.PdfReader(str(ACCOUNTS))
    assert "/AcroForm" in reader.trailer["/Root"]
    assert len(reader.get_fields() or {}) == 250


@pytest.mark.skipif(not PLAN.exists(), reason="plan template not present")
def test_plan_roundtrip_value_persists():
    reader = pypdf.PdfReader(str(PLAN))
    field = _first_text_field(reader)
    fields = _fill_and_reread(PLAN, {field: "GENTILI"})
    assert fields[field]["/V"] == "GENTILI"
    # AcroForm survived the write.
    assert len(fields) == 603


@pytest.mark.skipif(not ACCOUNTS.exists(), reason="accounts template not present")
def test_accounts_roundtrip_value_persists():
    reader = pypdf.PdfReader(str(ACCOUNTS))
    field = _first_text_field(reader)
    fields = _fill_and_reread(ACCOUNTS, {field: "RENATO"})
    assert fields[field]["/V"] == "RENATO"
    assert len(fields) == 250


@pytest.mark.skipif(not ACCOUNTS.exists(), reason="accounts template not present")
def test_unrelated_fields_stay_blank_after_fill():
    """Filling one field must not perturb the others."""
    reader = pypdf.PdfReader(str(ACCOUNTS))
    field = _first_text_field(reader)
    fields = _fill_and_reread(ACCOUNTS, {field: "RENATO"})
    others_with_value = [
        k for k, v in fields.items() if k != field and v.get("/V")
    ]
    assert others_with_value == []
