"""Build the two filled pilot stories from their mutant shells.

Leaf-only fill: node bodies come from the authored BODIES dicts, choice labels
and ending titles are the skeleton's own templates with the book's theme binding
substituted, and the storybook title is rewritten (hence
``--allow-title-rewrite`` on the integrity check). Nothing structural is touched,
so ``check_fill_integrity`` compares like with like.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bodies_d  # noqa: E402
import bodies_s  # noqa: E402
from bindings import BINDING_D, BINDING_S, LABELS_D  # noqa: E402

_TOKEN = re.compile(r"\{([A-Z0-9_]+)\}")

SHELL_S = HERE / "out/the-midnight-museum-m1-s1/the-midnight-museum-m1-s1.json"
SHELL_D = HERE / (
    "out/the-midnight-museum-m4insertdecisionreconvergence-s7/"
    "the-midnight-museum-m4insertdecisionreconvergence-s7.json"
)

# Re-guidance resolutions that change a surface's meaning, not just its wording.
LABEL_OVERRIDES_S = {
    "c_panel_secret": "Follow the cold draught behind the pedestal.",
    "c_vault_grab": "Follow the cold draught at the back of the chamber.",
}
LABEL_OVERRIDES_D = LABELS_D


def _bind(text: str, binding: dict[str, str]) -> str:
    """Substitute every {SLOT} token in ``text`` from ``binding``."""
    out = _TOKEN.sub(lambda m: binding.get(m.group(1), m.group(0)), text)
    return out[:1].upper() + out[1:] if out else out


def build(
    shell_path: Path,
    bodies: dict[str, str],
    binding: dict[str, str],
    title: str,
    overrides: dict[str, str],
    out_path: Path,
) -> None:
    """Write one filled story from a mutant shell."""
    story = json.loads(shell_path.read_text(encoding="utf-8"))
    story["title"] = title
    for node in story["nodes"]:
        node["body"] = bodies[node["id"]]
        for choice in node.get("choices") or []:
            choice["label"] = overrides.get(
                choice["id"], _bind(choice["label"], binding)
            )
        ending = node.get("ending")
        if ending is not None:
            ending["title"] = _bind(ending["title"], binding)
    out_path.write_text(
        json.dumps(story, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    sys.stdout.write(f"wrote {out_path}\n")


if __name__ == "__main__":
    build(
        SHELL_S,
        bodies_s.BODIES,
        BINDING_S,
        bodies_s.TITLE,
        LABEL_OVERRIDES_S,
        HERE / "filled_S.json",
    )
    build(
        SHELL_D,
        bodies_d.BODIES,
        BINDING_D,
        bodies_d.TITLE,
        LABEL_OVERRIDES_D,
        HERE / "filled_D.json",
    )
