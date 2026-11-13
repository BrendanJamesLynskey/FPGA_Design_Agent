#!/usr/bin/env python3
"""Board run of designs/b63d_nexys_net on the Nexys A7-100T. Two phases:

  loopback  no network cable in the board's Ethernet jack (J4): the PHY's near-end loopback (set over MDIO, BMCR bit
            14) is expected to return every frame the design sends. The host injects an ARP request, an echo request
            and a UDP datagram from an invented PC address and reads back the design's answers with the frame capture,
            each checked against the library models.
  link      one cable from J4 straight to a PC interface that is on no other network. Before any traffic the script
            checks the isolation itself (isolation_check) and refuses if the interface has a default route, carries the
            default route, has any address but 192.168.63.1/24, or if anything but the board answers on the subnet.
            Every socket is bound to that interface (SO_BINDTODEVICE when allowed, else its source address), and the
            multicast socket sends through it with TTL 1. Then: ping, the board's neighbour entry, the UDP statistics
            service, and a datagram to a multicast group before and after the board joins it.

Operating conditions (XADC Tj, VCCINT, VCCAUX, VCCBRAM and the alarms the design latches between polls) are read at
the start, between steps and at the end, and written with the results. Example:
    python3 designs/b63d_nexys_net/host/board_run.py --port /dev/ttyUSB1 --phase loopback --out board_loopback.json
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import re
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from flow.net import inet  # noqa: E402
from flow.program import ROC  # noqa: E402  (the recommended operating conditions the flow already checks)
from hil.instruments.shell_instruments import xadc_temp_c, xadc_volts  # noqa: E402
from ip_lib.arp_responder import model as arpm  # noqa: E402
from ip_lib.eth_mac_rgmii import model as macm  # noqa: E402
from ip_lib.icmp_echo import model as icmpm  # noqa: E402

W = 0x80
DESIGN_ID = 0x4E363344
BOARD_IP, BOARD_MAC = "192.168.63.2", "02:00:00:00:00:63"      # locally administered example address
PC_IP = "192.168.63.1"
SUBNET = ipaddress.ip_network("192.168.63.0/24")
GROUP = "239.63.0.1"
PHY_ADDR = 1                                   # the board's RXER/PHYAD0 pull-up (boards/nexys_a7_100t/inventory.yaml)
LIMITS = {"tj_c": (-40.0, ROC["TEMPERATURE"][1]), "vccint_v": ROC["VCCINT"], "vccaux_v": ROC["VCCAUX"],
          "vccbram_v": ROC["VCCBRAM"]}
ALARMS = ["tj", "vccint", "vccaux", "vccbram", "over_temperature"]
SO_BINDTODEVICE = getattr(socket, "SO_BINDTODEVICE", 25)


# ------------------------------------------------------------------------------------------------ board access
def conditions(sh, label: str) -> dict:
    """One sample: the XADC codes and the alarms latched since the last sample (then cleared)."""
    c = [sh.read(W + 0x38 + i) & 0xFFF for i in range(4)]
    alm = sh.read(W + 0x3C) & 0x1F
    sh.write(W + 0x3C, 0)
    d = {"label": label, "t": time.time(), "tj_c": round(xadc_temp_c(c[0]), 2), "vccint_v": round(xadc_volts(c[1]), 4),
         "vccaux_v": round(xadc_volts(c[2]), 4), "vccbram_v": round(xadc_volts(c[3]), 4),
         "alarms": [a for i, a in enumerate(ALARMS) if alm >> i & 1]}
    d["inside_roc"] = all(lo <= d[k] <= hi for k, (lo, hi) in LIMITS.items()) and not d["alarms"]
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


# ------------------------------------------------------------------------------------------------ loopback phase
def loopback(sh, out: dict) -> bool:
    own_mac, own_ip = inet.mac_b(BOARD_MAC), inet.ip_b(BOARD_IP)
    pc_mac, pc_ip = inet.mac_b("02:00:00:00:00:01"), inet.ip_b(PC_IP)
    out["phy_id"] = [hex(mdio(sh, 2)), hex(mdio(sh, 3))]
    out["bmsr"] = hex(mdio(sh, 1))
    mdio(sh, 0, 0x6100)                         # loopback, 100 Mb/s, full duplex (BMCR, IEEE 802.3 clause 22)
    time.sleep(0.1)
    sh.write(W + 9, 1)                          # clear the counters
    checks = []
    req = inet.eth(arpm.BCAST, pc_mac, 0x0806, inet.arp(1, pc_mac, pc_ip, b"\x00" * 6, own_ip))
    got = capture(sh, 1, lambda: inject(sh, req))
    want = arpm.reply(own_mac, own_ip, {"sha": pc_mac, "spa": pc_ip}).ljust(60, b"\x00")
    checks.append({"step": "arp", "ok": got == want, "got": got.hex()})
    out["conditions"].append(conditions(sh, "after arp"))
    ping = icmpm.request(pc_mac, own_mac, pc_ip, own_ip, 0x63D, 1, bytes(range(32)))
    got = capture(sh, 1, lambda: inject(sh, ping))
    want = icmpm.reply(ping, own_mac, own_ip, 64)[0].ljust(60, b"\x00")
    checks.append({"step": "ping", "ok": got == want, "got": got.hex()})
    out["conditions"].append(conditions(sh, "after ping"))
    u = inet.udp(pc_ip, own_ip, 40000, 5000, b"stats")
    dg = inet.eth(own_mac, pc_mac, 0x0800, inet.ipv4(pc_ip, own_ip, 17, u))
    got = capture(sh, 1, lambda: inject(sh, dg))
    good = len(got) >= 42 + 88 and got[:6] == pc_mac and got[42:46] == b"N63D" and inet.ok(got[14:34])
    checks.append({"step": "udp_service", "ok": good, "got": got.hex()})
    out["conditions"].append(conditions(sh, "after udp service"))
    out["checks"] = checks
    out["stats"] = stats(sh)
    mdio(sh, 0, 0x3100)                         # loopback off, auto-negotiation on, restarted
    return all(c["ok"] for c in checks)


# ------------------------------------------------------------------------------------------------ link phase
def _run(*cmd: str) -> str:
    return subprocess.run(list(cmd), capture_output=True, text=True).stdout


STACKED_KINDS = ("vlan", "macvlan", "macvtap", "ipvlan", "ipvtap", "bridge", "bridge_slave", "bond", "bond_slave",
                 "team", "team_slave", "veth", "tun", "tap", "vxlan", "gre", "gretap", "ipip", "sit", "wireguard",
                 "vrf", "vrf_slave", "dummy", "geneve")


def isolation_check(iface: str, runner=_run) -> list[str]:
    """Reasons the interface is not an isolated link to the board (empty: isolated). Run before any traffic, and
    again after the first ping, when the neighbour table can show other hosts. `runner` runs a command and returns
    its standard output (a stand-in in the tests). It sees only this PC's view of the interface: it cannot see past the
    cable, so the cabling confirmation is still needed."""
    why = []
    # the interface itself: a plain physical link, not stacked on or enslaved to another (a VLAN or macvlan on the home
    # NIC would put every frame on the home LAN however it is addressed)
    link = runner("ip", "-d", "-o", "link", "show", "dev", iface)
    if not link.strip():
        why.append(f"{iface} does not exist")
    else:
        head = link.split(":", 2)[1].strip() if link.count(":") >= 2 else ""
        if "@" in head:
            why.append(f"{iface} is stacked on another interface ({head})")
        if re.search(r"\bmaster \S+", link):
            why.append(f"{iface} is enslaved to another interface ({re.search(r'master (\S+)', link).group(1)})")
        kinds = [k for k in STACKED_KINDS if re.search(rf"(?:^|\s){k}(?:\s|$)", link)]
        if kinds:
            why.append(f"{iface} is a {', '.join(kinds)} interface, not a plain physical link")
    # IPv4: exactly 192.168.63.1/24, in the a.b.c.d/n form (a peer-form address is refused)
    lines = [l for l in runner("ip", "-4", "-o", "addr", "show", "dev", iface).splitlines() if " inet " in f" {l} "]
    if not lines:
        why.append(f"{iface} has no IPv4 address")
    for l in lines:
        m = re.search(r"\binet (\S+)", l)
        tok = m.group(1) if m else ""
        if not re.fullmatch(r"\d+\.\d+\.\d+\.\d+/\d+", tok) or " peer " in l:
            why.append(f"{iface} has an address not in plain a.b.c.d/n form: {l.strip()}")
            continue
        a = ipaddress.ip_interface(tok)
        if a.network != SUBNET or str(a.ip) != PC_IP:
            why.append(f"{iface} has {tok}; only {PC_IP}/24 is allowed")
    # IPv6: link-local only (a global or unique-local address means a router or another network is on the wire)
    for l in runner("ip", "-6", "-o", "addr", "show", "dev", iface).splitlines():
        m = re.search(r"\binet6 (\S+)", l)
        if m and not ipaddress.ip_interface(m.group(1)).ip.is_link_local:
            why.append(f"{iface} has the IPv6 address {m.group(1)}")
    # routes: in every table, nothing on this interface but the subnet itself (no default, no 0/1 + 128/1 split, no
    # other prefix)
    for l in runner("ip", "-4", "route", "show", "table", "all", "dev", iface).splitlines():
        t = l.split()
        if not t:
            continue
        dst = t[1] if t[0] in ("local", "broadcast", "unicast", "multicast", "anycast", "blackhole", "unreachable",
                              "prohibit", "throw", "nat") and len(t) > 1 else t[0]
        try:
            net = ipaddress.ip_network("0.0.0.0/0" if dst == "default" else dst, strict=False)
        except ValueError:
            why.append(f"a route on {iface} that does not parse: {l.strip()}")
            continue
        if not net.subnet_of(SUBNET):
            why.append(f"{iface} carries a route other than {SUBNET}: {l.strip()}")
    defaults = runner("ip", "-4", "route", "show", "table", "all", "default")
    if re.search(rf"\bdev {re.escape(iface)}\b", defaults):
        why.append(f"{iface} carries a default route")
    # the home gateway must not be reachable by this interface
    for gw in sorted(set(re.findall(r"\bvia (\d+\.\d+\.\d+\.\d+)", defaults))):
        m = re.search(r"\bdev (\S+)", runner("ip", "-4", "route", "get", gw))
        if m and m.group(1) == iface:
            why.append(f"{iface} carries the route to the gateway {gw}")
    for dst in (BOARD_IP, GROUP):
        m = re.search(r"\bdev (\S+)", runner("ip", "-4", "route", "get", dst, "oif", iface))
        if not m or m.group(1) != iface:
            why.append(f"{dst} would not leave by {iface}")
    m = re.search(r"\bdev (\S+)", runner("ip", "-4", "route", "get", BOARD_IP))
    if not m or m.group(1) != iface:
        why.append(f"the routing table sends {BOARD_IP} by {m.group(1) if m else 'nothing'}, not {iface}")
    # neighbours: only the board, and the board's address only with the board's MAC
    for line in runner("ip", "-4", "neigh", "show", "dev", iface).splitlines():
        t = line.split()
        if not t or "FAILED" in line or "INCOMPLETE" in line:
            continue
        mac = re.search(r"\blladdr (\S+)", line)
        if t[0] != BOARD_IP:
            why.append(f"another host answers on {iface}: {line.strip()}")
        elif mac and mac.group(1).lower() != BOARD_MAC:
            why.append(f"{BOARD_IP} answers with {mac.group(1)}, not the board's {BOARD_MAC}")
    return why


def ping_ok(text: str, count: int) -> bool:
    """True only when every echo request was answered (a numeric parse: '100% packet loss' is a failure)."""
    m = re.search(r"(\d+) packets transmitted, (\d+) (?:packets )?received", text)
    loss = re.search(r"(\d+(?:\.\d+)?)% packet loss", text)
    return bool(m and loss) and int(m.group(1)) == count and int(m.group(2)) == count and float(loss.group(1)) == 0.0


def bound_socket(iface: str, multicast: bool = False) -> socket.socket:
    """A UDP socket that can only use `iface`: SO_BINDTODEVICE when the kernel allows it, and in any case bound to
    the PC's address on that interface (isolation_check has made sure no other interface has it); multicast leaves by
    that interface with TTL 1 and no loopback."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, SO_BINDTODEVICE, iface.encode() + b"\0")
    except PermissionError:
        pass
    s.bind((PC_IP, 0))
    if multicast:
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(PC_IP))
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 0)
    s.settimeout(1.0)
    return s


def link(sh, out: dict, iface: str) -> bool:
    """On an isolated link with the PC at 192.168.63.1/24 on `iface`."""
    why = isolation_check(iface)
    if why:
        out["refused"] = why
        return False
    broadcast = _run("ping", "-b", "-c", "2", "-W", "1", "-I", iface, str(SUBNET.broadcast_address))
    if re.search(r"bytes from (?!" + re.escape(BOARD_IP) + r"\b)", broadcast):
        out["refused"] = [f"another host answers a broadcast ping on {iface}"]
        return False
    r = _run("ping", "-c", "5", "-W", "1", "-I", iface, BOARD_IP)
    out["ping"] = r.strip().splitlines()[-2:]
    out["ping_ok"] = ping_ok(r, 5)
    why = isolation_check(iface)                # the neighbour table after the first exchange
    if why:
        out["refused"] = why
        return False
    out["conditions"].append(conditions(sh, "after ping"))
    out["arp"] = _run("ip", "neigh", "show", BOARD_IP, "dev", iface).strip()
    s = bound_socket(iface)
    s.sendto(b"stats", (BOARD_IP, 5000))
    try:
        data, _ = s.recvfrom(2048)
        out["udp_service"] = {"magic": data[:4].decode(errors="replace"),
                              "counters": dict(zip(macm.STAT_NAMES, struct.unpack(">21I", data[4:88])))}
    except socket.timeout:
        out["udp_service"] = None
    out["conditions"].append(conditions(sh, "after udp service"))
    m = bound_socket(iface, multicast=True)
    res = {}
    for joined in (False, True):
        sh.write(W + 7, int(joined))
        time.sleep(0.5)
        m.sendto(b"stats", (GROUP, 5000))
        try:
            m.recvfrom(2048)
            res[str(joined)] = True
        except socket.timeout:
            res[str(joined)] = False
    out["multicast_answered"] = res
    sh.write(W + 7, 0)
    out["conditions"].append(conditions(sh, "after multicast"))
    return out["ping_ok"] and BOARD_MAC in out["arp"].lower() and out["udp_service"] is not None and \
        res == {"False": False, "True": True}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", required=True, help="the test shell's UART device, e.g. /dev/ttyUSB1")
    ap.add_argument("--phase", choices=["loopback", "link"], required=True,
                    help="loopback: no cable in J4, the PHY loops frames back; link: one cable from J4 to an isolated "
                         "PC interface")
    ap.add_argument("--iface", default="", help="link phase: the PC's interface on the isolated link (for example enx1); "
                                                "it must be a plain physical interface set to 192.168.63.1/24")
    ap.add_argument("--isolated-link-confirmed", action="store_true",
                    help="confirm the cable runs only from J4 to this isolated interface; the script also checks the "
                         "interface's addresses and routes before sending")
    ap.add_argument("--out", required=True, help="JSON results file")
    a = ap.parse_args()
    if a.phase == "link" and not (a.isolated_link_confirmed and a.iface):
        sys.exit("link phase: needs --iface and --isolated-link-confirmed")
    if a.phase == "link":
        why = isolation_check(a.iface)
        if why:
            sys.exit("link phase refused: " + "; ".join(why))
    from shell.host.fpga_shell import FpgaShell
    sh = FpgaShell.open(a.port)
    assert sh.read(0) == DESIGN_ID, "not the b63d_nexys_net bitstream"
    sh.write(W + 0x3C, 0)                       # clear any alarm latched before this run
    out = {"phase": a.phase, "conditions": [conditions(sh, "start")]}
    ok = loopback(sh, out) if a.phase == "loopback" else link(sh, out, a.iface)
    out["conditions"].append(conditions(sh, "end"))
    out["inside_roc"] = all(c["inside_roc"] for c in out["conditions"])
    out["pass"] = bool(ok)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: out.get(k) for k in ("phase", "pass", "inside_roc", "refused")}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
