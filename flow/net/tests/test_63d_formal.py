"""SymbiYosys jobs of the network entries (ip_lib/<entry>/formal): the MDIO frame proved by k-induction; the transmit framing
and AXI-Stream rules (the AXI checker's axis_rules) of arp_responder, icmp_echo, ipv4_udp_rx, ipv4_udp_tx and igmp_join, and
the address filter of eth_mac_rgmii against the rule restated in the harness, by bounded model checking (not proofs);
covers that each block can do its job. Skipped where sby is not installed (CI: the verification job installs it).

    python3 flow/net/tests/test_63d_formal.py --json results/b63d/formal.json     # run all, record the verdicts
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
IP = ROOT / "ip_lib"
# (entry, sby file, task, what it shows)
JOBS = [
    ("mdio_master", "mdio.sby", "prove", "frame position, MDC waveform, line releases and setup/hold: k-induction proof"),
    ("mdio_master", "mdio.sby", "cover", "a whole read frame completes"),
    ("arp_responder", "arp.sby", "bmc", "42-byte frames, AXI-Stream rules, lookups answered only when asked: bounded, 60 clocks"),
    ("arp_responder", "arp.sby", "cover", "a reply and a request leave"),
    ("icmp_echo", "icmp.sby", "bmc", "AXI-Stream rules, no reply without a request, and the reply carries the request it answers (byte 13 equal) whatever frame follows it: bounded, 64 clocks; fails at step 60 with the round-1 back-to-back bug restored"),
    ("icmp_echo", "icmp.sby", "cover", "a whole reply to a minimal echo request"),
    ("ipv4_udp_rx", "udp_rx.sby", "bmc", "AXI-Stream rules with tuser, tdest and header fields; input held after a frame: bounded, 30 clocks"),
    ("ipv4_udp_rx", "udp_rx.sby", "cover", "a whole datagram parsed and passed on"),
    ("ipv4_udp_tx", "udp_tx.sby", "bmc", "frames of 42 bytes plus the payload, AXI-Stream rules, input held while sending: bounded, 60 clocks"),
    ("ipv4_udp_tx", "udp_tx.sby", "cover", "a two-byte datagram leaves"),
    ("igmp_join", "igmp.sby", "bmc", "46-byte frames, AXI-Stream rules: bounded, 60 clocks"),
    ("igmp_join", "igmp.sby", "cover", "a report and a leave leave"),
    ("eth_mac_rgmii", "classify.sby", "bmc", "the address filter's verdict equals the restated rule: bounded, 12 clocks"),
    ("eth_mac_rgmii", "classify.sby", "cover", "a multicast address accepted by the table or the hash"),
]


LAST = {}


def run(entry: str, sby: str, task: str, out: Path) -> str:
    r = subprocess.run(["sby", "-f", "-d", str(out), sby, task], cwd=IP / entry / "formal", capture_output=True,
                       text=True, timeout=3600)
    LAST["log"] = (r.stdout + r.stderr)[-3000:]
    return (out / "status").read_text().split()[0] if (out / "status").exists() else "ABSENT"


@pytest.mark.skipif(shutil.which("sby") is None, reason="SymbiYosys not installed")
@pytest.mark.parametrize("entry,sby,task", [j[:3] for j in JOBS], ids=[f"{j[0]}-{j[2]}" for j in JOBS])
def test_formal(tmp_path, entry, sby, task):
    assert run(entry, sby, task, tmp_path / f"{entry}_{task}") == "PASS", LAST["log"]


if __name__ == "__main__":
    import argparse
    import tempfile
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    a = ap.parse_args()
    ver = subprocess.run(["yosys", "-V"], capture_output=True, text=True).stdout.strip()
    rows = []
    with tempfile.TemporaryDirectory() as t:
        for entry, sby, task, what in JOBS:
            t0 = time.time()
            st = run(entry, sby, task, Path(t) / f"{entry}_{task}")
            rows.append({"entry": entry, "job": f"{sby} {task}", "what": what, "status": st,
                         "seconds": round(time.time() - t0, 1)})
            print(f"{st:6s} {entry:14s} {sby} {task}  {rows[-1]['seconds']} s", flush=True)
    Path(a.json).parent.mkdir(parents=True, exist_ok=True)
    Path(a.json).write_text(json.dumps({"tool": ver, "engine": "smtbmc boolector", "jobs": rows}, indent=1) + "\n")
    sys.exit(0 if all(r["status"] == "PASS" for r in rows) else 1)
