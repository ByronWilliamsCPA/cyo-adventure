---
title: "Template Feedback"
schema_type: common
status: published
owner: core-maintainer
purpose: "Document template issues for upstream fixes."
tags:
  - feedback
  - template
---

> **Purpose**: Document issues discovered in this project that should be addressed in the [cookiecutter-python-template](https://github.com/ByronWilliamsCPA/cookiecutter-python-template).
>
> **Generated From**: cookiecutter-python-template v0.1.0
> **Project Created**: 2026-06-20

---

## How to Use This File

When working on this project, if you discover any issue that originates from the template itself (not project-specific), add it here with the following format:

````markdown
### [Short Title]

- **Priority**: Critical / High / Medium / Low
- **Category**: [Configuration / Documentation / Tooling / Structure / CI/CD / Security / Other]
- **Discovered**: YYYY-MM-DD

**Issue**: [Clear description of what's wrong or missing]

**Context**: [How was this discovered? What were you trying to do?]

**Suggested Fix**: [What should the template do differently?]

**Affected Files**: [List template files that need changes]
````

---

## Feedback Items

<!-- Add your feedback below this line -->

### check-json pre-commit hook fails on frontend tsconfig JSONC files

- **Priority**: Medium
- **Category**: Tooling
- **Discovered**: 2026-06-23

**Issue**: The generated `.pre-commit-config.yaml` includes the standard
`check-json` hook with no exclude pattern. In a full-stack project the frontend
ships `tsconfig.app.json` and `tsconfig.node.json`, which are JSONC (JSON with
comments) as TypeScript and Vite require. `check-json` uses a strict JSON parser
and fails on the comments, so `pre-commit run --all-files` reports a permanent
failure unrelated to any change being committed.

**Context**: Discovered while running the full gate (`pre-commit run
--all-files`) at the end of an unrelated backend feature. The only failure was
`check-json` on `frontend/tsconfig.node.json` and `frontend/tsconfig.app.json`;
no committed change touched those files.

**Suggested Fix**: For the full-stack template variant, either exclude
`tsconfig*.json` (and other known JSONC) from the `check-json` hook via an
`exclude:` regex, or replace `check-json` with a JSONC-aware check (e.g.
`check-json5`) for the frontend paths.

**Affected Files**: `.pre-commit-config.yaml`

### ci.yml ships with frontend and ci-gate jobs dedented outside the jobs map

- **Priority**: Critical
- **Category**: CI/CD
- **Discovered**: 2026-06-20

**Issue**: In the generated `.github/workflows/ci.yml`, the `frontend:` and
`ci-gate:` job blocks are indented at column 0, placing them as top-level
workflow keys instead of members of `jobs:`. GitHub Actions parses only the
`test` job; `frontend` and `ci-gate` are silently ignored, so the `CI Gate`
required status check is never produced.

**Context**: Found during a repo-compliance audit via `yaml.safe_load`, which
reported top-level keys `[name, on, concurrency, permissions, env, jobs,
frontend, ci-gate]` with `jobs` containing only `test`.

**Suggested Fix**: Correct the indentation in the template's `ci.yml` so all
jobs nest under `jobs:`. Add a `yamllint`/parse check in the template CI to
catch dedented job blocks.

**Affected Files**: `.github/workflows/ci.yml`

### Required pre-commit hooks are missing or fail-open in the generated config

- **Priority**: High
- **Category**: Security
- **Discovered**: 2026-06-20

**Issue**: The generated `.pre-commit-config.yaml` omits the `basedpyright`
hook (PC-003, critical), the `no-em-dash` hook (PC-011), `commitizen`,
`yamllint`, and `markdownlint`, and wraps `trufflehog` in a fail-open
silent-skip (`command -v trufflehog ... || echo "...skipping"`) that passes
when the tool is absent, defeating PC-005.

**Context**: Found during a repo-compliance audit; corroborated by two
independent auditors.

**Suggested Fix**: Ship the full required hook set SHA-pinned, and make secret
scanning fail closed (no `|| echo` fallback).

**Affected Files**: `.pre-commit-config.yaml`

### Misc template drift: AGENTS.md absent, known-vulnerabilities misplaced, stray template artifact, unfilled placeholder

- **Priority**: Medium
- **Category**: Structure
- **Discovered**: 2026-06-20

**Issue**: Several baseline items drift from the standards manifest:
`AGENTS.md` is not scaffolded at root (FOUND-010); `known-vulnerabilities.md`
is placed at `.github/` instead of `docs/` (FOUND-009); a Jinja2 artifact
`README.md.j2` is emitted into `.github/workflows/` (CI-013); `requires-python`
carries a `<3.15` upper bound (FOUND-008); and `docs/template_feedback.md`
ships with an unsubstituted `__PROJECT_CREATION_DATE__` placeholder.

**Context**: Found during a repo-compliance audit of a freshly generated
project.

**Suggested Fix**: Scaffold `AGENTS.md`; output `known-vulnerabilities.md`
under `docs/`; keep template-only files out of `.github/workflows/`; drop the
`requires-python` upper bound; substitute the creation-date placeholder in the
post-generation hook.

**Affected Files**: `AGENTS.md`, `docs/known-vulnerabilities.md`,
`.github/workflows/README.md.j2`, `pyproject.toml`, `docs/template_feedback.md`

### Planning document templates generate markdown that violates the repo markdownlint config

- **Priority**: Low
- **Category**: Documentation
- **Discovered**: 2026-06-20

**Issue**: The planning templates in `.claude/skills/project-planning/templates/`
(pvs, tech-spec, roadmap, adr) prescribe an H1 heading in the document body, while the
placeholder files in `docs/planning/` carry a `title:` field in their YAML frontmatter.
With the repo `.markdownlint.json` settings, this trips `MD025` (multiple top-level
headings) on every generated planning doc. The ADR template's `**Pros**:` / `**Cons**:`
labels placed directly above a list also trip `MD032` (lists should be surrounded by
blank lines), and ASCII diagrams plus dense tables trip `MD060` (table column style).

**Context**: Discovered while generating the four foundational planning documents
(project-vision, tech-spec, roadmap, and six ADRs) from the project scoping handoff. The
committed gate already excludes `docs/planning/` via the pre-commit pattern
`^docs/(?!planning/).*\.md$`, so these are IDE-only warnings and do not block commits,
but they are noise for anyone authoring planning docs in an editor.

**Suggested Fix**: Either (a) set `MD025: { front_matter_title: "" }` in
`.markdownlint.json` so the frontmatter `title` is not treated as a competing H1, or
(b) drop the `title:` field from the planning placeholder frontmatter and rely on the
body H1. Additionally, add a blank line between the `**Pros**:` / `**Cons**:` labels and
their lists in `adr-template.md` so generated ADRs are MD032-clean.

**Affected Files**: `.markdownlint.json`;
`.claude/skills/project-planning/templates/adr-template.md`;
`docs/planning/*.md` placeholder frontmatter.

### Template ships docs/ADRs/adr-template.md with a schema_type the validator rejects (breaks pre-commit out of the box)

- **Priority**: High
- **Category**: CI/CD
- **Discovered**: 2026-06-20

**Issue**: A freshly generated project fails `pre-commit` immediately. The
`validate-front-matter` hook (wired in `.pre-commit-config.yaml` with
`files: ^docs/(?!planning/).*\.md$`) only accepts `schema_type` values of
`script`, `knowledge`, `planning`, or `common`, but the template ships
`docs/ADRs/adr-template.md` with `schema_type: adr`. Because the hook validates
the whole non-planning docs tree (not just staged files), this one file blocks
every commit in the repo until it is corrected.

**Context**: Discovered when committing the generated planning documents. The
hook failed on `docs/ADRs/adr-template.md` even though it was not part of the
change set, blocking the commit. Fixed locally by changing `schema_type: adr`
to `schema_type: planning` (matching the value used by
`docs/planning/adr/README.md`).

There is a deeper mismatch underneath: even after correcting `schema_type` to
`planning`, the `planning` schema's `status` enum is `draft | in-review |
published`, which excludes the natural ADR statuses (`proposed`, `accepted`,
`superseded`). So no `schema_type` + `status` combination cleanly fits an ADR
under the current validator. Locally this was resolved by setting
`schema_type: planning` and `status: draft` on the template placeholder.

**Suggested Fix**: Add a dedicated `adr` schema to the front-matter validator
with an ADR-appropriate status enum (`proposed | accepted | deprecated |
superseded`) and set `docs/ADRs/adr-template.md` to use it; or, if a separate
schema is not wanted, ship the template file with a combination the existing
validator accepts (`schema_type: planning`, `status: draft`). Add a CI smoke
test that runs `pre-commit run --all-files` on a freshly rendered project so this
class of out-of-the-box breakage is caught in the template repo.

**Affected Files**: `docs/ADRs/adr-template.md`; the front-matter validation
script and its allowed-tags list.

---

## Submitting Feedback

Once you've collected feedback, you can:

1. **Create an issue** in the [cookiecutter-python-template repository](https://github.com/ByronWilliamsCPA/cookiecutter-python-template/issues)
2. **Submit a PR** if you have fixes for the template
3. **Share this file** with the template maintainers

When submitting, reference this project as the source of the feedback.

### Docker compose image tags fall back to `latest`

- **Priority**: Medium
- **Category**: CI/CD
- **Discovered**: 2026-06-20

**Issue**: `docker-compose.yml` tags the app and frontend images as
`${VERSION:-latest}`. The project standard forbids the `latest` tag in any
environment, so the default fallback violates the policy whenever `VERSION` is
unset.

**Context**: Discovered while writing `TECHNICAL_BASELINE.md` (Phase 0, P0-07),
which records that container images are pinned by tag and `latest` is never used.

**Suggested Fix**: Drop the `:-latest` fallback and require `VERSION` to be set
(fail fast if missing), or default to a pinned placeholder tag rather than
`latest`.

**Affected Files**: `docker-compose.yml`, `docker-compose.prod.yml`

### `requires-python` range lets local venvs drift off the target interpreter

- **Priority**: Low
- **Category**: Configuration
- **Discovered**: 2026-06-20

**Issue**: `requires-python = ">=3.10,<3.15"` permits uv to build a local venv on
Python 3.14 even though `target-version` and CI pin 3.12. Local test runs then
execute on a different interpreter than CI.

**Context**: The worktree venv resolved to Python 3.14 during Phase 0 schema work;
CI runs 3.12.

**Suggested Fix**: Either pin a `.python-version` to 3.12 for local development, or
document that the broad range is intentional for library compatibility testing.

**Affected Files**: `pyproject.toml`, optionally `.python-version`

### pydoclint config requires typed docstrings the template itself does not provide

- **Priority**: High
- **Category**: Tooling
- **Discovered**: 2026-06-20

**Issue**: `[tool.pydoclint]` sets `arg-type-hints-in-docstring = true`, but the
template's own modules (for example `src/cyo_adventure/core/exceptions.py`) ship
Google-style docstrings without docstring type hints. Running pydoclint on the
template code reports many violations, so any new code must adopt a docstring
style the template does not itself model.

**Context**: A Phase 0 commit was blocked by pydoclint until the new schema module
docstrings were rewritten to include parenthesized arg types and typed Returns.

**Suggested Fix**: Either set `arg-type-hints-in-docstring = false` (types live in
signatures already), or update the template's shipped modules to the typed style so
there is a working example to copy.

**Affected Files**: `pyproject.toml`, `src/**/*.py`

### `test_example.py` imports a `cli` module that the template does not ship

- **Priority**: High
- **Category**: Tooling
- **Discovered**: 2026-06-20

**Issue**: `tests/test_example.py` contains a `TestCLI` class importing
`from cyo_adventure.cli import cli`, but no `cli` module exists, so 12 tests fail
with `ModuleNotFoundError` on a fresh checkout.

**Context**: Discovered when running the full test suite during Phase 0.

**Suggested Fix**: Either include a minimal `cli` module in the template, or gate
the CLI tests behind the feature flag that generates the CLI, or remove them when
no CLI is selected.

**Affected Files**: `tests/test_example.py`, `src/{{package}}/cli.py`

### Docs CI runs `mkdocs build --strict` but most pages are not in the nav

- **Priority**: Medium
- **Category**: Documentation
- **Discovered**: 2026-06-20

**Issue**: `mkdocs.yml` sets `strict: false`, yet `.github/workflows/docs.yml` runs
`mkdocs build --strict`. The starter nav lists only a subset of pages, so every
page outside it (the whole `docs/planning/` tree, the ADR pages, several root docs)
is an orphan that fails the strict CLI build.

**Context**: Discovered while wiring Phase 0 specification docs; the docs job is red
on the base independent of any new content.

**Suggested Fix**: Make the config and CI agree (either drop `--strict` from CI or
set `strict: true` in config), and ship a nav that covers every generated page, or
set `validation.nav.omitted_files` so intentional orphans do not fail strict builds.

**Affected Files**: `mkdocs.yml`, `.github/workflows/docs.yml`

### Frontend `App.tsx` ships unrendered cookiecutter placeholders

- **Priority**: Medium
- **Category**: Tooling
- **Discovered**: 2026-06-21

**Issue**: The generated `frontend/src/App.tsx` contains literal
`{{ cookiecutter.project_name }}` and `{{ cookiecutter.project_short_description }}`
strings rendered into the JSX, so a fresh frontend shows raw template tags.

**Context**: Discovered while replacing the demo App with the Phase 1 reader.

**Suggested Fix**: Render the cookiecutter variables in `App.tsx` at generation
time (or use the project name/description values), the same way other generated
files are templated.

**Affected Files**: `frontend/src/App.tsx`

### Generated API client is gitignored but CI never regenerates it

- **Priority**: Medium
- **Category**: Tooling
- **Discovered**: 2026-06-21

**Issue**: `frontend/.gitignore` ignores `src/client/` (the hey-api generated
client) and the CLAUDE.md architecture treats it as the source of truth for API
types, but the frontend CI job runs `typecheck`/`build` without a step that
regenerates the client. Any app code importing `src/client` would fail CI on a
fresh checkout because the directory does not exist and no backend is running to
generate it.

**Context**: Discovered in Phase 1 when wiring the reader to the backend; worked
around by adding a small hand-written axios adapter instead of importing the
generated client.

**Suggested Fix**: Either commit the generated client, or add a CI step that
starts the backend and runs `npm run generate-client` before typecheck/build, and
document which approach the template intends.

**Affected Files**: `frontend/.gitignore`, `.github/workflows/ci.yml`, `CLAUDE.md`
