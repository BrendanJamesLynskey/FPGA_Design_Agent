#!/bin/bash
# Brief 208: copy the text records of a build root into results/208/runs/<part>/ (no checkpoints). A report larger than
# 300 kB keeps its first 400 lines (the summary sections) and says so on its last line.
src=$1; dst=$2
mkdir -p "$dst"
for d in "$src"/*/; do
  n=$(basename "$d"); mkdir -p "$dst/$n"
  for f in "$d"*.rpt "$d"*.txt; do
    [ -f "$f" ] || continue
    if [ "$(stat -c %s "$f")" -gt 300000 ]; then
      head -400 "$f" > "$dst/$n/$(basename "$f")"
      echo "[brief 208: truncated to the first 400 lines; the full report is $(stat -c %s "$f") bytes, regenerate with tcl/run_jobs.tcl]" >> "$dst/$n/$(basename "$f")"
    else
      cp "$f" "$dst/$n/"
    fi
  done
done
