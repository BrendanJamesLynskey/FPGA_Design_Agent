"""Brief 113: the board's own stream in simulation. Compares one run of results/b113/ml_sim.sh in +LOOP mode (the generator's feed frames, ADD ask 99.50 size 1 for instrument 1, looped back through the
near-end loop: the stream the board script sends) with the prediction the board driver uses (designs/b96_kr260_10g/host/b113_ml.py predict).

usage: python3 results/b113/loop_check.py <log> <frames> <veto 0|1> <out.json>"""
import json
import sys

from designs.b96_kr260_10g.host import b113_ml as m


def main() -> int:
    log, n, veto, out = sys.argv[1], int(sys.argv[2]), sys.argv[3] == "1", sys.argv[4]
    regs, mlv = {}, {}
    for ln in open(log):
        t = ln.split()
        if t and t[0] == "REG":
            regs[t[1]] = int(t[2])
        elif t and t[0] == "MLV":
            mlv[int(t[1])] = int(t[2])
    want = m.predict(n, veto)
    got = {k: mlv.get(i) for i, k in enumerate(m.MLV_NAMES)}
    res = {"frames": n, "veto": veto, "predicted": want, "stage_counters": got, "tx_n_order": regs.get("tx_n_order"), "rx_fired": regs.get("rx_fired"),
           "safety": {k: regs.get(k) for k in ("tx_poisoned", "tx_dropped", "tx_underrun", "tx_late", "tx_stale", "rx_err", "rx_ovf")}}
    res["pass"] = all(got[k] == want[k] for k in m.MLV_NAMES) and regs.get("tx_n_order") == want["orders"] and regs.get("rx_fired") == want["orders"] and not any(res["safety"].values())
    json.dump(res, open(out, "w"), indent=1)
    print("PASS" if res["pass"] else "FAIL", json.dumps({"stage": got, "orders": regs.get("tx_n_order")}))
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
