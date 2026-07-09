---
title: "Changelog"
schema_type: common
status: published
owner: core-maintainer
purpose: "Changelog for CYO Adventure."
tags:
  - project
  - changelog
---

All notable changes to CYO Adventure will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial project structure from cookiecutter template
- Core configuration with Pydantic Settings
- Structured logging with structlog and rich
- Comprehensive test infrastructure
- Documentation with MkDocs Material
- Admin-generated story book covers: illustrated portrait covers created on demand from a published story version via Gemini image generation, run in an async worker, optimized to a small WebP within the Supabase Storage budget, and rendered on the kid library's BookCard

### Changed

- None

### Deprecated

- None

### Removed

- None

### Fixed

- None

### Security

- None

## [0.1.0] - 2026

### Added

- Initial release of CYO Adventure

---

[Unreleased]: https://github.com/ByronWilliamsCPA/cyo-adventure/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ByronWilliamsCPA/cyo-adventure/releases/tag/v0.1.0
