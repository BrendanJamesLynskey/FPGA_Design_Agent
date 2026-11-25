"""Brief 215: table of per-category pass rates with Wilson 95% intervals, from a results CSV (id,category,result,...).

usage: summarise.py results.csv [--weights cid002=94,cid003=78,...]   (stdlib only; bootstrap seed 215, 10,000 resamples)
Overall is the pooled rate; with --weights also the stratum-weighted rate and its stratified bootstrap interval."""
import csv, math, random, sys, argparse, collections


def wilson(k, n, z=1.959964):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv"); ap.add_argument("--weights"); ap.add_argument("--col", default="result"); ap.add_argument("--exclude", default="", help="comma-separated problem ids to leave out")
    a = ap.parse_args()
    ex = set(x for x in a.exclude.split(",") if x)
    rows = [r for r in csv.DictReader(open(a.csv)) if r["id"] not in ex]
    cat = collections.defaultdict(list)
    for r in rows:
        cat[r["category"]].append(1 if r[a.col] == "pass" else 0)
    print("| category | n | passed | pass rate | 95% interval (Wilson) |")
    print("|---|---|---|---|---|")
    K = N = 0
    for c in sorted(cat):
        k, n = sum(cat[c]), len(cat[c]); K += k; N += n
        lo, hi = wilson(k, n)
        print(f"| {c} | {n} | {k} | {100*k/n:.0f}% | {100*lo:.0f}% to {100*hi:.0f}% |")
    lo, hi = wilson(K, N)
    print(f"| all (pooled) | {N} | {K} | {100*K/N:.0f}% | {100*lo:.0f}% to {100*hi:.0f}% |")
    if a.weights:
        w = {k: int(v) for k, v in (x.split("=") for x in a.weights.split(","))}
        tot = sum(w[c] for c in cat)
        est = sum(w[c] / tot * sum(cat[c]) / len(cat[c]) for c in cat)
        rng = random.Random(215); bs = []
        for _ in range(10000):
            s = 0.0
            for c in cat:
                v = cat[c]; s += w[c] / tot * sum(rng.choice(v) for _ in v) / len(v)
            bs.append(s)
        bs.sort()
        print(f"| all (stratum-weighted) | {N} | | {100*est:.0f}% | {100*bs[249]:.0f}% to {100*bs[9749]:.0f}% (bootstrap) |")


if __name__ == "__main__":
    main()
