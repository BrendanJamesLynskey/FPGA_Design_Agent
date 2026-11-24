#!/usr/bin/env python3
"""Brief 206: split a Vivado arms log into per-arm WARNING / CRITICAL WARNING / INFO lines that mention initial values.

Usage: split_log.py <vivado.log> <part>  -> TSV on stdout: part, arm, initv, severity, message id, text (first 200 chars).
Every WARNING and CRITICAL WARNING is kept; INFO lines are kept only when they mention INIT, initial, power, SRVAL, GSR,
or are Synth 8-7052 (a RAM output register not merged).
"""
import re
import sys

KEEP_INFO = re.compile(r"INIT|initial|power|SRVAL|GSR|Synth 8-7052|output register could be merged", re.I)
arm = initv = None
for line in open(sys.argv[1], errors="replace"):
    m = re.match(r"### ARM (\S+) (\d)", line)
    if m:
        arm, initv = m.group(1), m.group(2)
        continue
    if line.startswith("### END"):
        arm = None
        continue
    if arm is None:
        continue
    m = re.match(r"(CRITICAL WARNING|WARNING|INFO): \[([^\]]+)\] (.*)", line)
    if not m:
        continue
    sev, mid, text = m.groups()
    if sev == "INFO" and not KEEP_INFO.search(text):
        continue
    print("\t".join([sys.argv[2], arm, initv, sev, mid, text.strip()[:200]]))
