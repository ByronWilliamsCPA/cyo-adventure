# Python Development Standards

Standards and patterns for Python development in this project.

> Corrected 2026-09-05: this file had drifted from the tree (Black, Python 3.12, a 100 percent
> critical-path target). `pyproject.toml` and `tests/CLAUDE.md` are authoritative where they differ.

## Code Style

### Formatting
- **Formatter**: Ruff format (88 character line length); Black is not used
- **Import Sorting**: Ruff isort rules
- **Docstrings**: Google style

### Linting
- **Linter**: Ruff with PyStrict-aligned rules
- **Type Checker**: BasedPyright (strict mode)

## Type Annotations

### Required Annotations
- All public function parameters
- All public function return types
- All class attributes

### Type Checking Configuration
```toml
[tool.basedpyright]
pythonVersion = "3.14"
typeCheckingMode = "strict"
strictListInference = true
strictDictionaryInference = true
strictSetInference = true
```

## Error Handling

### Patterns
```python
# Use specific exceptions
def process_data(data: dict[str, Any]) -> Result:
    if not data:
        raise ValueError("Data cannot be empty")
    try:
        result = validate_and_process(data)
    except ValidationError as e:
        logger.error("Validation failed: %s", e)
        raise
    return result
```

### Anti-Patterns
```python
# Avoid bare except
try:
    risky_operation()
except:  # Never do this
    pass

# Avoid catching Exception without re-raising
try:
    risky_operation()
except Exception:  # Too broad
    pass
```

## Testing Standards

### Test Organization
```text
tests/
├── unit/           # Fast, isolated tests (<1s each)
├── integration/    # Service integration tests
├── e2e/           # End-to-end scenarios
└── conftest.py    # Shared fixtures
```

### Coverage Requirements
- **Minimum**: 80%
- **Branch Coverage**: Enabled
- **Critical Paths**: 90% (the `safety-critical` Codecov component: `moderation/**`, `middleware/**`, `core/**`, `api/deps.py`, `publishing/**`; patch 95%)

### Test Naming
```python
def test_login_with_expired_token_raises_auth_error():
    """`test_<unit>_<scenario>_<expected_outcome>`, per tests/CLAUDE.md."""
```

## Documentation

### Docstring Format (Google Style)
```python
def function(param1: str, param2: int) -> bool:
    """Short description of function.

    Longer description if needed. Can span multiple lines.

    Args:
        param1: Description of param1.
        param2: Description of param2.

    Returns:
        Description of return value.

    Raises:
        ValueError: When param1 is empty.

    Example:
        >>> function("test", 42)
        True
    """
```

## Security Considerations

### Input Validation
- Always validate user input at boundaries
- Use type annotations for runtime validation
- Sanitize before processing

### Secret Management
- Never hardcode secrets
- Use environment variables
- Encrypt sensitive data at rest

### Dependency Management
- Pin dependency versions
- Regular security audits
- Use trusted sources only

## Performance Guidelines

### Database Queries
- Avoid N+1 queries
- Use eager loading where appropriate
- Index frequently queried columns

### Memory Management
- Use generators for large datasets
- Clean up resources (context managers)
- Profile memory usage

### Async Operations
- Use asyncio for I/O-bound operations
- Avoid blocking calls in async contexts
- Use connection pooling
