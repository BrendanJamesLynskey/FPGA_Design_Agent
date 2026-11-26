#!/bin/bash
# run_ifg_formal.sh (brief 158): runs the three SymbiYosys tasks of mac64_tx_ifg.sby and checks their verdicts.
#   unreach_cover must FAIL with both UNREACH_* statements listed as unreached; unreach_prove must PASS; reach_cover must PASS.
# Needs sby and yosys with the slang plugin: the OSS CAD Suite release the repo's CI pins (2026-11-12), found through FDA_OSS_CAD, then ~/.local/opt/oss-cad-suite, then PATH.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-/tmp/mac64_tx_ifg_formal}"
for c in "${FDA_OSS_CAD:-}" "$HOME/.local/opt/oss-cad-suite"; do
    if [ -n "$c" ] && [ -x "$c/bin/sby" ]; then export PATH="$c/bin:$PATH"; break; fi
done
command -v sby >/dev/null || { echo "sby not found"; exit 2; }
cd "$HERE"
rc=0
sby -f -d "$OUT/unreach_cover" mac64_tx_ifg.sby unreach_cover > "$OUT.unreach_cover.log" 2>&1
n=$(grep -c "Unreached cover statement" "$OUT.unreach_cover.log")
if [ "$n" -eq 2 ] && ! grep -q "reached cover statement mac64_tx_fv_top.*UNREACH" "$OUT.unreach_cover.log"; then echo "unreach_cover: both conditions unreached (as expected)"; else echo "unreach_cover: UNEXPECTED (see $OUT.unreach_cover.log)"; rc=1; fi
for t in unreach_prove reach_cover; do
    if sby -f -d "$OUT/$t" mac64_tx_ifg.sby "$t" > "$OUT.$t.log" 2>&1; then echo "$t: PASS"; else echo "$t: FAIL (see $OUT.$t.log)"; rc=1; fi
done
exit $rc
