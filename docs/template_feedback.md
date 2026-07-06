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

### `no-em-dash` pre-commit hook's byte pattern never matches, so it silently never fires

- **Priority**: Critical
- **Category**: Tooling
- **Discovered**: 2026-07-04

**Issue**: `.pre-commit-config.yaml`'s `no-em-dash` hook runs
`git grep --cached -nP "\xe2\x80\x94" -- .`. Under PCRE `grep -P` in a UTF-8
locale, `\xe2\x80\x94` is parsed as three separate single-byte character
matches against decoded Unicode codepoints, not as the three raw UTF-8 bytes
that encode U+2014 (em-dash). Since no single codepoint in ordinary text
equals `0xE2`, `0x80`, or `0x94` in sequence as decoded characters, the
pattern never matches a real em-dash. The hook has reported "Passed" on every
commit since it was added, including commits that actually contained em-dash
characters, so the no-em-dash policy has been unenforced from the start.

**Context**: Discovered during a final whole-branch code review on a feature
branch, which found two literal U+2014 characters in a committed markdown
file despite that commit's own pre-commit run reporting the `no-em-dash`
hook as passed. Verified directly: `printf 'test\xe2\x80\x94dash\n' | grep
-nP "\xe2\x80\x94"` exits 1 (no match) against a string that visibly
contains an em-dash, while `grep -nP '\x{2014}'` against the same input
correctly matches. The config's own comment ("Pre-scan confirmed no existing
em-dashes in the repository") reflects that the check's false-negative
behavior was never caught because the pre-scan itself likely used the same
broken pattern.

**Suggested Fix**: Replace the byte-escape pattern with PCRE's codepoint
escape: `git grep --cached -nP "\x{2014}" -- .` (note: `grep -P` requires
`\x{...}` with braces for codepoints above `\x7f`; add a smoke test in the
template repo itself that stages a file containing a real em-dash and
asserts the hook fails, so this class of silently-inert security/style hook
cannot regress unnoticed again).

**Affected Files**: `.pre-commit-config.yaml`

### Template ships `utils/financial.py` scaffolding irrelevant to non-financial projects

- **Priority**: Medium
- **Category**: Structure
- **Discovered**: 2026-06-29

**Issue**: The generated `src/{package}/utils/financial.py` ships Decimal helper
utilities appropriate only for payment or accounting applications. In a kids'
reading app (or any non-financial project), the file is dead code from day one,
accumulates as technical debt, and produces confusing type-checking noise. The
CLAUDE.md architecture note for this project explicitly flags it as "template
scaffolding, not domain logic."

**Context**: Discovered during a pre-Phase-3 cleanup audit. The file contained
only a module docstring with no symbols. Nothing in the project imported it.

**Suggested Fix**: Gate generation of `utils/financial.py` behind a cookiecutter
variable (e.g. `include_financial_utils: false` by default), or remove it from
the template entirely and ship it only in a "finance" project type.

**Affected Files**: `src/{{package}}/utils/financial.py`

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

### Frontend `index.html` ships the same unrendered cookiecutter placeholders the App.tsx fix missed

- **Priority**: Medium
- **Category**: Tooling
- **Discovered**: 2026-07-05

**Issue**: `frontend/index.html` renders the document `<title>` as
`{{ cookiecutter.project_name }}` and `<meta name="description">` as
`{{ cookiecutter.project_short_description }}`, the same two placeholders flagged
for `App.tsx` on 2026-06-21 but in a different file the App.tsx fix did not
cover. `index.html` is Vite's entry document, templated at generation time
rather than rendered by React, so a project can "fix" the visible JSX and still
ship a browser tab literally titled `{{ cookiecutter.project_name }}`.

**Context**: Surfaced by a naive-user Claude-for-Chrome pass over the live site
(scenario K1): a 7-year-old persona immediately noticed the browser tab read
`{{ cookiecutter.project_name }}` and called it "leftover computer-programmer
text" on an otherwise broken-looking page.

**Suggested Fix**: Render the cookiecutter variables in `index.html` at
generation time, exactly as other generated files are templated. Add a
post-generation smoke check that greps the rendered project for any literal
`{{ cookiecutter.` string across all file types (not just `.tsx`), so the whole
class of missed-file placeholders is caught at once rather than one file at a
time.

**Affected Files**: `frontend/index.html`

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

### Workflow concurrency keys break the merge queue (missing `|| github.ref`)

- **Priority**: High
- **Category**: Tooling / CI
- **Discovered**: 2026-06-29

**Issue**: The generated `pr-validation.yml` sets its concurrency group to
`pr-validation-${{ github.event.pull_request.number }}` with no fallback. On
`merge_group` events there is no pull_request context, so the expression
collapses to a constant (`pr-validation-`) and every concurrent queue entry
shares one group. With `cancel-in-progress: true`, queue entries cancel each
other's required `Dependency & Standards Validation` check, and a cancelled
required check blocks the merge queue indefinitely. The other required
workflows (`ci.yml`, `reuse.yml`, `security-analysis.yml`, `sonarcloud.yml`)
already use the safe `${{ github.event.pull_request.number || github.ref }}`
pattern, so `pr-validation.yml` is the inconsistent one.

Separately, `sonarcloud.yml` sets `fail-on-quality-gate:
${{ github.event_name != 'pull_request' }}`, which evaluates to `true` on
`merge_group`, so Sonar enforces (and fails) the quality gate on every queue
build, producing red non-required check noise. It should enforce only on
`push` to a protected branch.

**Context**: Discovered while diagnosing why PRs were not merging through the
GitHub merge queue. Required checks were green on the PR but the queue stalled.

**Suggested Fix**: In every template workflow that triggers on `merge_group`,
key the concurrency group on `${{ github.event.pull_request.number ||
github.ref }}` (never on `pull_request.number` alone). For Sonar-style gates,
use `${{ github.event_name == 'push' }}` for enforcement so the queue stays
advisory.

**Affected Files**: `.github/workflows/pr-validation.yml`,
`.github/workflows/sonarcloud.yml`

### `skeleton-format.md` reference doc documents stale `ending.type` field and value set

- **Priority**: Medium
- **Category**: Documentation
- **Discovered**: 2026-06-30

**Issue**: `.claude/skills/cyo-author/reference/skeleton-format.md` documents ending
conventions under an `ending.type` field with values `{completion, good, neutral,
failure, death}`. The enforced schema model (`src/cyo_adventure/storybook/models.py`,
class `Ending`) uses `ending.kind` (an `EndingKind` enum: `success, setback, death,
capture, completion, discovery`) plus a separate `ending.valence` field
(`Valence`: `positive, neutral, negative`). The reference doc's field name, value set,
and axis split all differ from the enforced model, so any author following the reference
will produce structurally invalid skeletons that the Pydantic validator rejects.

**Context**: Discovered during the skeleton-diagrams workstream (Task 9 gate review)
when verifying that the drift-guard test and catalog generator use the live `EndingKind`
enum correctly. The reference doc was written before the schema 2.0 breaking change
(PR that introduced `valence`/`kind` split) and was not updated at that time.

**Suggested Fix**: Regenerate or rewrite `.claude/skills/cyo-author/reference/skeleton-format.md`
from the live model enums: replace `ending.type` with `ending.kind` (values from
`EndingKind`), add a new `ending.valence` row (values from `Valence`), and remove the
stale value set (`good`, `neutral` as top-level kinds).

**Affected Files**: `.claude/skills/cyo-author/reference/skeleton-format.md`

### `.env.example.baseline` ships generic ML/data scaffolding as default runtime vars

- **Priority**: Medium
- **Category**: Configuration
- **Discovered**: 2026-07-02

**Issue**: The template's `.standards/env.example.baseline` (which seeds each project's
root `.env.example`) ships a large block of vars for an ML/data-pipeline archetype that
most generated projects never use: `MODAL_TOKEN_ID/SECRET/WORKSPACE`,
`HUGGINGFACE_TOKEN/HUB_CACHE/MODEL_ID`, `GOOGLE_HMAC_ACCESS_KEY_ID/SECRET`,
`GCS_BUCKET_NAME/REGION`, plus generic `PROJECT_NAME`, `PROJECT_ENV`, `LOG_FORMAT`,
`LOG_FILE`, and `WORKERS` that do not map to any field in a standard Pydantic
`Settings` class. In this FastAPI project none of these had a consumer; grep confirmed
they appear only in the baseline itself. They accumulate as dead bulk that every project
must manually prune. The baseline also documents CI-only secrets (`CODECOV_TOKEN`,
`SONAR_TOKEN`, Infisical machine identity) inside a *local* `.env.example` even though
they belong in GitHub Secrets, and it uses unprefixed provider names
(`OPENROUTER_MODEL`, `OPENROUTER_MAX_TOKENS`, `OPENROUTER_TEMPERATURE`) that match no
`env_prefix`-based Settings field.

**Context**: Discovered while cleaning up this project's `.env.example`, which had grown
to 300+ lines mixing real backend/compose vars with the untouched template block and a
duplicated, typo-laden operator-pasted tail. Reconstructing "what is truly needed"
required diffing the file against `core/config.py`, `docker-compose*.yml`, the frontend
example, and repo scripts.

**Suggested Fix**: Slim the baseline to a minimal, archetype-neutral core (environment,
log level, database URL, one optional provider key) and move the ML/data and cloud-storage
vars into an opt-in cookiecutter feature flag (e.g. `use_ml_stack`). Keep CI-only secrets
out of `.env.example` and document them in README instead. Align example var names with
the `env_prefix` the template's `config.py` actually uses, so example names are readable
by the generated Settings class without edits.

**Affected Files**: `.standards/env.example.baseline`, template `config.py`, cookiecutter
`cookiecutter.json` (for a proposed `use_ml_stack` flag)

---

### `frontend`'s `npm run typecheck` silently checks zero files

- **Priority**: High
- **Category**: Tooling
- **Discovered**: 2026-07-03

**Issue**: `frontend/package.json`'s `"typecheck": "tsc --noEmit"` runs against the root
`frontend/tsconfig.json`, which is a references-only "solution" config (`"files": []`,
`"references": [tsconfig.app.json, tsconfig.node.json]`). Plain `tsc --noEmit` (no `-b`
flag) does not follow project references, so it type-checks zero files and always exits 0
regardless of real errors in `src/`. The only command that actually type-checks the app is
`npm run build` (`tsc -b && vite build`), which CI's "Frontend (Node 22)" job runs but
which is easy to forget is the real gate, since its name and output suggest a bundling
step, not a type-checking one.

**Context**: Discovered during a `/pr-fix` pass on PR #90: `npm run typecheck` reported
clean locally after a refactor, but the pushed commits failed CI's "Frontend (Node 22)"
job with two genuine `tsc -b` errors (an ES2022-only `Error` constructor form used against
an ES2020 build target, and a TypeScript union-narrowing gap) that `--noEmit` alone never
surfaced. Reproducing locally required running `npm run build`, not `npm run typecheck`.

**Suggested Fix**: Either point `typecheck` at `tsc --noEmit -p tsconfig.app.json` (and a
second invocation for `tsconfig.node.json`) so it actually checks files without emitting a
build, or change the script to `tsc -b --noEmit` if `-b` supports it project-wide, so the
command's name matches what it does. Whichever is chosen, add a one-line comment in the
generated `package.json` noting that the root `tsconfig.json` is references-only and
`--noEmit` alone will not check anything through it.

**Affected Files**: template `frontend/package.json` (`typecheck` script), template
`frontend/tsconfig.json` scaffold comment
