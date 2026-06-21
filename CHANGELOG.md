# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project setup and structure
- `environment` setting plus a fail-fast guard that refuses to start outside a
  local environment when the development default database URL is still in use
- Unit tests for the database, health, config, and security modules, restoring
  the 80% coverage gate
- Storybook schema v1 (`cyo_adventure.storybook`): Pydantic v2 models, a whitelisted
  in-house condition DSL (ADR-006), and JSON Schema export to
  `schema/storybook.schema.json`.
- Phase 0 specifications: runtime semantics, validator rule catalog, condition-evaluator
  spec, authorization matrix, and privacy/data-handling model.
- Effect/variable type-agreement validation (`inc`/`dec` require an int target; a `set`
  value must match the target variable type) and a `schema_version` compatibility check.

### Changed
- Readiness probes no longer return raw exception text to clients; failures are
  logged server-side and a generic message is returned (OWASP A09)
- Removed the deprecated org `python-pr-validation.yml` caller; PR-title and
  conventional-commit validation are handled by `pr-title.yml` and `ci.yml`
- Raised the supported Python floor to 3.11 (`requires-python = ">=3.11"`); the Storybook
  models use `enum.StrEnum` and `typing.Self`, which require Python 3.11 or newer.
- Restricted Storybook state variables to `bool` and `int` in v1 (removed the unused
  `string` and `enum` variable types to match the condition-evaluator specification).

### Fixed
- `mkdocs --strict` docs build (dangling known-vulnerabilities template link)
- SBOM workflow caller now passes `no-build: false` for this installable package
- Windows compatibility matrix `ParserError` (test step pinned to `shell: bash`)
- REUSE compliance coverage for newly added files
- Documentation consistency (SECURITY.md SLA, requires-python, docs claims)

## [0.1.0] - TBD

### Added
- Initial project structure with Poetry package management
- Pydantic v2 JSON schema validation
- Structured logging with structlog and rich console output
- Pre-commit hooks (Ruff format, Ruff lint, BasedPyright, Bandit, pip-audit)
- Comprehensive test suite with pytest
- GitHub Actions CI/CD pipeline with quality gates
- CLI tool foundation
- License

### Documentation
- README with project overview and quick start
- CONTRIBUTING guidelines with development workflow
- References to ByronWilliamsCPA org-level Security Policy
- References to ByronWilliamsCPA org-level Code of Conduct

### Infrastructure
- Poetry dependency management with lock file
- pytest test framework with coverage reporting
- GitHub issue tracking and templates
- Automated dependency security scanning (Safety, Bandit)
- Code quality enforcement (Ruff, BasedPyright)
- CI/CD pipeline with multiple quality gates

### Security
- Bandit security linting
- Safety dependency vulnerability scanning
- Pre-commit hooks for security validation

[Unreleased]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/releases/tag/v0.1.0
