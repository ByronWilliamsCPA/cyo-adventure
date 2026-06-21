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
> **Project Created**: __PROJECT_CREATION_DATE__

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
