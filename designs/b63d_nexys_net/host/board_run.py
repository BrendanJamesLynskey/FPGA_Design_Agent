#!/usr/bin/env python3
"""Board run of designs/b63d_nexys_net on the Nexys A7-100T (brief 63D). Two phases:

  loopback  no network cable: the PHY's near-end loopback (MDIO, BMCR bit 14) returns every frame the design sends.
            The host injects an ARP request, an echo request and a UDP datagram from an invented PC address and reads
            back the design's answers with the frame capture, each checked against the library models.
  link      an isolated cable to a PC (never the home network): the PC pings the board, reads its ARP entry, asks the
            UDP statistics service for the counters, and sends to a multicast group before and after the board joins it.
            Refused unless --isolated-link-confirmed is given (the owner confirms the cabling first).

Operating conditions (XADC Tj, VCCINT, VCCAUX, VCCBRAM) are read at the start, between steps and at the end, and
written with the results: python3 -m designs.b63d_nexys_net.host.board_run --port /dev/ttyUSB1 --phase loopback
--out results/b63d/board_loopback.json
"""
from __future__ import annotations

import argparse
import json
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from flow.net import inet  # noqa: E402
from hil.instruments.shell_instruments import xadc_temp_c, xadc_volts  # noqa: E402
from ip_lib.arp_responder import model as arpm  # noqa: E402
from ip_lib.eth_mac_rgmii import model as macm  # noqa: E402
from ip_lib.icmp_echo import model as icmpm  # noqa: E402

W = 0x80
DESIGN_ID = 0x4E363344
BOARD_IP, BOARD_MAC = "192.168.63.2", "02:00:00:00:00:63"
PHY_ADDR = 1                                   # the board's RXER/PHYAD0 pull-up (boards/nexys_a7_100t/inventory.yaml)
from flow.program import ROC  # noqa: E402  (the recommended operating conditions the flow already checks)
LIMITS = {"tj_c": (-40.0, ROC["TEMPERATURE"][1]), "vccint_v": ROC["VCCINT"], "vccaux_v": ROC["VCCAUX"],
          "vccbram_v": ROC["VCCBRAM"]}


def conditions(sh) -> dict:
    c = [sh.read(W + 0x38 + i) & 0xFFF for i in range(4)]
    d = {"t": time.time(), "tj_c": round(xadc_temp_c(c[0]), 2), "vccint_v": round(xadc_volts(c[1]), 4),
         "vccaux_v": round(xadc_volts(c[2]), 4), "vccbram_v": round(xadc_volts(c[3]), 4)}
    d["inside_roc"] = all(lo <= d[k] <= hi for k, (lo, hi) in LIMITS.items())
    return d


def mdio(sh, reg: int, value: int | None = None) -> int:
    cmd = (PHY_ADDR << 21) | (reg << 16) | (1 << 30 if value is None else value)
    sh.write(W + 4, cmd)
    for _ in range(100):
        r = sh.read(W + 4)
        if not r >> 31:
            return r & 0xFFFF
    raise RuntimeError("MDIO access did not finish")


def inject(sh, frame: bytes) -> None:
    frame = frame.ljust(60, b"\x00")
    sh.write(W + 0x42, 0)
    for i in range(0, len(frame), 4):
        sh.write(W + 0x41, int.from_bytes(frame[i:i + 4].ljust(4, b"\x00"), "big"))
    sh.write(W + 0x40, (1 << 31) | len(frame))


def capture(sh, skip: int, send) -> bytes:
    """Arm the capture to keep the frame after `skip` others, run send(), read the frame back."""
    sh.write(W + 0x48, 1 | (skip << 4))
    send()
    for _ in range(200):
        st = sh.read(W + 0x48)
        if st >> 31:
            break
        time.sleep(0.01)
    else:
        raise RuntimeError("nothing captured")
    n = st & 0x7FF
    sh.write(W + 0x49, 0)
    return bytes(sh.read(W + 0x4A) & 0xFF for _ in range(n))


def stats(sh) -> dict:
    return {n: sh.read(W + 0x10 + i) for i, n in enumerate(macm.STAT_NAMES)}


def loopback(sh, out: dict) -> bool:
    own_mac, own_ip = inet.mac_b(BOARD_MAC), inet.ip_b(BOARD_IP)
    pc_mac, pc_ip = inet.mac_b("02:00:00:00:00:01"), inet.ip_b("192.168.63.1")
    ok = True
    out["phy_id"] = [hex(mdio(sh, 2)), hex(mdio(sh, 3))]
    out["bmsr"] = hex(mdio(sh, 1))
    mdio(sh, 0, 0x6100)                         # loopback, 100 Mb/s, full duplex (BMCR, IEEE 802.3 clause 22)
    time.sleep(0.1)
    sh.write(W + 9, 1)                          # clear the counters
    checks = []
    # ARP: the design sees its own injected request (looped) and answers; the answer loops back too
    req = inet.eth(arpm.BCAST, pc_mac, 0x0806, inet.arp(1, pc_mac, pc_ip, b"\x00" * 6, own_ip))
    got = capture(sh, 1, lambda: inject(sh, req))
    want = arpm.reply(own_mac, own_ip, {"sha": pc_mac, "spa": pc_ip}).ljust(60, b"\x00")
    checks.append({"step": "arp", "ok": got == want, "got": got.hex()})
    # ping
    ping = icmpm.request(pc_mac, own_mac, pc_ip, own_ip, 0x63D, 1, bytes(range(32)))
    got = capture(sh, 1, lambda: inject(sh, ping))
    want = icmpm.reply(ping, own_mac, own_ip, 64)[0].ljust(60, b"\x00")
    checks.append({"step": "ping", "ok": got == want, "got": got.hex()})
    # the UDP statistics service (the PC's MAC is in the ARP cache from the request above)
    u = inet.udp(pc_ip, own_ip, 40000, 5000, b"stats")
    dg = inet.eth(own_mac, pc_mac, 0x0800, inet.ipv4(pc_ip, own_ip, 17, u))
    got = capture(sh, 1, lambda: inject(sh, dg))
    good = len(got) >= 42 + 88 and got[:6] == pc_mac and got[42:46] == b"N63D" and inet.ok(got[14:34])
    checks.append({"step": "udp_service", "ok": good, "got": got.hex()})
    out["checks"] = checks
    out["stats"] = stats(sh)
    mdio(sh, 0, 0x3100)                         # loopback off, auto-negotiation on, restarted
    ok = all(c["ok"] for c in checks)
    return ok


def link(sh, out: dict, iface: str) -> bool:
    """On an isolated link with the PC at 192.168.63.1/24 on `iface`."""
    r = subprocess.run(["ping", "-c", "5", "-W", "1", "-I", iface, BOARD_IP], capture_output=True, text=True)
    out["ping"] = r.stdout.strip().splitlines()[-2:] if r.stdout else r.stderr
    neigh = subprocess.run(["ip", "neigh", "show", BOARD_IP, "dev", iface], capture_output=True, text=True).stdout
    out["arp"] = neigh.strip()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(1.0)
    s.sendto(b"stats", (BOARD_IP, 5000))
    try:
        data, _ = s.recvfrom(2048)
        out["udp_service"] = {"magic": data[:4].decode(errors="replace"),
                              "counters": dict(zip(macm.STAT_NAMES, struct.unpack(">21I", data[4:88])))}
    except socket.timeout:
        out["udp_service"] = None
    # multicast: not answered before the board joins 239.63.0.1, answered after
    m = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    m.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
    m.settimeout(1.0)
    res = {}
    for joined in (False, True):
        sh.write(W + 7, int(joined))
        time.sleep(0.5)
        m.sendto(b"stats", ("239.63.0.1", 5000))
        try:
            m.recvfrom(2048)
            res[str(joined)] = True
        except socket.timeout:
            res[str(joined)] = False
    out["multicast_answered"] = res
    sh.write(W + 7, 0)
    return ("0% packet loss" in " ".join(out["ping"] or [])) and BOARD_MAC in out["arp"].lower() and \
        out["udp_service"] is not None and res == {"False": False, "True": True}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", required=True)
    ap.add_argument("--phase", choices=["loopback", "link"], required=True)
    ap.add_argument("--iface", default="", help="link phase: the PC's interface on the isolated link")
    ap.add_argument("--isolated-link-confirmed", action="store_true",
                    help="the owner has confirmed the cable goes only to this PC's isolated interface")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.phase == "link" and not (a.isolated_link_confirmed and a.iface):
        sys.exit("link phase: needs --iface and --isolated-link-confirmed (the owner checks the cabling first)")
    from shell.host.fpga_shell import FpgaShell
    sh = FpgaShell.open(a.port)
    assert sh.read(0) == DESIGN_ID, "not the b63d_nexys_net bitstream"
    out = {"phase": a.phase, "conditions": [conditions(sh)]}
    ok = loopback(sh, out) if a.phase == "loopback" else link(sh, out, a.iface)
    out["conditions"].append(conditions(sh))
    out["inside_roc"] = all(c["inside_roc"] for c in out["conditions"])
    out["pass"] = bool(ok)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: out[k] for k in ("phase", "pass", "inside_roc")}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
