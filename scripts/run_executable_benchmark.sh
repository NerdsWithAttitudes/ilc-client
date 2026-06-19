#!/usr/bin/env bash
# Run the executable-encryption benchmark for a provider/workload set and fail
# unless every produced result reports passed_validation=true.
#
# Unlike scripts/executable_benchmark_smoke.sh (which only emits JSON and never
# inspects the outcome), this runner is correctness-gating: a benchmark whose
# decrypted outputs drift outside the provider tolerance, or that produces no
# results, exits non-zero.
#
# Configuration (environment variables):
#   PYTHON_BIN                 python interpreter to use (default: python3)
#   ILC_EXECUTABLE_PROVIDER    comma-separated provider ids (default: plaintext)
#   ILC_EXECUTABLE_WORKLOAD    comma-separated workload ids (default: add_chain)
#   ILC_EXECUTABLE_REPEAT      repeat count per provider/workload (default: 1)
#   ILC_EXECUTABLE_ALLOW_SKIP  if 1, tolerate a skipped benchmark (e.g. optional
#                              dependency missing) instead of failing (default: 0)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
PROVIDER="${ILC_EXECUTABLE_PROVIDER:-plaintext}"
WORKLOAD="${ILC_EXECUTABLE_WORKLOAD:-add_chain}"
REPEAT="${ILC_EXECUTABLE_REPEAT:-1}"
ALLOW_SKIP="${ILC_EXECUTABLE_ALLOW_SKIP:-0}"

OUT_DIR="$(mktemp -d)"
trap 'rm -rf "$OUT_DIR"' EXIT
OUT_FILE="$OUT_DIR/benchmark.json"

echo "executable benchmark: provider=${PROVIDER} workload=${WORKLOAD} repeat=${REPEAT}"

"$PYTHON_BIN" -m ilc.executable.benchmark \
  --provider "$PROVIDER" \
  --workload "$WORKLOAD" \
  --repeat "$REPEAT" \
  --output-format json \
  --output-path "$OUT_FILE"

ILC_EXECUTABLE_ALLOW_SKIP="$ALLOW_SKIP" "$PYTHON_BIN" - "$OUT_FILE" <<'PY'
import json
import os
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    report = json.load(stream)

allow_skip = os.environ.get("ILC_EXECUTABLE_ALLOW_SKIP", "0") == "1"

if report.get("skipped"):
    reason = report.get("reason", "unknown reason")
    if allow_skip:
        print(f"benchmark skipped (tolerated): {reason}")
        sys.exit(0)
    print(f"ERROR: benchmark skipped: {reason}", file=sys.stderr)
    sys.exit(1)

results = report.get("results") or []
if not results:
    print("ERROR: benchmark produced no results", file=sys.stderr)
    sys.exit(1)

failures = []
for result in results:
    label = f"{result.get('workload_instance_id')}/{result.get('provider_id')}"
    if result.get("passed_validation", False):
        print(
            f"OK   {label}: max_absolute_error={result.get('max_absolute_error')} "
            f"total_time_s={result.get('total_time_s')}"
        )
    else:
        failures.append(
            f"{label}: passed_validation=false "
            f"(max_absolute_error={result.get('max_absolute_error')}, "
            f"abs_tol={result.get('absolute_tolerance')}, "
            f"rel_tol={result.get('relative_tolerance')})"
        )

if failures:
    print("ERROR: executable benchmark validation failed:", file=sys.stderr)
    for failure in failures:
        print(f"  - {failure}", file=sys.stderr)
    sys.exit(1)

print(f"All {len(results)} executable benchmark result(s) passed validation.")
PY
