#!/bin/bash
# Brief 208: copy the text records of a build root into results/208/records/<part>/ (no checkpoints). A report larger than
# 300 kB (timing summaries and timing_to_bufctl: 60 kB) keeps its first 400 lines (the summary sections) and says so on its last line.
src=$1; dst=$2
mkdir -p "$dst"
for d in "$src"/*/; do
  n=$(basename "$d"); mkdir -p "$dst/$n"
  for f in "$d"*.rpt "$d"*.txt; do
    [ -f "$f" ] || continue
    lim=300000; case "$(basename "$f")" in timing_summary_*|timing_to_bufctl_*) lim=60000;; esac
    if [ "$(stat -c %s "$f")" -gt $lim ]; then
      head -400 "$f" > "$dst/$n/$(basename "$f")"
      echo "[brief 208: truncated to the first 400 lines; the full report is $(stat -c %s "$f") bytes, regenerate with tcl/run_jobs.tcl]" >> "$dst/$n/$(basename "$f")"
    else
      cp "$f" "$dst/$n/"
    fi
  done
done
