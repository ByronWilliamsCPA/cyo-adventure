---
title: "API Reference"
schema_type: common
status: published
owner: core-maintainer
purpose: "API documentation for CYO Adventure."
tags:
  - api
  - reference
---

CYO Adventure's REST API is documented by its live, generated OpenAPI schema, not by
hand-maintained pages here. With the backend running (`uv run uvicorn cyo_adventure.app:app
--reload`), the full, current set of routers is available at:

- **Swagger UI**: <http://localhost:8000/docs>, interactive, try-it-out per endpoint.
- **ReDoc**: <http://localhost:8000/redoc>, a single-page reference view.
- **Raw schema**: <http://localhost:8000/openapi.json>, the source of truth the frontend's
  API client is generated from (`cd frontend && npm run generate-client`); CI fails the
  build on drift between this schema and the committed client.

For the endpoint-by-endpoint authorization model (who can call what), see
[Authorization Matrix](planning/authorization-matrix.md) rather than the schema, which
does not encode role checks.

## Selected internal modules

The two modules below are stable enough to be worth static reference; the rest of the
codebase is intentionally not duplicated here (see the OpenAPI schema instead).

### Core configuration

::: cyo_adventure.core.config
    options:
      show_root_heading: true
      members_order: source

### Logging

::: cyo_adventure.utils.logging
    options:
      show_root_heading: true
      members_order: source
