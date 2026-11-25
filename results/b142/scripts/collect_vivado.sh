#!/bin/bash
# collect_vivado.sh <scratch viv dir> : copy the small report files of every finished job into results/b142/vivado/<k26|a7>/<arm>/<name>/
set -u
SRC=$1; DST=$(cd "$(dirname "$0")/.." && pwd)/vivado
for d in "$SRC"/k26/*/* "$SRC"/a7/*/*; do
  [ -d "$d" ] || continue
  [ -f "$d/done.txt" ] || [ -f "$d/error.txt" ] || continue
  rel=${d#$SRC/}; mkdir -p "$DST/$rel"
  cp "$d"/*.rpt "$d"/done.txt "$d"/error.txt "$DST/$rel"/ 2>/dev/null
done
echo "collected into $DST"
