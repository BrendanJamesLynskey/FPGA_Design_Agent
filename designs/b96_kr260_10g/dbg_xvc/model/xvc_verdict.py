"""Brief 131: the PRE-REGISTERED verdict of the dbg_xvc board test (docs/xvc_board_test.md), written before any board time. NOT YET RUN ON A BOARD.

Input: the record that dbg_xvc/board/xvc_board_session.sh collects (a dict, JSON on disk). Output: (verdict, reasons). The criteria are the constants below; nothing is tuned
after a run. A criterion that cannot be evaluated (a key missing) is a FAIL, never a pass by default.
"""

from __future__ import annotations

import json
import sys

#: Linux must keep running: the 1 Hz heartbeat written on the board during the whole test may not have a gap longer than this, in seconds
MAX_HEARTBEAT_GAP_S = 3.0
#: Vivado must find the ILA through XVC within this many seconds of the connection command
MAX_CONNECT_S = 60.0
#: the ILA core as built: one probe of 38 bits (ip/amd_ip_xvc.tcl), 1024 samples
ILA_PROBE_WIDTH = 38
ILA_SAMPLES = 1024
#: repeated capture-and-upload cycles with the trigger set to "immediate"
N_CAPTURES = 20
#: bits that the 2026-11-17 board run measured with the laser off (results/b96/hw/20261117_101326/stage3.json): rx_los 1, mod_abs 0, tx_fault 0; pgood is 1 whenever the GT is powered
EXPECT_STATIC = {"rx_los": 1, "mod_abs": 0, "tx_fault": 0, "pgood": 1}
#: a trigger on pcs_lock = 1 must stay armed and not fire while the laser is off (no light, so no block lock)
HELD_TRIGGER_S = 30.0


def verdict(rec: dict) -> tuple[str, list[str]]:
    why: list[str] = []

    def need(path: str):
        cur = rec
        for k in path.split("."):
            if not isinstance(cur, dict) or k not in cur:
                why.append(f"FAIL: record has no {path}")
                return None
            cur = cur[k]
        return cur

    # T0: no JTAG cable traffic during the test (the reason for the whole build)
    j = need("jtag_cable_used")
    if j is not False and j is not None:
        why.append("FAIL: the JTAG cable was used during the test (it must be unplugged or its hw_server never opened)")
    # T1: Linux alive
    gaps = need("heartbeat_gaps_s")
    if gaps is not None:
        if not gaps:
            why.append("FAIL: no heartbeat recorded")
        elif max(gaps) > MAX_HEARTBEAT_GAP_S:
            why.append(f"FAIL: heartbeat gap {max(gaps):.1f} s > {MAX_HEARTBEAT_GAP_S} s")
    errs = need("dmesg_new_errors")
    if errs:
        why.append(f"FAIL: {len(errs)} new kernel error line(s) during the test")
    # T2: Vivado reaches the ILA over the network
    if need("xvc.connected") is not True:
        why.append("FAIL: Vivado did not connect over XVC")
    if need("xvc.ila_count") != 1:
        why.append(f"FAIL: ILA cores found: {rec.get('xvc', {}).get('ila_count')} (expected 1)")
    if need("xvc.probe_width") != ILA_PROBE_WIDTH:
        why.append(f"FAIL: probe width {rec.get('xvc', {}).get('probe_width')} (expected {ILA_PROBE_WIDTH})")
    t = need("xvc.connect_s")
    if isinstance(t, (int, float)) and t > MAX_CONNECT_S:
        why.append(f"FAIL: connection took {t:.0f} s > {MAX_CONNECT_S:.0f} s")
    # T3: a trigger that cannot fire stays armed; immediate trigger captures
    held = need("held_trigger_s")
    if isinstance(held, (int, float)) and held < HELD_TRIGGER_S:
        why.append(f"FAIL: the pcs_lock trigger ended after {held:.0f} s (< {HELD_TRIGGER_S:.0f} s: it fired, or the core stopped)")
    caps = need("captures")
    if isinstance(caps, list):
        if len(caps) != N_CAPTURES:
            why.append(f"FAIL: {len(caps)} captures (expected {N_CAPTURES})")
        bad = [i for i, c in enumerate(caps) if not (c.get("ok") is True and c.get("samples") == ILA_SAMPLES)]
        if bad:
            why.append(f"FAIL: captures {bad} did not return {ILA_SAMPLES} samples")
    # T4: the captured bits agree with what the board is known to show with the laser off
    st = need("static_bits")
    if isinstance(st, dict):
        for k, v in EXPECT_STATIC.items():
            if st.get(k) != v:
                why.append(f"FAIL: captured {k} = {st.get(k)}, expected {v}")
    return ("FAIL" if why else "PASS"), why or ["all pre-registered criteria met"]


def main() -> None:
    rec = json.load(open(sys.argv[1]))
    v, why = verdict(rec)
    print(v)
    for w in why:
        print(" -", w)
    sys.exit(0 if v == "PASS" else 1)


if __name__ == "__main__":
    main()
