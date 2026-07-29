#!/usr/bin/env python3
"""Guard the Mermaid ER diagram against schema drift and copy drift.

The ER diagram exists three times: ``er-diagram.puml`` (authoritative, carries
CHECK constraints and ON DELETE semantics), ``er-diagram.mmd``, and an inline
copy of the Mermaid source embedded in ``data-model.md`` so GitHub renders it
without opening the SVG. Two hand-maintained copies of the same content is a
drift hazard, and a diagram that silently disagrees with the schema is worse
than no diagram: it is read as documentation and trusted.

This script enforces the three properties that can be checked mechanically:

1. The embedded copy in ``data-model.md`` is byte-identical to ``.mmd``.
2. Every table, column, primary key and foreign-key marker in the Mermaid
   source matches SQLAlchemy's own metadata.
3. Every table and column in the PlantUML source matches it too.

Property 3 is newer than the other two, and it was added because calling the
.puml "authoritative" while checking only the .mmd is a contradiction the file
paid for: it silently accumulated three missing columns (``child_profile
.reduce_motion``, ``device_grant.expires_at``, ``story_request.interpretation``)
that the .mmd gate could not see. The .puml check is column NAMES only, not
types or PK/FK markers: its annotations are deliberately prose
(``<<FK family.id>>``, ``NULL``, bracketed commentary, embedded ``\\n`` line
breaks), and pinning that shape would make every readability edit a gate
failure. Names are the part that can silently disagree with the schema.

Deliberately NOT checked: relationship edges. The pure-attribution foreign keys
to ``user.id`` (``created_by``, ``updated_by``, ``approved_by``, ``changed_by``,
``assigned_by``, ``resolved_by``, ``consented_by_*``) are intentionally omitted
as edges to keep the graph readable; that omission is documented in the .puml
and in the .mmd header. Column-level FK markers ARE checked in the Mermaid
source, and those are present for the attribution columns.

Run: ``uv run python scripts/check_er_diagram.py``
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MMD = REPO_ROOT / "docs/architecture/diagrams/er-diagram.mmd"
PUML = REPO_ROOT / "docs/architecture/diagrams/er-diagram.puml"
DATA_MODEL = REPO_ROOT / "docs/architecture/data-model.md"

_ENTITY_OPEN = re.compile(r"^([a-z_]+)\s*\{$")
_MERMAID_BLOCK = re.compile(r"```mermaid\n(erDiagram\n.*?)\n```", re.DOTALL)
_PUML_ENTITY = re.compile(
    r'^entity "([a-z_]+)" as \w+[^{]*\{(.*?)^\}', re.DOTALL | re.MULTILINE
)
# A column line, after stripping the leading `*` NOT-NULL marker: an identifier
# followed by a colon. Constraint lines inside the same block start with an
# uppercase keyword (CHECK, UNIQUE, INDEX, ON DELETE) or a bare parenthesis, and
# continuation lines carry no colon, so none of them match.
_PUML_COLUMN = re.compile(r"^\s*\*?\s*([a-z][a-z0-9_]*)\s*:")


def parse_mermaid(source: str) -> dict[str, dict[str, str]]:
    """Map each entity to ``{column: marker string}`` from Mermaid ER source.

    Args:
        source: The Mermaid ``erDiagram`` body.

    Returns:
        Entity name -> column name -> the marker text (``PK``, ``FK``, or both).
    """
    entities: dict[str, dict[str, str]] = {}
    # Hold the open entity's own column map rather than its name, so the
    # "no entity is open" case is a None check rather than a dict lookup.
    current: dict[str, str] | None = None
    for raw in source.splitlines():
        line = raw.strip()
        opened = _ENTITY_OPEN.match(line)
        if opened:
            current = entities.setdefault(str(opened.group(1)), {})
            continue
        if line == "}":
            current = None
            continue
        if current is None or not line or line.startswith("%%"):
            continue
        # Drop the quoted comment: it is prose and may contain "FK" or "PK".
        parts = line.split('"')[0].strip().split()
        if len(parts) >= 2:
            current[parts[1]] = " ".join(parts[2:])
    return entities


def parse_puml(source: str) -> dict[str, set[str]]:
    """Map each PlantUML entity to its set of column names.

    Args:
        source: The full ``er-diagram.puml`` text.

    Returns:
        Entity name -> the column names declared inside that entity block.
        Constraint and index lines in the same block are excluded; see
        ``_PUML_COLUMN``.
    """
    return {
        name: {
            m.group(1)
            for line in body.splitlines()
            if (m := _PUML_COLUMN.match(line)) is not None
        }
        for name, body in _PUML_ENTITY.findall(source)
    }


def puml_problems(schema: dict[str, dict[str, tuple[bool, bool]]]) -> list[str]:
    """Compare the PlantUML entity/column names against the live schema.

    Args:
        schema: The mapping returned by :func:`schema_tables`.

    Returns:
        One message per disagreement; empty when the .puml is in sync.
    """
    drawn = parse_puml(PUML.read_text(encoding="utf-8"))
    problems: list[str] = []
    for table in sorted(set(schema) | set(drawn)):
        actual = schema.get(table)
        columns = drawn.get(table)
        if actual is None:
            problems.append(f"{table}: in er-diagram.puml but not in the ORM.")
            continue
        if columns is None:
            problems.append(f"{table}: an ORM table with no entity in er-diagram.puml.")
            continue
        if missing := sorted(set(actual) - columns):
            problems.append(f"{table}: columns missing from er-diagram.puml: {missing}")
        if phantom := sorted(columns - set(actual)):
            problems.append(
                f"{table}: columns in er-diagram.puml that the ORM lacks: {phantom}"
            )
    return problems


def schema_tables() -> dict[str, dict[str, tuple[bool, bool]]]:
    """Read the live schema from SQLAlchemy metadata.

    Returns:
        Table name -> column name -> ``(is_primary_key, is_foreign_key)``.
    """
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from cyo_adventure.db.models import Base  # noqa: PLC0415

    return {
        name: {c.name: (c.primary_key, bool(c.foreign_keys)) for c in table.columns}
        for name, table in Base.metadata.tables.items()
    }


def main() -> int:
    """Compare both Mermaid copies against each other and against the schema.

    Returns:
        0 when the diagram is in sync, 1 on any drift.
    """
    mermaid_source = MMD.read_text(encoding="utf-8")
    body = mermaid_source[mermaid_source.index("erDiagram") :].rstrip("\n")

    embedded = _MERMAID_BLOCK.search(DATA_MODEL.read_text(encoding="utf-8"))
    if embedded is None:
        print(
            f"No ```mermaid erDiagram block found in {DATA_MODEL.relative_to(REPO_ROOT)}."
        )
        return 1

    problems: list[str] = []
    if embedded.group(1).rstrip("\n") != body:
        problems.append(
            f"The Mermaid block embedded in {DATA_MODEL.relative_to(REPO_ROOT)} has drifted"
            f" from {MMD.relative_to(REPO_ROOT)}. They must be byte-identical; copy the"
            " .mmd body (everything from `erDiagram` onward) into the fenced block."
        )

    diagram = parse_mermaid(body)
    schema = schema_tables()

    for table in sorted(set(schema) | set(diagram)):
        actual = schema.get(table)
        drawn = diagram.get(table)
        if actual is None:
            problems.append(f"{table}: in the diagram but not in the ORM.")
            continue
        if drawn is None:
            problems.append(f"{table}: an ORM table with no entity in the diagram.")
            continue
        if missing := sorted(set(actual) - set(drawn)):
            problems.append(f"{table}: columns missing from the diagram: {missing}")
        if phantom := sorted(set(drawn) - set(actual)):
            problems.append(
                f"{table}: columns in the diagram that the ORM lacks: {phantom}"
            )
        for column in sorted(set(actual) & set(drawn)):
            is_pk, is_fk = actual[column]
            markers = drawn[column]
            if is_pk != ("PK" in markers):
                problems.append(
                    f"{table}.{column}: PK marker mismatch"
                    f" (ORM primary_key={is_pk}, diagram={'PK' in markers})."
                )
            if is_fk != ("FK" in markers):
                problems.append(
                    f"{table}.{column}: FK marker mismatch"
                    f" (ORM foreign_keys={is_fk}, diagram={'FK' in markers})."
                )

    problems.extend(puml_problems(schema))

    if problems:
        print("ER diagram drift detected:")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "\nUpdate docs/architecture/diagrams/er-diagram.mmd, mirror the change into"
            " the fenced block in docs/architecture/data-model.md, and keep"
            " er-diagram.puml (the authoritative source) in step. Re-render the SVG"
            " after a .puml edit: uv run python tools/generate_diagram_svgs.py."
        )
        return 1

    print(
        f"ER diagram OK: {len(schema)} tables match the ORM across the PlantUML source,"
        " and both Mermaid copies agree."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
