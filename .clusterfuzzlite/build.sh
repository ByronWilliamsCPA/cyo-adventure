#!/bin/bash -eu
# ClusterFuzzLite Build Script
# Compiles Python fuzz targets with coverage instrumentation
#
# Reference: https://google.github.io/clusterfuzzlite/build-integration/python/

# shellcheck disable=SC2154
# Note: $SRC and $OUT are provided by ClusterFuzzLite runtime environment

# Install the package with fuzzing support
pip3 install -e .

# Copy fuzz targets to the output directory
# Each Python file in fuzz/ directory becomes a fuzz target
for fuzzer in "$SRC"/cyo_adventure/fuzz/fuzz_*.py; do
    if [ -f "$fuzzer" ]; then
        fuzzer_basename=$(basename -s .py "$fuzzer")
        cp "$fuzzer" "$OUT/$fuzzer_basename"
        chmod +x "$OUT/$fuzzer_basename"
    fi
done
