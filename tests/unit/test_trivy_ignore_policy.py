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


def _uncommented_source() -> str:
    """Return the policy with ``#`` comment lines removed."""
    return "\n".join(
        line
        for line in _policy_source().splitlines()
        if not line.lstrip().startswith("#")
    )


def _rule_bodies() -> list[str]:
    """Return every ``ignore`` rule body in the policy.

    Rego combines same-name rules with OR, so a second ``ignore`` rule is not
    a refinement of the first, it is an independent way for a finding to be
    suppressed. Returning all of them is what lets the callers assert on the
    policy as a whole rather than on whichever rule happens to appear first.

    Returns:
        One entry per ``ignore { ... }`` rule, in source order.
    """
    return re.findall(r"\bignore\s*\{(.*?)\}", _uncommented_source(), re.DOTALL)


def _rule_body() -> str:
    """Return the policy's single ``ignore`` rule body.

    Returns:
        The text between the ``ignore {`` opening brace and its closing brace.
    """
    bodies = _rule_bodies()
    assert len(bodies) == 1, f"expected exactly one `ignore` rule, found {len(bodies)}"
    return bodies[0]


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
    def test_policy_declares_exactly_one_ignore_rule(self) -> None:
        """A second `ignore` rule is a second, unreviewed way to suppress.

        Rego ORs same-name rules, so appending `ignore { input.Severity ==
        "HIGH" }` would silence every High finding in the image while each
        assertion about the first rule still passed. Every other structural
        test here inspects one rule body, so this is the test that makes those
        assertions mean anything about the policy as a whole.
        """
        assert len(_rule_bodies()) == 1

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

    @pytest.mark.unit
    def test_policy_carries_an_expiry(self) -> None:
        """A package-scoped rule with no date suppresses its package forever.

        Every `.trivyignore.yaml` entry self-expires, so a lapsed per-CVE
        acceptance returns to the gate on its own. Without this guard the
        package rule would not, leaving the scan silent after the documented
        acceptance ran out. Raised by Greptile on PR #725.
        """
        body = _rule_body()

        assert "time.now_ns()" in body
        assert "time.parse_rfc3339_ns(" in body

    @pytest.mark.unit
    def test_policy_expiry_matches_the_documented_entry(self) -> None:
        """The date Trivy enforces equals the date the document records."""
        document = (REPO_ROOT / "docs" / "known-vulnerabilities.md").read_text(
            encoding="utf-8"
        )

        expiry = re.search(
            r'time\.parse_rfc3339_ns\(\s*"(\d{4}-\d{2}-\d{2})T', _rule_body()
        )
        assert expiry is not None

        entry = document.split("## linux-libc-dev kernel UAPI headers", 1)[1]
        due = re.search(r"\| \*\*Reassessment Due\*\* \| (\d{4}-\d{2}-\d{2})", entry)
        assert due is not None

        assert expiry.group(1) == due.group(1)


@pytest.mark.skipif(
    shutil.which("trivy") is None,
    reason=(
        "trivy binary not on PATH; the CI unit-test job does not install it. "
        "Restoring this tier is tracked by UW-D33."
    ),
)
class TestPolicyEvaluation:
    """End-to-end evaluation through Trivy itself, where it is available."""

    @staticmethod
    def _convert(
        tmp_path: Path, *, with_policy: bool, policy: Path | None = None
    ) -> set[str]:
        """Run `trivy convert` over the fixture and return surviving CVE IDs.

        Args:
            tmp_path: pytest-provided scratch directory.
            with_policy: whether to apply an ignore policy at all.
            policy: policy file to apply; defaults to the repository's.

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
            command += ["--ignore-policy", str(policy or POLICY_PATH)]
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
    def test_lapsed_policy_stops_suppressing(self, tmp_path: Path) -> None:
        """Trivy honours the expiry itself, so the acceptance is self-limiting."""
        lapsed = tmp_path / "lapsed.rego"
        lapsed.write_text(
            _policy_source().replace(
                re.search(
                    r'time\.parse_rfc3339_ns\(\s*"(\d{4}-\d{2}-\d{2})T', _rule_body()
                ).group(1),
                "2020-01-01",
            ),
            encoding="utf-8",
        )

        surviving = self._convert(tmp_path, with_policy=True, policy=lapsed)

        assert _SUPPRESSED in surviving

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
