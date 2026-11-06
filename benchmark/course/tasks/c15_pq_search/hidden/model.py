"""P15-4 model: the distance tables, the code stream and the reference result (standalone: python only; the data are in pq_data.json)."""
import json
from pathlib import Path

K = 8
M = 8
_DATA = json.loads((Path(__file__).with_name("pq_data.json")).read_text())


def tables():
    return _DATA["tables"]


def codes():
    return _DATA["codes"]


def distances(table):
    return [sum(table[j][(c >> (4 * j)) & 15] for j in range(M)) for c in codes()]


def reference_top(table):
    d = distances(table)
    return sorted(((d[i], i) for i in range(len(d))))[:K]            # smallest distance, then smaller index


def reference_output():
    return {"queries": [{"top": [list(p) for p in reference_top(t)]} for t in tables()]}


# ---- benchmark wrapper: the shell register map (from spec.yaml) ----
DESIGN_ID = 0x50515352          # "PQSR"
TADDR, TDATA, START, CODE, BURST, STATUS, RES_D, RES_I = 0x00, 0x01, 0x02, 0x08, 0x18, 0x19, 0x40, 0x48


def top_of(table, cs):
    d = [sum(table[j][(c >> (4 * j)) & 15] for j in range(M)) for c in cs]
    return sorted((d[i], i) for i in range(len(d)))[:K]


def bench_queries():
    """(table, entries, expected top-8): two course tables with 32 database entries each, and a constant table
    (every distance equal, so the order is decided by the entry number alone)."""
    ts, cs = tables(), codes()
    flat = [[5] * 16 for _ in range(M)]
    qs = [(ts[0], cs[:32]), (ts[3], cs[40:72]), (flat, cs[:20])]
    return [(t, c, top_of(t, c)) for t, c in qs]
