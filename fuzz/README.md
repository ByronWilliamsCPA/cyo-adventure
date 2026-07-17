# Fuzzing Tests

This directory contains fuzzing harnesses for continuous security testing using
[Atheris](https://github.com/google/atheris) and
[ClusterFuzzLite](https://google.github.io/clusterfuzzlite/).

## Overview

Fuzzing feeds random and mutated data into security-relevant parsers to discover
crashes, hangs, and contract violations. This project fuzzes the two boundaries
that take fully attacker-shaped input:

- **Atheris**: Python fuzzing engine built on libFuzzer
- **ClusterFuzzLite**: Continuous fuzzing integration for GitHub Actions

## Fuzz Harnesses

### `fuzz_condition_evaluator.py`

Fuzzes the storybook condition DSL (ADR-006, in-house evaluator), which decides
which choices a child reader sees. Contract under test: `validate_condition`
rejects every malformed shape with `ValueError`, and any condition it accepts
evaluates to a `bool` for any variable state without raising. Seeded from the
shared conformance corpus (`schema/conformance/conditions.json`).

### `fuzz_storybook_validation.py`

Fuzzes `Storybook.model_validate`, the pipeline's first structural gate for raw
LLM output. Contract under test: malformed documents raise pydantic
`ValidationError` and nothing else, and accepted documents satisfy their own
structural invariants (unique ids, resolvable start node). Seeded from
`tests/fixtures/storybook/` (valid and invalid corpus).

### Harness self-test

Each harness keeps its check logic importable without atheris, and
`tests/unit/test_fuzz_harnesses.py` drives the checks over the curated corpora
on every CI run. That guarantees the harnesses stay wired to real project code:
a harness that fuzzes nothing cannot silently pass (the original template stub
did exactly that).

## Running Locally

### Prerequisites

```bash
# Install fuzzing dependencies (atheris needs a C++ toolchain)
uv sync --all-extras
uv pip install atheris
```

### Execute Fuzzers

```bash
# Condition evaluator, 60 seconds
python fuzz/fuzz_condition_evaluator.py -max_total_time=60

# Storybook schema validation, 10 minutes
python fuzz/fuzz_storybook_validation.py -max_total_time=600

# Reproduce with a specific seed
python fuzz/fuzz_condition_evaluator.py -seed=12345
```

## CI/CD Integration

Fuzzing runs via `.github/workflows/cifuzzy.yml`:

- **Triggers**: weekly schedule (Mondays 07:13 UTC) and manual
  `workflow_dispatch` only; fuzzing is deliberately not part of the per-PR loop
  (it is too heavy, and the mutation-testing workflow follows the same weekly
  cadence)
- **Duration**: 600 seconds per fuzzer per run
- **Sanitizer**: AddressSanitizer
- **Seed corpora**: built by `.clusterfuzzlite/build.sh` from the conformance
  and storybook fixture corpora
- **Reporting**: SARIF uploaded to the Security tab when a crash is found; a
  failed scheduled run files a `ci-failure` tracking issue so schedule-only
  breakage cannot stay silent

## Writing New Fuzzers

Follow the shape of the two existing harnesses:

1. Put the contract check in a plain function that takes decoded input
   (`check_<target>(text: str) -> None`), so the unit suite can drive it
   without atheris.
2. Suppress only the exceptions the contract defines as "correct rejection"
   (e.g. `ValueError`, pydantic `ValidationError`). Anything else escaping is a
   finding; never use a blanket `except Exception`.
3. Keep `test_one_input(data: bytes)` as the atheris entry point and import
   atheris inside `main()` only.
4. Add corpus-driven tests for the new check to
   `tests/unit/test_fuzz_harnesses.py`, and extend `.clusterfuzzlite/build.sh`
   with a seed corpus zip if real input shapes exist.

Good future candidates: the skeleton catalog loader (`generation/skeletons`),
the storybook import CLI, and the reading-state replay parser.

## Troubleshooting

### Atheris Installation Issues

```bash
# Ensure a C++ compiler is available
sudo apt-get install build-essential  # Ubuntu/Debian
brew install gcc                       # macOS

pip install atheris
```

### Python Version Compatibility

Atheris wheels can lag new Python releases. CI fuzzes inside the
`gcr.io/oss-fuzz-base/base-builder-python` image, which pins a supported
Python; locally, use a virtualenv on a Python version atheris supports if the
project default fails to build it.

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
