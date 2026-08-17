"""Tests for the Trivy package-scoped ignore policy.

``.trivy/ignore-policy.rego`` suppresses an entire package rather than a list
of CVE IDs, so the guards that keep it narrow are the only thing standing
between "one well-understood acceptance" and "a blanket silencer". These tests
pin both guards:

- the rule matches ``linux-libc-dev`` and nothing else, so the per-CVE
  acceptances in ``.trivyignore.yaml`` keep their own dates and review;
- the rule matches only findings with NO fixed version, so a
  ``linux-libc-dev`` CVE that Debian HAS fixed still fails the scan and
  prompts a base-image digest refresh (the CVE-2026-64530 / CVE-2026-64531
  case from issue #535, which a blanket package ignore would have hidden).

Two layers, because CI has no Trivy binary: the structural assertions always
run and catch the two ways this rule silently becomes a no-op, while the
end-to-end evaluation runs only where Trivy is installed.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Final

import pytest

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
POLICY_PATH: Final = REPO_ROOT / ".trivy" / "ignore-policy.rego"
CONFIG_PATH: Final = REPO_ROOT / "trivy.yaml"

# One finding per behaviour the policy has to get right.
_FIXTURE_FINDINGS: Final[list[dict[str, Any]]] = [
    {
        "VulnerabilityID": "CVE-2025-68174",
        "PkgName": "linux-libc-dev",
        "InstalledVersion": "6.12.101-1+dhi0",
        "Status": "affected",
        "Severity": "HIGH",
        "Title": "kernel: AMD KFD race condition",
    },
    {
        "VulnerabilityID": "CVE-2026-64530",
        "PkgName": "linux-libc-dev",
        "InstalledVersion": "6.12.96-1+dhi0",
        "FixedVersion": "6.12.100-1",
        "Status": "fixed",
        "Severity": "HIGH",
        "Title": "kernel: net/sched use-after-free (fix available)",
    },
    {
        "VulnerabilityID": "CVE-2026-42496",
        "PkgName": "perl-base",
        "InstalledVersion": "5.40.1-6",
        "Status": "affected",
        "Severity": "HIGH",
        "Title": "perl: bundled Archive::Tar",
    },
]

_SUPPRESSED: Final = "CVE-2025-68174"
_SURVIVES_FIXABLE: Final = "CVE-2026-64530"
_SURVIVES_OTHER_PKG: Final = "CVE-2026-42496"


def _policy_source() -> str:
    return POLICY_PATH.read_text(encoding="utf-8")


def _rule_body() -> str:
    """Return the policy's rule body, comments stripped.

    Returns:
        The text between the ``ignore {`` opening brace and its closing brace,
        with ``#`` comment lines removed so assertions read real Rego rather
        than the explanatory prose above it.
    """
    source = "\n".join(
        line
        for line in _policy_source().splitlines()
        if not line.lstrip().startswith("#")
    )
    match = re.search(r"\bignore\s*\{(.*?)\}", source, re.DOTALL)
    assert match is not None, "no `ignore { ... }` rule found in the policy"
    return match.group(1)


class TestPolicyStructure:
    """Assertions that hold with or without a Trivy binary on PATH."""

    @pytest.mark.unit
    def test_policy_and_config_exist(self) -> None:
        """Both halves of the wiring are present."""
        assert POLICY_PATH.is_file()
        assert CONFIG_PATH.is_file()

    @pytest.mark.unit
    def test_config_points_at_the_policy(self) -> None:
        """trivy.yaml references the policy by its real repo-relative path."""
        config = CONFIG_PATH.read_text(encoding="utf-8")
        assert "ignore-policy: .trivy/ignore-policy.rego" in config
        assert "ignorefile: .trivyignore.yaml" in config

    @pytest.mark.unit
    def test_scoped_to_linux_libc_dev_only(self) -> None:
        """The package guard names exactly one package."""
        body = _rule_body()
        assert 'input.PkgName == "linux-libc-dev"' in body

        packages = set(re.findall(r'input\.PkgName\s*==\s*"([^"]+)"', body))
        assert packages == {"linux-libc-dev"}

    @pytest.mark.unit
    def test_unfixed_guard_uses_absence_not_empty_string(self) -> None:
        """`not input.FixedVersion` is required; `== ""` is a silent no-op.

        ``FixedVersion`` is ``omitempty`` in Trivy's JSON, so a finding with no
        fix has no such key at all. Comparing it to the empty string never
        matches, which would suppress nothing while looking correct.
        """
        body = _rule_body()
        assert "not input.FixedVersion" in body
        assert 'input.FixedVersion == ""' not in body

    @pytest.mark.unit
    def test_uses_rego_v0_syntax(self) -> None:
        """Trivy 0.70 parses Rego v0; a v1 `if` keyword fails to load."""
        source = "\n".join(
            line
            for line in _policy_source().splitlines()
            if not line.lstrip().startswith("#")
        )
        assert re.search(r"^\s*ignore\s+if\s*\{", source, re.MULTILINE) is None
        assert (
            re.search(r"^\s*default\s+ignore\s*=\s*false", source, re.MULTILINE)
            is not None
        )

    @pytest.mark.unit
    def test_package_is_not_also_listed_per_cve(self) -> None:
        """`.trivyignore.yaml` must not re-enumerate what the policy now covers.

        Both mechanisms suppressing the same package would hide whether either
        one still works, and would resurrect the maintenance cost the policy
        exists to remove.
        """
        ignorefile = (REPO_ROOT / ".trivyignore.yaml").read_text(encoding="utf-8")
        document = (REPO_ROOT / "docs" / "known-vulnerabilities.md").read_text(
            encoding="utf-8"
        )

        suppressed = set(
            re.findall(r"^\s*-\s+id:\s*(CVE-\d{4}-\d+)", ignorefile, re.MULTILINE)
        )
        assert suppressed, "the ignore file parsed to no entries at all"

        # The consolidated entry's "CVEs Absorbed To Date" table is the record of
        # what the policy covers. No id may appear in both places.
        absorbed_section = document.split("### CVEs Absorbed To Date", 1)[1]
        absorbed = set(
            re.findall(
                r"(CVE-\d{4}-\d+)", absorbed_section.split("### References", 1)[0]
            )
        )
        assert absorbed, "the absorbed-CVE table parsed to nothing"

        assert suppressed.isdisjoint(absorbed)


@pytest.mark.skipif(shutil.which("trivy") is None, reason="trivy binary not on PATH")
class TestPolicyEvaluation:
    """End-to-end evaluation through Trivy itself, where it is available."""

    @staticmethod
    def _convert(tmp_path: Path, *, with_policy: bool) -> set[str]:
        """Run `trivy convert` over the fixture and return surviving CVE IDs.

        Args:
            tmp_path: pytest-provided scratch directory.
            with_policy: whether to apply the repository's ignore policy.

        Returns:
            The set of vulnerability IDs left in the converted report.
        """
        report = tmp_path / "report.json"
        report.write_text(
            json.dumps(
                {
                    "SchemaVersion": 2,
                    "ArtifactName": "cyo_adventure:scan",
                    "ArtifactType": "container_image",
                    "Results": [
                        {
                            "Target": "cyo_adventure:scan (debian 13.6)",
                            "Class": "os-pkgs",
                            "Type": "debian",
                            "Vulnerabilities": _FIXTURE_FINDINGS,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        command = ["trivy", "convert", "--format", "json"]
        if with_policy:
            command += ["--ignore-policy", str(POLICY_PATH)]
        command.append(str(report))

        completed = subprocess.run(
            command, capture_output=True, text=True, check=True, cwd=tmp_path
        )
        converted = json.loads(completed.stdout)
        return {
            vulnerability["VulnerabilityID"]
            for result in converted.get("Results", [])
            for vulnerability in (result.get("Vulnerabilities") or [])
        }

    @pytest.mark.unit
    def test_fixture_is_meaningful_without_the_policy(self, tmp_path: Path) -> None:
        """All three findings are present when the policy is not applied."""
        assert self._convert(tmp_path, with_policy=False) == {
            _SUPPRESSED,
            _SURVIVES_FIXABLE,
            _SURVIVES_OTHER_PKG,
        }

    @pytest.mark.unit
    def test_policy_suppresses_only_unfixed_kernel_headers(
        self, tmp_path: Path
    ) -> None:
        """The no-fix kernel-header finding goes; the other two remain."""
        surviving = self._convert(tmp_path, with_policy=True)

        assert _SUPPRESSED not in surviving
        assert _SURVIVES_FIXABLE in surviving
        assert _SURVIVES_OTHER_PKG in surviving
