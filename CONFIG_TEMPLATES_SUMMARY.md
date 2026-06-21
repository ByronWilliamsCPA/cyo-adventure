# Configuration File Templates Summary

This document describes the comprehensive configuration file templates created for the cookiecutter Python template.

## Files Created

All configuration files have been created in `/home/user/cookiecutter-python-template/cyo_adventure/`

### 1. **codecov.yml** - Code Coverage Configuration
- **Purpose**: Configure Codecov for coverage tracking and reporting
- **Cookiecutter Variables**:
  - `CYO Adventure` - Project name in comments
  - `A choose-your-own-adventure reading app for kids` - Description in comments
  - `cyo_adventure` - Module path for coverage tracking
  - `80` - Coverage target percentage
- **Features**:
  - Component-based coverage tracking (ingestion, detection, correction, output, utils)
  - Multi-flag tracking for unit, integration, and Python version tests
  - Comprehensive ignore patterns for tests, cache, documentation, etc.
  - Pull request comment configuration with change requirements
  - Annotations enabled for detailed coverage reports

### 2. **renovate.json** - Dependency Management
- **Purpose**: Configure automated dependency updates via Renovate Bot
- **Cookiecutter Variables**:
  - `williaby` - GitHub assignees and reviewers
- **Features**:
  - Extends recommended Renovate configuration
  - Dependency dashboard, semantic commits, semver preservation
  - Package rules for:
    - Grouped Python dependencies and dev dependencies
    - Auto-merged GitHub Actions updates (minor/patch only)
    - High-priority security updates (not auto-merged)
    - Critical security updates with prPriority 10
  - GitHub Actions commit SHA pinning
  - Poetry and GitHub Actions managers enabled
  - Weekly lock file maintenance on Monday mornings

### 3. **REUSE.toml** - License Compliance
- **Purpose**: Centralized license information via REUSE specification
- **Cookiecutter Variables**:
  - `cyo_adventure` - Package name
  - `Byron Williams` - Copyright holder
  - `https://github.com/ByronWilliamsCPA/cyo-adventure` - Download location
  - `MIT` - Primary license for source code
- **License Categories**:
  - Source code (Python, tools, tests): `MIT` (user-selected)
  - Documentation: CC-BY-4.0
  - Configuration files: CC0-1.0
  - Data files and models: ODbL-1.0
  - Build artifacts and generated files: CC0-1.0
  - Benchmark results and metadata: CC0-1.0

### 4. **osv-scanner.toml** - CVE Exception Handling
- **Purpose**: Document vulnerability exceptions and false positives
- **Features**:
  - Template structure with clear guidelines for adding exceptions
  - Three example categories (commented out):
    - Withdrawn vulnerabilities
    - Fixed in current version
    - Not used in project
  - Explicit instructions for proper exception documentation
  - Section for project-specific exceptions
- **No Cookiecutter Variables** - File is generic for all projects

### 5. **mkdocs.yml** - Documentation Configuration (Conditional)
- **Purpose**: Configure MkDocs Material theme for project documentation
- **Condition**: Only generated if `yes == "yes"`
- **Cookiecutter Variables**:
  - `CYO Adventure` - Site name and title
  - `A choose-your-own-adventure reading app for kids` - Site description
  - `Byron Williams` - Author and copyright holder
  - `https://cyo-adventure.readthedocs.io` - Documentation site URL
  - `https://github.com/ByronWilliamsCPA/cyo-adventure` - Repository URL
  - `williaby` - GitHub org/user in repo name
  - `cyo_adventure` - Project slug for repo name
- **Features**:
  - Material theme with light/dark mode palette
  - Navigation features: instant loading, tracking, tabs, sections, expand, indexes
  - Code features: copy button, annotations, syntax highlighting
  - 10 plugins: search, autorefs, mkdocstrings, section-index, git-revision-date-localized, gen-files
  - Comprehensive Markdown extensions for Python documentation
  - Google-style docstring parsing via mkdocstrings
  - Pydantic constraint rendering via griffe_pydantic
  - Standard navigation structure (User Guide, API Reference, Development, Project, Security, Operational)
  - Strict mode disabled for repo root file links

### 6. **noxfile.py** - Automation Sessions (Conditional)
- **Purpose**: Define Nox-UV automation sessions for testing, documentation, and compliance
- **Condition**: Only generated if `yes == "yes"`
- **Cookiecutter Variables**:
  - `3.12` - Python version for all sessions
- **Sessions Included**:
  - **fm**: Validate and autofix front matter in documentation
  - **docs**: Build documentation with MkDocs in strict mode
  - **serve**: Serve documentation locally with live reloading
  - **docstrings**: Check docstring coverage with pydocstyle and interrogate
  - **validate**: Run all validation checks (front matter, docstrings, docs build)
  - **reuse**: Check REUSE compliance (Docker-based)
  - **reuse_spdx**: Generate REUSE SPDX document (Docker-based)
  - **sbom**: Generate CycloneDX SBOM using UV (runtime, complete)
  - **scan**: Scan SBOM for vulnerabilities with Trivy (Docker-based)
  - **compliance**: Run all compliance checks (REUSE, SBOM, scan)
  - **test**: Run tests across Python 3.10-3.14
  - **lint**: Run Ruff linting and type hint checks across Python 3.10-3.14
  - **typecheck**: Run BasedPyright type checking across Python 3.10-3.14
- **Features**:
  - Uses nox-uv for fast virtual environment creation
  - UV as the default venv backend for all sessions
  - Multi-Python version testing support (3.10, 3.11, 3.12, 3.13, 3.14)
  - Reuses existing virtualenvs across sessions
  - External tool support for Docker-based operations
  - Comprehensive docstrings with usage examples
  - Path argument support for flexible execution
  - Error handling for missing SBOM files

### 7. **scripts/check_type_hints.py** - Type Hint Syntax Validation
- **Purpose**: Enforce that files using Python 3.10+ `|` union syntax include `from __future__ import annotations`
- **No Cookiecutter Variables** - Script is generic for all projects
- **Features**:
  - AST-based detection of `|` union syntax in type annotations
  - Regex pattern matching for common type hint patterns (`: Type | Type`, `-> Type | Type`)
  - Automatic fixing with `--fix` flag
  - Supports `--src-dir` to specify source directory (defaults to `src/`)
  - `--include-tests` flag to also check test files
  - Comprehensive error reporting with file paths and violations
- **Integration**:
  - Runs in `nox -s lint` session across multiple Python versions
  - Integrated into CI workflow quality checks
  - Exit code 0 for compliance, 1 for violations
- **Usage Examples**:
  ```bash
  # Check source files
  python scripts/check_type_hints.py

  # Check and auto-fix
  python scripts/check_type_hints.py --fix

  # Include test files
  python scripts/check_type_hints.py --include-tests
  ```
- **Rationale**: While Python 3.10+ supports native `|` union syntax, including the future import ensures forward compatibility and code clarity across Python versions.

## Cookiecutter Variables Used

All templates use the following cookiecutter variables from `cookiecutter.json`:

| Variable | Type | Default | Used In |
|----------|------|---------|---------|
| `CYO Adventure` | string | "My Python Project" | codecov.yml, mkdocs.yml |
| `cyo_adventure` | auto | Derived from project_name | codecov.yml, renovate.json, REUSE.toml, mkdocs.yml, noxfile.py |
| `A choose-your-own-adventure reading app for kids` | string | "A short description..." | codecov.yml, mkdocs.yml |
| `Byron Williams` | string | "Your Name" | REUSE.toml, mkdocs.yml |
| `williaby` | string | "yourusername" | renovate.json |
| `williaby` | auto | Derived from github_username | mkdocs.yml |
| `MIT` | choice | Apache-2.0 (default) | REUSE.toml |
| `https://github.com/ByronWilliamsCPA/cyo-adventure` | auto | Derived from github info | REUSE.toml, mkdocs.yml |
| `https://cyo-adventure.readthedocs.io` | auto | Derived from project_slug | mkdocs.yml |
| `80` | string | "80" | codecov.yml |
| `3.12` | choice | 3.12 (default) | noxfile.py |
| `yes` | choice | "yes" | mkdocs.yml (conditional) |
| `yes` | choice | "yes" | noxfile.py (conditional) |

## Conditional Rendering

Two files use Jinja2 conditional rendering:

### mkdocs.yml
```jinja2
  [Full mkdocs configuration]
```

### noxfile.py
```jinja2
  """Full nox-uv sessions with multi-Python version testing"""
```

## Component-Based Coverage Tracking

The `codecov.yml` template includes component tracking for:

- **ingestion**: PDF/Image Ingestion module (`src/cyo_adventure/ingestion/**`)
- **detection**: IQA Detection module (`src/cyo_adventure/detection/**`)
- **correction**: Image Correction module (`src/cyo_adventure/correction/**`)
- **output**: JSON Output module (`src/cyo_adventure/output/**`)
- **utils**: Utilities module (`src/cyo_adventure/utils/**`)

These can be customized per project by editing the generated `codecov.yml` file.

## Integration with Source Project

All templates are based on modern Python project best practices:

- Follows project naming conventions (snake_case for modules, PascalCase for classes)
- Includes component-based architecture patterns
- Supports Material theme for documentation
- Includes comprehensive compliance and security tooling
- Uses UV for fast dependency management
- Uses nox-uv for multi-version testing automation
- Uses Ruff for comprehensive linting and formatting
- Supports GitHub Actions CI/CD workflows

## Usage in Generated Projects

When cookiecutter generates a new project from the template:

1. **codecov.yml** - Automatically configured for project coverage thresholds
2. **renovate.json** - Automated dependency updates with proper assignees
3. **REUSE.toml** - License compliance tracking with project-specific copyright
4. **osv-scanner.toml** - Ready for project-specific vulnerability exceptions
5. **mkdocs.yml** - Generated only if `use_mkdocs == "yes"`
6. **noxfile.py** - Generated only if `include_nox == "yes"`

All paths, URLs, and configuration values are automatically substituted with project-specific values during generation.
