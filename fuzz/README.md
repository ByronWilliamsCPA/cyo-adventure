# Fuzzing Tests

This directory contains fuzzing harnesses for continuous security testing using [Atheris](https://github.com/google/atheris) and [ClusterFuzzLite](https://google.github.io/clusterfuzzlite/).

## Overview

Fuzzing is an automated testing technique that feeds random or mutated data into your code to discover crashes, hangs, and security vulnerabilities. This project uses:

- **Atheris**: Python fuzzing engine built on libFuzzer
- **ClusterFuzzLite**: Continuous fuzzing integration for GitHub Actions

## Fuzz Harnesses

### `fuzz_input_validation.py`

Tests input validation and sanitization:

- Empty inputs and edge cases
- Invalid UTF-8 sequences
- Special characters and format strings
- Buffer overflow attempts
- Type confusion

## Running Locally

### Prerequisites

```bash
# Install fuzzing dependencies
uv sync --all-extras
uv pip install atheris
```

### Execute Fuzzers

Run each fuzzer for 60 seconds:

```bash
# Input validation fuzzer
python fuzz/fuzz_input_validation.py -max_total_time=60
```

For longer fuzzing sessions:

```bash
# Run for 10 minutes
python fuzz/fuzz_input_validation.py -max_total_time=600

# Run with specific seed for reproducibility
python fuzz/fuzz_input_validation.py -seed=12345
```

## CI/CD Integration

Fuzzing runs automatically in CI via `.github/workflows/cifuzzy.yml`:

- **Triggers**: Every push to main/develop and on PRs
- **Duration**: 600 seconds per fuzzer
- **Sanitizer**: AddressSanitizer for memory safety
- **Reporting**: SARIF format uploaded to GitHub Security tab

## Writing New Fuzzers

Create a new fuzzer by following this template:

```python
#!/usr/bin/env python
"""Fuzzing harness for [component name]."""

import sys
import atheris

with atheris.instrument_imports():
    from cyo_adventure import your_function


def TestOneInput(data: bytes) -> None:
    """Fuzz test [component] with arbitrary byte sequences.

    Args:
        data: Random byte sequence from fuzzer.
    """
    if len(data) < MIN_SIZE:
        return

    try:
        # Test your function
        your_function(data)
    except ExpectedException:
        # Expected exceptions are OK
        pass
    except Exception:
        # Catch-all to prevent crashes
        pass


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
```

## Common Fuzzing Targets

Good candidates for fuzzing:

- ✅ Input parsers (JSON, XML, CSV, etc.)
- ✅ Data validators and sanitizers
- ✅ File format handlers
- ✅ Network protocol implementations
- ✅ Cryptographic functions
- ✅ Regular expression matchers

## Troubleshooting

### Atheris Installation Issues

If Atheris fails to install:

```bash
# Ensure you have a C++ compiler
sudo apt-get install build-essential  # Ubuntu/Debian
brew install gcc  # macOS

# Install with pip
pip install atheris
```

### Python Version Compatibility

**Note**: Atheris currently works best with Python 3.11. If your project uses Python 3.12+, you may need to:

1. Use Python 3.11 specifically for fuzzing:

   ```bash
   python3.11 -m venv fuzz-env
   source fuzz-env/bin/activate
   pip install atheris
   ```

2. CI/CD uses Python 3.11 for fuzzing even if main project uses 3.12+

## Resources

- [Atheris Documentation](https://github.com/google/atheris)
- [ClusterFuzzLite Guide](https://google.github.io/clusterfuzzlite/)
- [Fuzzing Best Practices](https://google.github.io/oss-fuzz/getting-started/new-project-guide/)
- [libFuzzer Tutorial](https://llvm.org/docs/LibFuzzer.html)

## Security

If fuzzing discovers a security vulnerability:

1. **DO NOT** commit crash samples to the repository
2. Report to byronawilliams@gmail.com
3. See [Security Policy](https://github.com/ByronWilliamsCPA/.github/blob/main/SECURITY.md)
