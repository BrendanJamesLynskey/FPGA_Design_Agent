"""Compressed-database search: the closest eight entries for two of the model's bench queries."""

QUERIES = [0, 1]


def trace(m):
    qs = m.bench_queries()
    x, qn, place, ent, word, dist, cap = [], [], [], [], [], [], []
    i = 0
    for q in QUERIES:
        table, entries, top = qs[q]
        for p, (d, e) in enumerate(top):
            x.append(i); i += 1
            qn.append(q); place.append(p); ent.append(int(e)); word.append(int(entries[e])); dist.append(int(d))
            cap.append(f"Query {q}, place {p}: entry {e} (codes {entries[e]:08X}) has distance {d}, the sum of eight table lookups.")
    return {
        "stimulus": f"Two queries, with {len(qs[QUERIES[0]][1])} and {len(qs[QUERIES[1]][1])} compressed database entries. The model adds up eight table values per entry and keeps the {m.K} smallest.",
        "unit": "result place", "x": x,
        "signals": [
            {"name": "query", "kind": "bus", "radix": "dec", "v": qn},
            {"name": "place", "kind": "bus", "radix": "dec", "v": place},
            {"name": "entry number", "kind": "bus", "radix": "dec", "v": ent},
            {"name": "entry codes", "kind": "bus", "radix": "hex", "width": 32, "v": word},
            {"name": "distance", "kind": "bus", "radix": "dec", "width": 23, "v": dist},
        ],
        "captions": cap,
    }
