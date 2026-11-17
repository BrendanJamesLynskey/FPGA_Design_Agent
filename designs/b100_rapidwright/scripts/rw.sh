#!/usr/bin/env bash
# rw.sh <log> <python-script> [args]: run a RapidWright script (flow/rw/*.py) in a memory-capped scope with the pinned venv, Vivado's own JRE,
# and Vivado 2026.1 first on PATH (RapidWright starts a Vivado to turn a checkpoint's encrypted EDIF into a readable one; with 2025.2 first
# on PATH it picks that and fails: "created with Vivado v2026.1 and cannot be opened in this version"). JVM peak is in <log>.time.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$HERE/../../.."
LOG="$1"; shift
VIVBIN="$(dirname "$(python3 "$ROOT/flow/version_pin.py" --vivado)")"
JH="$(python3 -c "import runpy; print(runpy.run_path('$ROOT/flow/rapidwright_pin.py')['JAVA_HOME'])")"
export JAVA_HOME="$JH" PATH="$VIVBIN:$JH/bin:$PATH"
cd "$ROOT/tools/rapidwright_env/work"
exec systemd-run --user --scope -p MemoryMax="${B100_RW_MEM:-8G}" bash "$HERE/peak.sh" "${LOG%.log}.time" nice -n 15 \
  "$ROOT/tools/rapidwright_env/venv/bin/python" -I "$@" > "$LOG" 2>&1
