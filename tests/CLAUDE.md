# Tests: cyo_adventure

Applies to all files under `tests/`. Inherits root `CLAUDE.md`; only
differences are listed here.

## Coverage threshold

Minimum 80% line coverage enforced in CI (`--cov-fail-under=80`). New code
paths must include tests before merging; do not lower the threshold.

## pytest conventions

- Unit tests live in `tests/unit/`; integration tests in `tests/integration/`.
- Use `conftest.py` fixtures for shared setup; never duplicate fixture logic.
- Name test functions `test_<unit>_<scenario>_<expected_outcome>` (e.g.,
  `test_login_with_expired_token_raises_auth_error`).
- Async tests must use `@pytest.mark.asyncio` and an `AsyncClient` fixture.
  Apply the marker per-test (or per-class), not via a bare module-level
  `pytestmark = pytest.mark.asyncio`, when the module mixes async and sync
  tests: a module-level mark applied to a sync test raises a `PytestWarning`
  under this project's `filterwarnings = ["error"]`.
- Do not use `pytest.mark.skip` without a linked issue reference.

## Test isolation

- Unit tests must not make real network calls or hit a live database.
  Patch external dependencies with `pytest-mock` (installed; use its `mocker`
  fixture) or `unittest.mock`.
- Integration tests that need a database use the `AsyncSession` fixture from
  `conftest.py` inside a rolled-back transaction.

## Ruff and type checking in tests

Ruff linting applies to test files. BasedPyright runs in strict mode over
`tests/`; type annotations are required on all fixtures and helpers.
