---
title: "Python Version Compatibility Guide"
schema_type: common
status: published
owner: core-maintainer
purpose: "Guide for maintaining compatibility across Python versions."
tags:
  - guide
  - development
  - requirements
---

This project requires **Python 3.11+** (`requires-python = ">=3.11"` in `pyproject.toml`, no upper bound). Python 3.12 is the primary local development target. CI coverage is split across two workflows with different scope: `ci.yml` runs the full quality gate (tests, lint, type checking) on **Python 3.12 only**; `python-compatibility.yml` runs a pytest-only compatibility check on Python 3.11-3.13 (Ubuntu), plus Python 3.12 on macOS and Windows. Python 3.10 and 3.14 appear only in the local `nox -s test` / `lint` / `typecheck` matrix (3.10-3.14); **no GitHub Actions workflow invokes `nox`**, so those two versions have no CI coverage, and 3.10 in particular falls below the project's `requires-python` floor (see the note under [Python 3.10 Support](#python-310-support-backports-needed) below).

## Version Support Matrix

| Python Version | Support Status | Nox Testing (local only) | CI Testing | Notes |
|----------------|----------------|--------------------------|------------|-------|
| 3.10 | ❌ Not supported | ⚠️ Listed in `noxfile.py`'s `test`/`lint`/`typecheck` matrix | ❌ None | Below `requires-python = ">=3.11"`; not installable via `uv sync` |
| 3.11 | ✅ Supported | ✅ test/lint/typecheck | ✅ `python-compatibility.yml` (Ubuntu only) | LTS version (EOL Oct 2027) |
| 3.12 | ✅ Supported | ✅ test/lint/typecheck | ✅ Full quality gate (`ci.yml`) + `python-compatibility.yml` (Ubuntu, macOS, Windows) | Primary/default local dev target; only version covered by the main CI gate |
| 3.13 | ✅ Supported | ✅ test/lint/typecheck | ✅ `python-compatibility.yml` (Ubuntu only) | Latest stable, PEP 594 removals |
| 3.14 | ⚠️ Locally tested only | ✅ test/lint/typecheck | ❌ None | Not covered by any GitHub Actions workflow |
| 3.15+ | ⚠️ Not tested | ❌ None | ❌ No CI/CD | May work but not guaranteed |

## Python 3.10 Support (Backports Needed)

> **Note:** This project's actual `requires-python` floor is `>=3.11` (verified in
> `pyproject.toml`), so Python 3.10 is **not currently supported** and the backport
> dependencies below are not active (they exist only as commented-out illustrative
> examples in `pyproject.toml`). This section is retained as generic reference
> guidance in case the floor is lowered again in the future; it does not describe
> this project's current dependency set.

If this project's floor were lowered back to Python 3.10, some features from newer versions would require backport packages:

### Required Backports for 3.10

```toml
dependencies = [
    # TOML support (tomllib added in 3.11)
    "tomli>=2.0.0; python_version < '3.11'",

    # Exception groups (added in 3.11)
    "exceptiongroup>=1.1.0; python_version < '3.11'",

    # Newer typing features
    "typing-extensions>=4.12.0",  # Always useful for backporting latest typing features
]
```

### Code Patterns for 3.10 Compatibility

```python
# TOML parsing
import sys
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

# Or use try/except
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

# Exception groups (use exceptiongroup backport for 3.10)
try:
    ExceptionGroup
except NameError:
    from exceptiongroup import ExceptionGroup

# Typing features
from typing_extensions import Self, TypeVarTuple, Never
```

## Built-in Features (Python 3.11+)

The following features are **natively available** in Python 3.11+ and **do not require backport packages**:

### Standard Library Additions

- **`tomllib`**: Native TOML parser (PEP 680)

  ```python
  import tomllib  # No need for tomli backport

  with open("pyproject.toml", "rb") as f:
      data = tomllib.load(f)
  ```

- **`asyncio.TaskGroup`**: Structured concurrency (PEP 654)

  ```python
  import asyncio

  async def main():
      async with asyncio.TaskGroup() as tg:
          tg.create_task(task1())
          tg.create_task(task2())
  ```

- **`ExceptionGroup`**: Native exception groups (PEP 654)

  ```python
  try:
      ...
  except* ValueError as eg:  # Note the * syntax
      handle_value_errors(eg)
  ```

### Typing Improvements

- **`typing.Self`**: Self-referential type annotations (PEP 673)

  ```python
  from typing import Self

  class Builder:
      def set_value(self, value: int) -> Self:
          self.value = value
          return self
  ```

- **`typing.TypeVarTuple`**: Variadic generics (PEP 646)
- **`typing.Never`**: Bottom type (PEP 484)
- **`typing.LiteralString`**: Literal string type (PEP 675)

### Other Enhancements

- **Fine-grained error locations** in tracebacks
- **Faster startup time** (10-60% improvement)
- **Better exception notes** with `.add_note()`

## Python 3.13 Changes

### PEP 594: Module Removals

Python 3.13 **removed** the following deprecated modules. If your code uses them, you'll need replacements:

#### Removed Modules

| Module | Purpose | Replacement |
|--------|---------|-------------|
| `cgi`, `cgitb` | CGI scripts | Use `legacy-cgi` package or modern web frameworks |
| `imghdr`, `sndhdr` | Image/sound header detection | Use `filetype` or `python-magic` |
| `mailcap` | Mailcap file handling | Use `mailcap-fix` package |
| `nntplib` | NNTP protocol | Use `nntplib-py3` package |
| `telnetlib` | Telnet protocol | Use `telnetlib3` package |
| `uu` | UU encoding | Use `base64` module |
| `aifc`, `audioop`, `chunk`, `sunau` | Audio file handling | Use `audiofile` or specialized libraries |
| `crypt` | Unix password hashing | Use `bcrypt` or `passlib` |
| `msilib` | Windows Installer | Windows-specific, use `pywin32` |
| `nis`, `spwd`, `ossaudiodev` | Unix-specific modules | Platform-specific alternatives |
| `pipes` | Shell command pipelines | Use `subprocess` module |
| `xdrlib` | XDR data | Use `xdrlib3` package |

#### How to Handle Removals

If you **do** use these modules, add conditional dependencies:

```toml
# In pyproject.toml dependencies list
dependencies = [
    # ... other deps ...

    # Add replacements for Python 3.13+
    "legacy-cgi>=2.6.1; python_version >= '3.13'",  # For cgi module
    "filetype>=1.2.0",  # Better alternative to imghdr/sndhdr
    "python-magic>=0.4.27",  # Alternative file type detection
]
```

### Python 3.13 Improvements

- **Experimental free-threaded mode** (no GIL) with `python3.13t`
- **Just-in-Time (JIT) compiler** (experimental, opt-in)
- **Improved error messages** with better suggestions
- **Better typing support** for generics

## Python 3.14 Changes

Python 3.14.0 was released on October 7, 2025, with significant performance and concurrency improvements.

### Free-Threaded Python (PEP 779)

Python 3.14 officially supports **free-threaded mode** (no Global Interpreter Lock):

```bash
# Install free-threaded Python
uv python install 3.14t

# Check if GIL is disabled
python -c "import sys; print(f'GIL enabled: {sys._is_gil_enabled()}')"
```

**Important Considerations:**
- Not all packages support free-threaded mode yet
- Some C extensions require GIL
- Performance may vary - benchmark your workload
- Use standard Python 3.14 unless you specifically need multi-threading

### Deferred Annotation Evaluation (PEP 649)

**Breaking Change:** Annotations are no longer evaluated at function definition time.

```python
# Python 3.13 and earlier
def func(x: expensive_type_check()):  # Evaluated immediately
    pass

# Python 3.14
def func(x: expensive_type_check()):  # Deferred until introspection
    pass
```

**Impact on Runtime Type Checking:**
- Libraries like Pydantic and dataclasses handle this automatically
- Custom type introspection code may need updates
- Access annotations via `__annotations__` or `inspect.get_annotations()`

### Template Strings (PEP 750)

Python 3.14 adds template strings (t-strings):

```python
name = "world"
message = t"Hello {name}"  # New syntax
```

This project does **not** require t-strings - standard f-strings work across all versions.

### Deprecations

**`from __future__ import annotations` is deprecated:**
- This template's `check_type_hints.py` currently enforces this import
- Deprecation in 3.14, removal not before Python 3.13 EOL (2029)
- Continue using it for now (enforced by `scripts/check_type_hints.py`, independent of the 3.10/3.11 floor)
- We'll update the template before 2029

**NotImplemented Boolean Context:**
- Using `NotImplemented` in boolean contexts now raises `TypeError`
- Was `DeprecationWarning` since Python 3.9

### New Features

- **compression.zstd module:** Native Zstandard compression
- **pathlib enhancements:** Recursive copy/move methods
- **Experimental JIT compiler:** Included in official binaries
- **Better error messages:** More context and suggestions
- **Syntax highlighting:** In default interactive shell
- **Android platform support:** Official binary releases
- **Emscripten support:** Tier 3 platform support

### Testing with Python 3.14

```bash
# Install Python 3.14
uv python install 3.14

# Run tests with 3.14
uv run --python 3.14 pytest

# Test all versions including 3.14
nox -s test
```

## Cross-Version Dependency Patterns

### Conditional Dependencies by Python Version

UV automatically installs the correct packages based on Python version:

```toml
dependencies = [
    # Install only on older Python versions (if you support < 3.11)
    "tomli>=2.0.0; python_version < '3.11'",
    "exceptiongroup>=1.1.0; python_version < '3.11'",

    # Install only on newer Python versions
    "legacy-cgi>=2.6.1; python_version >= '3.13'",

    # Install on specific version ranges
    "typing-extensions>=4.12.0; python_version < '3.13'",
]
```

### Platform-Specific Dependencies

Combine version and platform markers:

```toml
dependencies = [
    # Windows-specific for Python 3.13+
    "pywin32>=306; sys_platform == 'win32' and python_version >= '3.13'",

    # Unix-specific backport
    "unix-helpers>=1.0; sys_platform != 'win32'",
]
```

### Environment Markers Reference

| Marker | Example | Description |
|--------|---------|-------------|
| `python_version` | `python_version >= '3.11'` | Python version comparison |
| `python_full_version` | `python_full_version == '3.11.2'` | Exact version match |
| `sys_platform` | `sys_platform == 'linux'` | Operating system |
| `platform_machine` | `platform_machine == 'x86_64'` | CPU architecture |
| `platform_system` | `platform_system == 'Darwin'` | OS name (Darwin=macOS) |
| `implementation_name` | `implementation_name == 'cpython'` | Python implementation |

See: [PEP 508 - Dependency specification for Python Software Packages](https://peps.python.org/pep-0508/)

## Type Hint Syntax

### Modern Union Syntax (3.10+)

This project **requires** the `from __future__ import annotations` import when using `|` union syntax:

```python
from __future__ import annotations

def process(data: str | bytes) -> int | None:
    """This is enforced by scripts/check_type_hints.py"""
    ...
```

**Why?** While Python 3.10+ supports `|` natively, the future import:

- Ensures forward compatibility
- Makes runtime type evaluation consistent
- Improves code clarity across versions
- Required by our CI checks

**Validation:** Run `python scripts/check_type_hints.py --fix` to automatically add missing imports.

### Typing Best Practices

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    # Import types only for type checking (avoids circular imports)
    from mypackage.models import User

class UserManager:
    def create(self, name: str) -> Self:
        """Returns same type as the class."""
        return type(self)()

    def get_user(self, user_id: int) -> User:
        """Uses forward reference safely."""
        ...
```

## Tool Configuration

### Ruff (Linter & Formatter)

Configured to target the selected Python version:

```toml
[tool.ruff]
target-version = "py312"  # py311, py312, or py313
```

This ensures Ruff:

- Only suggests syntax available in your target version
- Flags usage of deprecated or removed features
- Applies version-appropriate optimizations

### BasedPyright (Type Checker)

Configured to match your Python version:

```toml
[tool.basedpyright]
pythonVersion = "3.12"  # 3.11, 3.12, or 3.13
typeCheckingMode = "strict"
```

This ensures BasedPyright:

- Uses correct type semantics for your version
- Validates compatibility with your target version
- Checks typing features availability

## Testing Across Versions

### Nox Sessions

`nox`'s `test`, `lint`, and `typecheck` sessions run a wide local matrix
(3.10, 3.11, 3.12, 3.13, 3.14). This is a **local-only parity check**: no
GitHub Actions workflow invokes `nox`, so running these sessions is the only
way to exercise 3.10 or 3.14 at all, and the only way to run lint/typecheck
against anything other than 3.12.

```bash
# Run tests locally across the nox matrix (3.10, 3.11, 3.12, 3.13, 3.14)
nox -s test

# Run linting locally across the nox matrix
nox -s lint

# Run type checking locally across the nox matrix
nox -s typecheck
```

### CI/CD Matrix

CI coverage is split across two separate workflows, neither of which matches
the local `nox` matrix exactly:

**`ci.yml`** (the main quality gate: tests, lint, type checking) runs on
Python 3.12 only:

```yaml
env:
  python-version: "3.12"
```

**`python-compatibility.yml`** (a pytest-only compatibility check, no lint or
type checking) runs a matrix of 3.11-3.13 on Ubuntu, plus 3.12 on macOS and
Windows:

```yaml
strategy:
  matrix:
    python-version: ['3.11', '3.12', '3.13']
    os: [ubuntu-latest]
    include:
      - os: macos-latest
        python-version: '3.12'
      - os: windows-latest
        python-version: '3.12'
```

Neither workflow covers Python 3.10 or 3.14; those two versions are exercised
only by the local `nox` matrix described above.

## Migration Guide

### Migrating to Python 3.10+

> **Note:** This project has already moved past this stage; its current
> `requires-python` floor is `>=3.11` with no upper bound. This walkthrough is
> retained as generic reference guidance for other projects (or a future
> re-lowering of the floor), not a description of this project's current
> state.

If migrating from Python 3.9 or earlier:

1. **Update Python version**:

   ```bash
   # Install Python 3.10+
   uv python install 3.10

   # Update requires-python in pyproject.toml
   requires-python = ">=3.10"
   ```

2. **Add backport packages** for 3.10 compatibility:

   ```bash
   uv add "tomli>=2.0.0; python_version < '3.11'"
   uv add "exceptiongroup>=1.1.0; python_version < '3.11'"
   uv add "typing-extensions>=4.12.0"
   ```

3. **Use conditional imports** for 3.10/3.11+ compatibility:

   ```python
   # TOML parsing - works on 3.10 and 3.11+
   try:
       import tomllib
   except ModuleNotFoundError:
       import tomli as tomllib
   ```

4. **Test across versions**:

   ```bash
   nox -s test
   ```

### Upgrading from Python 3.10 to 3.11+

> **Note:** This project has already dropped 3.10 support; `requires-python`
> in `pyproject.toml` is `>=3.11` today with no upper bound. This section is
> kept as reference guidance for the steps that were taken (and for other
> projects following the same path).

When dropping 3.10 support:

1. **Remove backport packages**:

   ```bash
   uv remove tomli exceptiongroup
   ```

2. **Update imports** to use native modules:

   ```python
   # Before (3.10 compat)
   try:
       import tomllib
   except ModuleNotFoundError:
       import tomli as tomllib

   # After (3.11+ only)
   import tomllib
   ```

3. **Update requires-python**:

   ```toml
   requires-python = ">=3.11"
   ```

### Preparing for Python 3.14

Python 3.14 (expected October 2025):

- Monitor deprecation warnings: `python -W default`
- Review PEPs targeting 3.14
- Test with pre-release versions: `uv python install 3.14.0a1`

## Troubleshooting

### Import Errors on Python 3.13

**Problem:** `ModuleNotFoundError: No module named 'cgi'`

**Solution:** Add the replacement package:

```bash
uv add "legacy-cgi>=2.6.1; python_version >= '3.13'"
```

### Type Hint Syntax Errors

**Problem:** `TypeError: unsupported operand type(s) for |: 'type' and 'type'`

**Solution:** Add future import:

```python
from __future__ import annotations
```

Or run auto-fix:

```bash
python scripts/check_type_hints.py --fix
```

### Version Detection

Check which Python version is active:

```bash
# Show active Python version
python --version

# Show all available Python versions (with UV)
uv python list

# Install specific version
uv python install 3.13

# Use specific version
uv run --python 3.13 pytest
```

## References

- [Python 3.11 Release Notes](https://docs.python.org/3/whatsnew/3.11.html)
- [Python 3.12 Release Notes](https://docs.python.org/3/whatsnew/3.12.html)
- [Python 3.13 Release Notes](https://docs.python.org/3/whatsnew/3.13.html)
- [PEP 594 - Removing dead batteries from the standard library](https://peps.python.org/pep-0594/)
- [UV Documentation - Dependency Specifiers](https://docs.astral.sh/uv/concepts/dependencies/#dependency-specifiers)
- [PEP 508 - Dependency specification](https://peps.python.org/pep-0508/)
