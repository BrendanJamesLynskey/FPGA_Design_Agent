#!/bin/bash
# usage: run.sh <block> <extra-latency> <part-tag xc7|k26> <k> [point index]
set -u
cd "$(dirname "$0")/../.."
export PATH=/home/brendan/Claude_sandbox/_worktrees/88-venv/bin:$PATH
b=$1; x=$2; tag=$3; k=$4
part=xc7a100tcsg324-1; [ "$tag" = k26 ] && part=xck26-sfvc784-2LV-c
python -u -m agent.graph.ip_closure_task "$b" --case "${tag}_${b}_k${k}" --part "$part" --clock-mhz 125 --extra-latency "$x" --max-iter 6 --point "${5:-0}" --max-usd 1.0 --out "results/b88_net125/${tag}_${b}_k${k}" --prefix "88-${b}-${tag}${k}" > "results/b88_net125/${tag}_${b}_k${k}.log" 2>&1
