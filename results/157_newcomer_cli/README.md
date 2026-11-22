# Newcomer CLI: what works without the key, and `agent doctor` (brief 157): measured results

Brief 157 (review item F8 of brief 147's flow-improvement review) makes the first minute on a fresh clone work: `--help`, `models show`,
`resume <design-dir> --dry-run` and a new `python -m agent doctor` run with no access key, while every command that calls a model, writes a design
or reads private material still stops at the gate. The labelled set is [cases.json](cases.json); [measure.py](measure.py) runs it against a
checkout and writes a record.

## Null result and prediction, written before any measurement

Written 2026-11-22 before the labelled set was run on either checkout. Before the change (origin/main at 17b4dd19) `main()` calls the gate before argparse, so
the prediction is: every `--help`, `models show` and `--dry-run` case exits 2 with the gate message and the case fails its label; the `doctor` cases fail
(`doctor` is not a command); only the cases that are meant to be refused pass. After the change the prediction is that every case passes in both
environments. A pass count after the change that is not the whole set is reported as a failure of the change, not adjusted away.
