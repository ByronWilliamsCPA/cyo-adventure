#!/bin/bash -eu
# ClusterFuzzLite Build Script
# Compiles Python fuzz targets into self-contained fuzzer executables.
#
# Reference: https://google.github.io/clusterfuzzlite/build-integration/python/

# shellcheck disable=SC2154
# Note: $SRC and $OUT, and the compile_python_fuzzer helper, are provided by
# the gcr.io/oss-fuzz-base/base-builder-python runtime environment.

# Install the package so fuzz targets can import project code.
pip3 install -e .

# Compile each fuzz target with compile_python_fuzzer. This helper runs
# PyInstaller to bundle the target plus its dependencies into a standalone
# Atheris-instrumented executable in $OUT (along with the .options metadata
# file) that the run_fuzzers action can discover. A plain `cp` of the .py
# file is NOT a recognised fuzz target and fails the bad-build-check with
# "No fuzz targets found".
for fuzzer in "$SRC"/cyo_adventure/fuzz/fuzz_*.py; do
    if [ -f "$fuzzer" ]; then
        compile_python_fuzzer "$fuzzer"
    fi
done

# Seed corpora: libFuzzer picks up $OUT/<fuzzer>_seed_corpus.zip
# automatically, so mutation-based fuzzing starts from real document
# shapes instead of raw noise.
#
# - fuzz_condition_evaluator: every condition from the shared conformance
#   corpus (schema/conformance/conditions.json), one JSON file per case.
# - fuzz_storybook_validation: the curated valid and invalid storybook
#   fixtures under tests/fixtures/storybook/.
python3 - <<'PYEOF'
import json
import zipfile
from pathlib import Path

src = Path("/src/cyo_adventure")
out = Path("/out")

cases = json.loads(
    (src / "schema" / "conformance" / "conditions.json").read_text(encoding="utf-8")
)["cases"]
with zipfile.ZipFile(out / "fuzz_condition_evaluator_seed_corpus.zip", "w") as zf:
    for case in cases:
        zf.writestr(f"{case['name']}.json", json.dumps(case["condition"]))

fixtures = sorted((src / "tests" / "fixtures" / "storybook").rglob("*.json"))
with zipfile.ZipFile(out / "fuzz_storybook_validation_seed_corpus.zip", "w") as zf:
    for path in fixtures:
        zf.writestr(path.name, path.read_text(encoding="utf-8"))

print(f"seed corpora: {len(cases)} conditions, {len(fixtures)} storybooks")
PYEOF
