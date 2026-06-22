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
