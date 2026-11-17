"""Wire-to-wire latency from a PC network card's timestamps (brief 96 stage 3 step 4). NOT YET RUN ON A NIC.

Sends one Bench Feed v1 feed packet (an ADD on the ask side at a price below the board's threshold) to the board, waits for the board's order, and
prints the card's TX timestamp of the packet and RX timestamp of the order, so wire-to-wire = rx_hw - tx_hw. Hardware timestamping must be enabled on the
card (`enable_hw_timestamps`, SIOCSHWTSTAMP: RX filter ALL, TX ON); `--software` uses the kernel's software stamps instead (for testing the plumbing on `lo`,
and as a clearly labelled much coarser figure).

What the number is: the card stamps when the frame leaves or enters its MAC (the exact point and the resolution are the card's: ConnectX-4 Lx stamps
with its free-running clock, resolution and accuracy to be taken from its documentation and recorded with the result, not assumed). It includes the
board's whole path (RX PHY and PCS, trading path, TX PCS and PHY, the GT's serialiser and CDR) and the cable and optics both ways; the report subtracts
the cable (about 4.9 ns per metre one way, measured length) and states the card's own figures with their source."""

from __future__ import annotations

import argparse
import ctypes
import fcntl
import json
import socket
import struct
import time

SO_TIMESTAMPING = 37
SCM_TIMESTAMPING = SO_TIMESTAMPING
SIOCSHWTSTAMP = 0x89B0
F_TX_HW, F_TX_SW, F_RX_HW, F_RX_SW, F_SOFTWARE, F_RAW_HW, F_OPT_ID, F_OPT_TSONLY = 1 << 0, 1 << 1, 1 << 2, 1 << 3, 1 << 4, 1 << 6, 1 << 7, 1 << 11
HWTSTAMP_TX_ON, HWTSTAMP_FILTER_ALL = 1, 1


class HwTstampConfig(ctypes.Structure):
    _fields_ = [("flags", ctypes.c_int), ("tx_type", ctypes.c_int), ("rx_filter", ctypes.c_int)]


def enable_hw_timestamps(iface: str) -> None:
    """SIOCSHWTSTAMP: ask the driver to stamp all received frames and the transmitted ones. Needs CAP_NET_ADMIN (run with sudo, owner action)."""
    cfg = HwTstampConfig(0, HWTSTAMP_TX_ON, HWTSTAMP_FILTER_ALL)
    ifr = struct.pack("16sP", iface.encode(), ctypes.addressof(cfg))
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fcntl.ioctl(s.fileno(), SIOCSHWTSTAMP, ifr)
    s.close()


def stamps(ancdata) -> list[float | None]:
    """The three timespecs of an SCM_TIMESTAMPING control message: [software, deprecated, raw hardware], seconds as floats (None when zero)."""
    for level, typ, data in ancdata:
        if level == socket.SOL_SOCKET and typ == SCM_TIMESTAMPING:
            v = struct.unpack("6q", data[:48])
            return [(v[2 * i] + v[2 * i + 1] * 1e-9) if (v[2 * i] or v[2 * i + 1]) else None for i in range(3)]
    return [None, None, None]


def measure(board_ip: str, bind_ip: str, feed_port: int, order_port: int, price: int, inst: int, software: bool, timeout_s: float = 1.0) -> dict:
    from designs.b58a_trigger.model import benchfeed as bf
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tx.bind((bind_ip, 0)); rx.bind((bind_ip, order_port)); rx.settimeout(timeout_s)
    flags = (F_TX_SW | F_RX_SW | F_SOFTWARE) if software else (F_TX_HW | F_RX_HW | F_RAW_HW)
    flags |= F_OPT_ID | F_OPT_TSONLY
    for s in (tx, rx):
        s.setsockopt(socket.SOL_SOCKET, SO_TIMESTAMPING, flags)
    payload = bf.packet(1, [bf.Msg(bf.ADD, bf.ASK, inst, price, 1, 1)])
    t_user = time.time_ns()
    tx.sendto(payload, (board_ip, feed_port))
    tx_stamp = None
    t0 = time.time()
    while tx_stamp is None and time.time() - t0 < timeout_s:               # the TX stamp comes back on the error queue
        try:
            _, anc, _, _ = tx.recvmsg(256, 512, socket.MSG_ERRQUEUE)
        except (BlockingIOError, OSError):
            time.sleep(0.001); continue
        st = stamps(anc)
        tx_stamp = st[0] if software else st[2]
    try:
        data, anc, _, _ = rx.recvmsg(2048, 512)
    except socket.timeout:
        return {"ok": False, "why": "no order came back within the timeout", "tx_stamp": tx_stamp}
    st = stamps(anc)
    rx_stamp = st[0] if software else st[2]
    out = {"ok": tx_stamp is not None and rx_stamp is not None, "software": software, "tx_stamp_s": tx_stamp, "rx_stamp_s": rx_stamp, "order_bytes": len(data), "t_user_ns": t_user}
    if out["ok"]:
        out["wire_to_wire_ns"] = (rx_stamp - tx_stamp) * 1e9
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--iface", required=True); ap.add_argument("--board-ip", required=True); ap.add_argument("--bind-ip", required=True)
    ap.add_argument("--feed-port", type=int, default=5800); ap.add_argument("--order-port", type=int, default=5801)
    ap.add_argument("--price", type=int, default=9950); ap.add_argument("--inst", type=int, default=7)
    ap.add_argument("--n", type=int, default=100); ap.add_argument("--software", action="store_true"); ap.add_argument("--enable-hw", action="store_true")
    a = ap.parse_args()
    if a.enable_hw:
        enable_hw_timestamps(a.iface)
    res = [measure(a.board_ip, a.bind_ip, a.feed_port, a.order_port, a.price, a.inst, a.software) for _ in range(a.n)]
    good = sorted(r["wire_to_wire_ns"] for r in res if r.get("ok"))
    print(json.dumps({"n": a.n, "ok": len(good), "min_ns": good[0] if good else None, "median_ns": good[len(good) // 2] if good else None,
                      "max_ns": good[-1] if good else None, "software": a.software}, indent=1))


if __name__ == "__main__":
    main()
