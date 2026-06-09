"""Artifact spec: load a declarative field map from JSON into frozen DTOs.

A spec lives at `src/config/artifacts/<key>.json` and describes how to fill one
NSWTG AcroForm PDF. Structure (data only — no logic):

    {
      "key": "annual_accounts",
      "title": "Private Manager Accounts",
      "template": "templates/nswtg/annual_accounts.pdf",
      "sections": [
        {
          "key": "A_personal",
          "title": "Section A — Personal information",
          "bindings": [
            {"field": "SurnameRow1", "type": "scalar",
             "resolver": "managed_person", "args": {"column": "surname"}},
            {"field": "undefined", "type": "checkbox", "on_state": "/On",
             "resolver": "managed_person_truthy", "args": {"column": "interpreter_required"}}
          ],
          "repeat_groups": [
            {
              "source": "accounts", "max_rows": 5,
              "columns": [
                {"field_template": "Name of financial institutionRow{i}",
                 "resolver": "attr", "args": {"name": "institution"}},
                {"field_template": "BSBRow{i}", "resolver": "attr", "args": {"name": "bsb"}}
              ]
            }
          ]
        }
      ]
    }

Each binding/column names a `resolver` key (looked up in `resolvers.py`) plus
`args`. Logic stays in Python; the map stays diffable JSON.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ARTIFACT_CONFIG_DIR = REPO_ROOT / "src" / "config" / "artifacts"


@dataclass(frozen=True)
class Binding:
    """A single AcroForm field bound to a resolver."""
    field: str
    resolver: str
    type: str = "scalar"                  # 'scalar' | 'checkbox'
    args: dict = field(default_factory=dict)
    on_state: str | None = None           # required when type == 'checkbox'


@dataclass(frozen=True)
class Column:
    """One column of a repeating row-set.

    Field naming per row is either a `field_template` containing `{i}` (1-based
    row index) or an explicit `fields` list (one PDF field name per row) for
    forms with irregular naming.
    """
    resolver: str
    args: dict = field(default_factory=dict)
    type: str = "scalar"                  # 'scalar' | 'checkbox'
    field_template: str | None = None
    fields: tuple[str, ...] | None = None
    on_state: str | None = None

    def field_for_row(self, i: int) -> str:
        """Return the PDF field name for 1-based row index `i`."""
        if self.field_template is not None:
            return self.field_template.format(i=i)
        if self.fields is not None:
            return self.fields[i - 1]
        raise ValueError("Column needs field_template or fields")


@dataclass(frozen=True)
class RepeatGroup:
    """A repeating row-set (e.g. up to 5 bank-account rows)."""
    source: str                           # resolver returning a list of row objects
    max_rows: int
    columns: tuple[Column, ...]
    source_args: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    bindings: tuple[Binding, ...] = ()
    repeat_groups: tuple[RepeatGroup, ...] = ()


@dataclass(frozen=True)
class ArtifactSpec:
    key: str
    title: str
    template: str                         # path relative to repo root
    sections: tuple[Section, ...]

    @property
    def template_path(self) -> Path:
        return REPO_ROOT / self.template


def _column(d: dict) -> Column:
    return Column(
        resolver=d["resolver"],
        args=d.get("args", {}),
        type=d.get("type", "scalar"),
        field_template=d.get("field_template"),
        fields=tuple(d["fields"]) if d.get("fields") else None,
        on_state=d.get("on_state"),
    )


def _repeat_group(d: dict) -> RepeatGroup:
    return RepeatGroup(
        source=d["source"],
        source_args=d.get("source_args", {}),
        max_rows=int(d["max_rows"]),
        columns=tuple(_column(c) for c in d["columns"]),
    )


def _section(d: dict) -> Section:
    return Section(
        key=d["key"],
        title=d.get("title", d["key"]),
        bindings=tuple(
            Binding(
                field=b["field"],
                resolver=b["resolver"],
                type=b.get("type", "scalar"),
                args=b.get("args", {}),
                on_state=b.get("on_state"),
            )
            for b in d.get("bindings", [])
        ),
        repeat_groups=tuple(_repeat_group(g) for g in d.get("repeat_groups", [])),
    )


def parse_spec(data: dict) -> ArtifactSpec:
    """Build an ArtifactSpec from a parsed JSON dict."""
    return ArtifactSpec(
        key=data["key"],
        title=data["title"],
        template=data["template"],
        sections=tuple(_section(s) for s in data.get("sections", [])),
    )


def load_spec(key: str, config_dir: Path = ARTIFACT_CONFIG_DIR) -> ArtifactSpec:
    """Load and parse `<config_dir>/<key>.json`."""
    path = config_dir / f"{key}.json"
    if not path.exists():
        raise FileNotFoundError(f"artifact spec not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return parse_spec(data)
