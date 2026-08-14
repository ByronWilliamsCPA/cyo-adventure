---
title: "CYO Adventure"
schema_type: common
status: published
owner: core-maintainer
purpose: "Documentation home page for CYO Adventure."
tags:
  - documentation
  - home
---

A choose-your-own-adventure reading app for kids

## Quick Start

```bash
# Clone and install (this is a deployed application, not a published package)
git clone https://github.com/ByronWilliamsCPA/cyo-adventure.git
cd cyo-adventure
uv sync --all-extras
uv run pre-commit install
```

## Features

- Python 3.11+ (3.14 is the primary runtime target)
- Type-safe with BasedPyright strict mode
- Comprehensive test coverage
- Structured logging with structlog
- Docker support
## Documentation

- [User Guide](guides/overview.md) - Getting started and usage
- [API Reference](api-reference.md) - Complete API documentation
- [Development](development/architecture.md) - Architecture and contributing
- [Project](project/roadmap.md) - Roadmap and changelog
- [Operator Runbook](operations/runbook.md) - Start/stop, health checks, incidents, secrets, kill switch
- [Authoring Guide](operations/authoring-guide.md) - Non-technical guide to the story review and approval flow

## License

This project is licensed under the MIT License - see the [LICENSE](project/license.md) file for details.
