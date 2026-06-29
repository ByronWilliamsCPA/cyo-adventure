---
title: "Snyk Implementation Findings and Recommendations"
schema_type: common
status: draft
owner: core-maintainer
purpose: "Report for the .claude/template team on how Snyk is currently scanning CYO Adventure, why the IDE panel over-reports, and how the standardized Snyk implementation should change."
tags:
  - security
  - dependencies
  - tooling
  - template
  - feedback
---

## Executive summary

The Snyk VS Code extension currently reports ~202 issues for this repository
(192 Open Source, 10 Code), with a separate summary box showing "33 issues, 8
fixable." Investigation shows that **the Open Source number is almost entirely
noise** caused by Snyk scanning the on-disk working tree (including `.venv/` and
`.worktrees/`) instead of the project's real dependency manifests. When scoped
to the actual lockfiles, the genuine open-source vulnerability count is currently
**zero** in both ecosystems.

The 10 Code (SAST) findings are real project files, but a meaningful share are
guard-unaware false positives or test fixtures rather than exploitable defects.

The core problem is not the codebase; it is **Snyk scope and configuration**.
This report is aimed at the team revising the standardized Snyk implementation,
because the fix belongs in the template, not in any one project.

### Headline numbers

| Surface | Snyk IDE panel | Reality (lockfile-scoped) |
| --- | --- | --- |
| Open Source (npm, real) | counted in the 192 | `npm audit` = **0 vulnerabilities** |
| Open Source (Python, real) | counted in the 192 | `osv-scanner uv.lock` (248 pkgs) = **0 issues** |
| Open Source (`.venv` + `.worktrees`) | bulk of the 192 | not project dependencies; should not be scanned |
| Code / SAST | 10 | 10 real files; several false positives (see Finding 3) |

## How this was gathered

- Environment: WSL2 Ubuntu 24.04, repo at `/home/byron/dev/CYO_Adventure`, branch `main`.
- Tool versions present on PATH: `osv-scanner 2.3.0`, `snyk 1.1305.2`, `uv 0.9.26`,
  `npm 11.11.0`, `trivy 0.52.2`.
- Snyk org shown in panel: `williaby`. Several Open Source rows are labeled
  `staging`, which is a path artifact, not a Snyk target (see Finding 1).

## Finding 1 (root cause): Snyk Open Source scans the filesystem, not the manifests

The repeated panel rows reading `package.json  staging - 15 vulnerabilities`
do not point at a project manifest. They resolve to JupyterLab's bundled build
artifact inside the Python virtual environment:

```text
.venv/lib/python3.14/site-packages/jupyterlab/staging/package.json
   -> "name": "@jupyterlab/application-top", "version": "4.6.0"
```

That manifest carries its own large npm tree (rspack, webpack, codemirror), which
Snyk resolves and reports 15 vulnerabilities against. The same file is then counted
again for every duplicate copy on disk.

Evidence:

- `find . -name package.json | wc -l` returns **1144** files on disk.
- Exactly **one** is a project manifest: `frontend/package.json`. Everything else
  is a Python venv's vendored JS, a worktree duplicate, or a build artifact.
- The duplicated worktree checkouts each carry their own `.venv` and `frontend/`,
  multiplying identical findings:
  `.worktrees/fix-pr26/.venv/.../jupyterlab/staging/package.json`,
  `.worktrees/pr-29-fix/frontend/package.json`, and so on.

Why git hygiene does not save us here:

- `.gitignore` already excludes `.venv` (lines 107, 218), `node_modules/` (206),
  and `.worktrees/` (293). Git never tracks these.
- The Snyk **IDE extension scans the filesystem working directory**, not the git
  index, so `.gitignore` does not constrain it.
- There is **no `.dcignore` and no `.snyk` file** in the repo to scope the scan.

Net effect: Snyk walks into `.venv/` and `.worktrees/` and reports other software's
vendored dependencies as if they were ours. This is the source of the 192.

## Finding 2: The real dependency surface is clean today

Scoped to the actual lockfiles:

```bash
npm --prefix frontend audit
# found 0 vulnerabilities

osv-scanner --config=osv-scanner.toml --lockfile=uv.lock
# Scanned uv.lock and found 248 packages
# No issues found
```

Two implications:

1. The 192 Open Source findings have a true-positive rate near zero for this repo.
   A developer who triages them top-to-bottom spends all their time on other
   projects' transitive trees.
2. `osv-scanner.toml` currently reports three **unused** ignores
   (`CVE-2022-42969`, `PYSEC-2022-42969`, `GHSA-w596-4wvx-j9j6`, all the disputed
   `py`/`interrogate` ReDoS). The transitive dependency that triggered them is gone,
   so these exceptions are now dead policy and should be removed.

## Finding 3: Code (SAST) findings are real files but partly false positives

These map to genuine project source. Triage:

| File | Count | Likely rule | Assessment |
| --- | --- | --- | --- |
| `src/cyo_adventure/generation/import_cli.py` | 1 | Path traversal into `read_text` (line 82) | **False positive.** Code already guards with `resolved.relative_to(cwd)` and a RAD/OWASP-LLM07 comment; Snyk's taint engine does not model `relative_to()` as a sanitizer. |
| `scripts/check_quality_gate.py` | 1 | SSRF: variable URL into `urlopen` (line 69) | **Low risk.** Code pre-validates `parsed.scheme not in ALLOWED_SCHEMES` (already satisfied Bandit B310). CI-only script hitting SonarCloud, not a request handler. |
| `tests/unit/test_worker.py` | 3 | Hardcoded credentials | **False positive.** `openrouter_api_key="test-key"` and `user:password` auth-split fixtures are test literals, not secrets. |
| `scripts/yield_harness.py` | 3 | Tainted file data into `os.environ` / `write_text` (lines 371, 457) | **Worth a real look.** `_load_env()` reads `KEY=VALUE` lines and writes them into `os.environ`. Intentional for a dev harness, but the one pattern here where untrusted file content mutates process state. |
| `test_cli_guard.py` (panel label) | 1 | n/a | Did not resolve in the main tree (`test_guarded.py`, `test_pii_guard.py` exist). Likely a worktree-only file or a slightly misread label; another symptom of worktrees being in scan scope. |

Pattern: the SAST engine does not recognize the project's existing guards, so
defensive code that already mitigates the issue still lights up. Any
suppression must follow this project's CLAUDE.md rule: justified inline ignore
with a documented reason, never a blanket suppression.

## Finding 4: Snyk overlaps four existing SCA/SAST tools with no defined role

The repo already runs, in CI and pre-commit: `osv-scanner` (+ `osv-scanner.toml`
policy), `pip-audit`, `trivy` (+ `.trivyignore`), `bandit`, `semgrep`
(`.semgrep.yml`), `renovate` (`renovate.json`), and `detect-secrets`
(`.secrets.baseline`). Snyk has been added on top with **no committed config and
no defined responsibility**. Without a decision on what Snyk owns that the others
do not, the team is signing up to maintain a fourth overlapping ignore-list and a
fourth source of duplicate findings.

## Recommendations for the .claude / template team

Priority order. Items A and B make the panel trustworthy; the rest set policy.

### A. Ship a `.dcignore` and `.snyk` baseline in the template (highest impact)

Add to the cookiecutter so every generated repo scopes Snyk away from
non-project trees:

```text
# .dcignore (Snyk Code) and conceptual exclude set for Snyk Open Source
.venv/
.worktrees/
node_modules/
site/
htmlcov/
out/
.git/
**/site-packages/**
```

Note: a `.snyk` policy file ignores specific vulns, it does not exclude paths.
Path exclusion for Snyk Open Source is driven by `--exclude` (see B). `.dcignore`
does scope Snyk Code.

### B. Standardize the extension's Open Source exclude parameters

Document (and where possible commit via `.vscode/settings.json`) the Snyk
extension setting *Advanced -> Additional parameters*:

```text
--exclude=.venv,.worktrees,node_modules,site,htmlcov,out
```

This is what collapses the 192 to the real count. Pair it with a one-line note
in the template README so developers understand why the panel was previously
inflated.

### C. Define Snyk's role relative to the existing stack

Pick one and document it so Snyk is not a redundant fourth scanner:

- **Option 1 (recommended): Snyk for SAST (Code) only**, disable Snyk Open Source,
  and keep `osv-scanner` + `pip-audit` + `trivy` as the SCA authority (they are
  already in CI and already have a justified-ignore workflow).
- **Option 2: Snyk as the single SCA+SAST tool**, and retire the overlapping
  scanners. Larger change; only worth it if Snyk's data or fix automation is
  materially better for this org.

Whatever is chosen, there should be **one** ignore-list workflow, not four.

### D. Adopt a provenance workflow for real findings

When a genuine transitive vuln does appear, the action depends on who introduced
it. Standardize these commands (template docs + optional `nox -s provenance`):

```bash
# Python: vuln list, then who pulls the package in (reverse tree)
osv-scanner --config=osv-scanner.toml --lockfile=uv.lock
uv tree --invert --package <vuln-pkg>

# Frontend: vuln list with "introduced through" path, then reverse lookup
npm --prefix frontend audit
npm --prefix frontend why <vuln-pkg>
```

The `uv tree --invert` output tags each path with the introducing extra
(`extra: dev`, `extra: supply-chain`), which is the key triage signal: a vuln
only reachable through a dev extra never ships to users and is not an emergency.

### E. SAST false-positive policy

Codify that Snyk Code suppressions follow the existing CLAUDE.md rule: inline
ignore with a documented justification, paired with a tracking reference where a
real fix is expected. The `import_cli.py` traversal guard and
`check_quality_gate.py` scheme check are the model: the mitigation lives in code,
and the suppression cites it.

### F. Clean up org/target naming

The `staging` labels in the panel are filesystem paths, not Snyk targets, which
is confusing. Once scope is fixed (A and B), confirm the `williaby` org's project
targets map to real manifests (`frontend/package.json`, `uv.lock`) and nothing
else.

## Suggested concrete template changes

1. Add `.dcignore` (template-level) with the exclude set in A.
2. Add `.vscode/settings.json` Snyk exclude params from B (or document them).
3. Add a short `docs/security/snyk.md` page covering: scope model, the
   provenance workflow (D), and the suppression policy (E).
4. Decide and record Snyk's role (C) in the template's security standards.
5. In this repo specifically: remove the three unused `osv-scanner.toml` ignores.

## Reproduction commands

```bash
# Show the scale of non-project manifests
find . -name package.json | wc -l
find . -path '*jupyterlab/staging/package.json'

# Confirm real surfaces are clean
npm --prefix frontend audit
osv-scanner --config=osv-scanner.toml --lockfile=uv.lock

# Trace provenance of any transitive package
uv tree --invert --package <name>
```

## Cross-reference

Per this project's Template Feedback Requirement, the template-level items
(A through F) should also be recorded in `docs/template_feedback.md` so they
reach the cookiecutter maintainers. Priority: **High** (security tooling emits
high false-positive volume out of the box).
