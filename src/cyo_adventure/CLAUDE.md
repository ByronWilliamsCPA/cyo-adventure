# Source: cyo_adventure package

Applies to all files under `src/cyo_adventure/`. Inherits root `CLAUDE.md`; only
differences are listed here.

## RAD Assumption Tagging (mandatory in this package)

Every function that touches async I/O, database access, external APIs, auth,
or financial logic MUST carry at least one RAD marker before shipping:

```python
# #CRITICAL: concurrency: async handler shares mutable state with background task
# #VERIFY: use asyncio.Lock or make state immutable
```

Mandatory categories for this package: timing dependencies (all async routes),
external resources (database, S3, any HTTP client), data integrity (ORM
boundary, Pydantic deserialization), concurrency (shared context vars),
security (auth middleware, input validation), and payment/financial if added.

## Async FastAPI patterns

- All route handlers must be `async def`; never mix sync blocking calls inside them.
- Use `async with` for database sessions (SQLAlchemy 2.x `AsyncSession`).
- Never call `session.commit()` inside a route handler directly; use a
  dependency-injected unit-of-work or context manager.
- Propagate correlation IDs from `middleware/correlation.py` into every log call.

## Exception hierarchy

Always raise from `core/exceptions.py`. Do not raise built-in exceptions
directly in route handlers or service functions. Map to HTTP status in the
FastAPI exception handler, not inline.

## Type checking

BasedPyright strict mode is enforced. No `# type: ignore` without a ticket
reference comment on the same line.
