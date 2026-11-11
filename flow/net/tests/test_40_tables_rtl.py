"""Brief 40, block 3: the match tables (exact, LPM, ternary) behind the AXI4-Lite front end, against the Python
models, with lookups running every clock while the tables are updated.

Each lookup is checked against the model state it may legally see: with commands applied one at a time, a lookup
issued after n commands have been polled complete sees the state after n commands or after n + 1 (the one in
flight); for a ternary rewrite also the state with that rule absent. Where those states agree, the check is exact.
"""
from __future__ import annotations

import bisect
import copy
import random

import pytest

from flow.net import model, pktio, sim

TB = sim.IP / "axil_table_ctrl" / "tb" / "tb_match_table.sv"
LAT = {0: 3, 1: 10, 2: 4}


def srcs(table: int, rtl_dirs=None):
    blk = {0: "match_exact", 1: "match_lpm", 2: "match_ternary"}[table]
    rd = (rtl_dirs or {}).get(blk)
    return sim.rtl("axil_table_ctrl") + sim.rtl(blk, rd) + [TB]


def prog_cmd(lines: list, op: int, addr: int = 0, key: int | None = None, care: int | None = None,
             act: int | None = None, raw: int | None = None):
    """Append the AXI4-Lite writes for one command and a poll."""
    def words(v, base_bit, nbits):
        for i in range((nbits + 31) // 32):
            lines.append(f"W {(base_bit // 32 + i) * 4:x} {(v >> (32 * i)) & 0xFFFFFFFF:x}")
    if key is not None:
        words(key, 0, 128)
    if care is not None:
        words(care, 128, 128)
    if act is not None:
        words(act, 256, 64)
    if raw is not None:
        words(raw, 0, 96)
    lines.append(f"W 40 {(addr << 16) | op:x}")
    lines.append("P")


def run(tmp, table, params, lookups, cmd_lines, tag="tables", rtl_dirs=None, lk_after=0):
    with open(tmp / "lk.txt", "w") as f:
        for g, k in lookups:
            f.write(f"{g} {k:x}\n")
    (tmp / "cmd.txt").write_text("\n".join(cmd_lines) + "\n")
    p = dict(params, TABLE=table)
    sim.run(srcs(table, rtl_dirs), "tb_match_table", {"lk": tmp / "lk.txt", "cmd": tmp / "cmd.txt",
                                                      "resp": tmp / "resp.txt", "lk_after": lk_after},
                params=p, tag=tag)
    r = pktio.read_resp(tmp / "resp.txt")
    res = sorted((w[2], c, w[0], w[1]) for c, w in r["words"]["R"])        # (tag, cycle, hit, act)
    polls = [(c, w[0]) for c, w in r["words"]["S"]]
    issued = {w[0]: c for c, w in r["words"]["I"]}
    lat = {res[i][1] - issued[res[i][0]] for i in range(len(res))}
    assert len(lat) == 1, f"lookup latency not constant: {lat}"
    LAT[table] = lat.pop()
    return res, polls, r["meta"]


def check_consistent(res, polls, states, lookups_keys, lat, extra_states=None, min_n=0):
    """states[n] = function key -> (hit, act) after n commands. Returns (exact, ambiguous) counts; raises on any
    result outside the allowed states."""
    done_cycles = [c for c, _ in polls]
    exact = amb = 0
    for tag, cyc, hit, act in res:
        issued = cyc - lat
        n0 = bisect.bisect_right(done_cycles, issued)
        if n0 < min_n:
            continue
        allowed = {states[n0](lookups_keys[tag])}
        if n0 + 1 < len(states):
            allowed.add(states[n0 + 1](lookups_keys[tag]))
        if extra_states and n0 < len(extra_states) and extra_states[n0]:
            allowed.add(extra_states[n0](lookups_keys[tag]))
        got = (bool(hit), act if hit else 0)
        assert got in allowed, f"lookup {tag} (key {lookups_keys[tag]:x}, cycle {cyc}): {got} not in {allowed}"
        if len(allowed) == 1:
            exact += 1
        else:
            amb += 1
    return exact, amb


# ------------------------------------------------------------------------------------------------ exact

def exact_case(seed, key_w=48, idx_w=6, stash=4, n_keys=170, n_lk=6000):
    r = random.Random(seed)
    keys = [r.getrandbits(key_w) for _ in range(n_keys)]
    t = model.ExactTable(key_w, idx_w, stash)
    states = [lambda k, s=copy.deepcopy(t): s.lookup(k)]
    cmds, want_status = [], []
    ops = [("ins", k) for k in keys]
    ops += [("del", r.choice(keys)) for _ in range(30)] + [("del", r.getrandbits(key_w)) for _ in range(5)]
    ops += [("ins", k) for k in r.sample(keys, 40)]           # refresh: used again
    ops += [("age",), ("ins", keys[0]), ("age",), ("op9",)] + [("ins", r.getrandbits(key_w)) for _ in range(20)]
    for o in ops:
        if o[0] == "ins":
            act = r.getrandbits(16)
            want_status.append(t.insert(o[1], act))
            prog_cmd(cmds, 1, key=o[1], act=act)
        elif o[0] == "del":
            want_status.append(t.delete(o[1]))
            prog_cmd(cmds, 2, key=o[1])
        elif o[0] == "age":
            want_status.append(t.age())
            prog_cmd(cmds, 3)
        else:
            want_status.append(model.BAD_OP)
            prog_cmd(cmds, 9)
        states.append(lambda k, s=copy.deepcopy(t): s.lookup(k))
    pool = keys + [r.getrandbits(key_w) for _ in range(50)]
    lks = [(0 if r.random() < 0.9 else r.randint(1, 5), r.choice(pool)) for _ in range(n_lk)]
    return lks, cmds, states, want_status, t


@pytest.mark.parametrize("seed,idx_w,stash", [(1, 6, 4), (2, 4, 0), (3, 7, 16)])
def test_exact_updates_under_traffic(tmp_path, seed, idx_w, stash):
    lks, cmds, states, want, t = exact_case(seed, idx_w=idx_w, stash=stash, n_lk=9000)
    res, polls, meta = run(tmp_path, 0, {"KEY_W": 48, "ACT_W": 16, "IDX_W": idx_w, "STASH": stash}, lks, cmds)
    assert [(s >> 4) & 0xF for _, s in polls] == want
    assert len(res) == len(lks)
    ex, amb = check_consistent(res, polls, states, [k for _, k in lks], LAT[0])
    assert ex > 0.9 * len(lks)
    if idx_w == 4:
        assert model.FULL in want                     # the full path is exercised
    if stash:
        assert t.stash_peak > 0                       # keys went to the stash (collision path exercised)


# ------------------------------------------------------------------------------------------------ LPM

B0, B1, B2 = [10, 44, 77, 100, 150, 172, 192, 203], [0, 16, 99, 168], [1, 200]


def lpm_routes(r, n):
    out, seen = [], set()
    while len(out) < n:
        ln = r.choice([0, 8, 12, 16, 16, 20, 24, 24, 24, 25, 28, 30, 32, 32, 7, 1, 17])
        # clustered like a real table: few /8s, few /16s inside them, few /24s inside those
        a = (r.choice(B0) << 24) | (r.choice(B1) << 16) | (r.choice(B2) << 8) | r.getrandbits(8)
        if r.random() < 0.1:
            a = r.getrandbits(32)
            ln = min(ln, 8)
        p = a & (((1 << ln) - 1) << (32 - ln) if ln else 0)
        if (p, ln) in seen:
            continue
        seen.add((p, ln))
        out.append((p, ln, r.getrandbits(12)))
    return out


def lpm_write_lines(words_new, words_old, lines):
    """Bottom-up: deepest level first, so new nodes exist before anything points at them."""
    keys = sorted(set(words_new) | set(words_old), key=lambda a: (-a[0], a[1]))
    n = 0
    for lv, idx in keys:
        w = words_new.get((lv, idx), 0)
        if w != words_old.get((lv, idx), 0):
            prog_cmd(lines, 1, addr=(lv << 14) | idx, raw=w)
            n += 1
    return n


def test_lpm_bit_exact_and_incremental(tmp_path):
    r = random.Random(4)
    nodes = (16, 32, 64)
    base = lpm_routes(r, 250)
    words, alloc = model.lpm_compile(base, 12, nodes)
    cmds = []
    lpm_write_lines(words, {}, cmds)
    n_base = len([c for c in cmds if c.startswith("W 40")])
    # the base load: lookups only after it (state index n_base)
    st_base = lambda a, R=list(base): model.lpm_oracle(R, a)
    states = [lambda a: (False, 0)] * n_base + [st_base]
    extra = [None] * (n_base + 1)
    # then one route at a time, each with its own bottom-up writes
    cur, cur_words = list(base), words
    for _ in range(25):
        nr = lpm_routes(r, 1)[0]
        if any((p, l) == (nr[0], nr[1]) for p, l, _ in cur):
            continue
        nxt = cur + [nr]
        nw, alloc = model.lpm_compile(nxt, 12, nodes, alloc)
        k = lpm_write_lines(nw, cur_words, cmds)
        # while this route's words are written, each address shows the old or the new answer (an expansion
        # rewrites several entries one by one); new nodes are unreachable until their parent entry is written last
        old_f = lambda a, R=list(cur): model.lpm_oracle(R, a)
        new_f = lambda a, R=list(nxt): model.lpm_oracle(R, a)
        extra += [new_f] * (k - 1) + [None]
        states += [old_f] * (k - 1) + [new_f]
        cur, cur_words = nxt, nw
    addrs = []
    for _ in range(12000):
        p, ln, _ = r.choice(cur)
        addrs.append((p | (r.getrandbits(32 - ln) if ln < 32 else 0)) if r.random() < 0.8 else r.getrandbits(32))
    lks = [(0, a) for a in addrs]
    res, polls, meta = run(tmp_path, 1, {"KEY_W": 32, "ACT_W": 12, "L1_NODES": 16, "L2_NODES": 32,
                                         "L3_NODES": 64}, lks, cmds, lk_after=n_base - 5)
    assert all(((s >> 4) & 0xF) == 0 for _, s in polls)
    # states per command: a route's intermediate writes may show old or new for that route only
    ex, amb = check_consistent(res, polls, states, addrs, LAT[1], extra_states=extra, min_n=n_base)
    assert ex > 1000
    tail = [x for x in res if x[1] - LAT[1] > polls[-1][0]]
    assert tail and all((bool(h), a if h else 0) == model.lpm_oracle(cur, addrs[t]) for t, _, h, a in tail)


# ------------------------------------------------------------------------------------------------ ternary

@pytest.mark.parametrize("kw,ent,chunk", [(40, 32, 5), (24, 8, 4), (48, 64, 6), (8, 1, 8)])
def test_ternary_updates_under_traffic(tmp_path, kw, ent, chunk):
    r = random.Random(5 + kw)
    t = model.TernaryTable(ent)
    states, mids, cmds = [lambda k, s=copy.deepcopy(t): s.lookup(k)], [], []
    rules = []
    for i in range(120):
        e = r.randrange(ent)
        if r.random() < 0.15:
            mids.append(None)
            t.delete(e)
            prog_cmd(cmds, 2, addr=e)
        else:
            if r.random() < 0.3:                  # broad rules (few cared bits) overlap the others: priority matters
                care = r.getrandbits(kw) & r.getrandbits(kw) & r.getrandbits(kw)
            else:
                care = r.getrandbits(kw) | (((1 << r.randint(0, min(20, kw))) - 1) << max(0, kw - 20))
            care &= (1 << kw) - 1
            val = r.getrandbits(kw) & care
            act = r.getrandbits(16)
            mid = copy.deepcopy(t)
            mid.delete(e)
            mids.append(lambda k, s=mid: s.lookup(k))
            t.write(e, val, care, act)
            rules.append((val, care))
            prog_cmd(cmds, 1, addr=e, key=val, care=care, act=act)
        states.append(lambda k, s=copy.deepcopy(t): s.lookup(k))
    keys = []
    for _ in range(9000):
        if rules and r.random() < 0.7:
            v, c = r.choice(rules)
            keys.append(v | (r.getrandbits(kw) & ~c & ((1 << kw) - 1)))
        else:
            keys.append(r.getrandbits(kw))
    res, polls, meta = run(tmp_path, 2, {"KEY_W": kw, "ACT_W": 16, "ENTRIES": ent, "CHUNK_W": chunk},
                           [(0, k) for k in keys], cmds)
    assert all(((s >> 4) & 0xF) == 0 for _, s in polls)
    ex, amb = check_consistent(res, polls, states, keys, LAT[2], extra_states=mids)
    assert ex > 0.5 * len(keys)
    # overlap: lookups that more than one rule of the final table matches
    multi = sum(1 for k in keys if sum(1 for e in t.e if e and ((k ^ e[0]) & e[1]) == 0) > 1)
    assert multi > 300 or ent == 1


@pytest.mark.parametrize("table,params", [
    (0, {"IDX_W": 1}), (0, {"STASH": 17}), (0, {"KEY_W": 0}),
    (1, {"L1_NODES": 65}), (1, {"ACT_W": 0}),
    (2, {"KEY_W": 41, "CHUNK_W": 5}), (2, {"ENTRIES": 300}), (2, {"CHUNK_W": 9, "KEY_W": 45})])
def test_table_guards(table, params):
    bad, out = sim.elaborate_fails(srcs(table), "tb_match_table", dict(params, TABLE=table))
    assert bad, out
