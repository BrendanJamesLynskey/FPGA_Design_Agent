"""Stage 3's host code against models, no hardware (brief 96): the I2C bit-bang against a slave model, the DDM decode."""

from __future__ import annotations

import math

import pytest

from designs.b96_kr260_10g.host import sfp_i2c as s


def module():
    a0 = bytearray(range(256)); a0[20:36] = b"VENDOR NAME     "; a0[40:56] = b"PART-NUMBER-LR  "
    a2 = bytearray(256)
    a2[96:106] = (0x1900).to_bytes(2, "big") + (33000).to_bytes(2, "big") + (3000).to_bytes(2, "big") + (5000).to_bytes(2, "big") + (3162).to_bytes(2, "big")
    sl = s.EepromSlave(bytes(a0), bytes(a2))
    return sl, s.I2CMaster(sl.drive, sl.line_sda)


def test_reads_identity_and_diagnostics() -> None:
    sl, m = module()
    assert m.read(0x50, 20, 16) == b"VENDOR NAME     "
    assert m.read(0x50, 0, 4) == bytes([0, 1, 2, 3])
    raw = m.read(0x51, 96, 10)
    d = s.ddm(raw)
    assert d["temp_c"] == pytest.approx(25.0) and d["vcc_v"] == pytest.approx(3.3) and d["tx_bias_ma"] == pytest.approx(6.0)
    assert d["tx_power_dbm"] == pytest.approx(10 * math.log10(0.5), abs=1e-6) and d["rx_power_dbm"] == pytest.approx(10 * math.log10(0.3162), abs=1e-4)


def test_no_module_acknowledges_nothing() -> None:
    sl, m = module()
    with pytest.raises(s.I2CError):
        m.read(0x52, 0, 1)


def test_bus_left_idle() -> None:
    sl, m = module()
    m.read(0x50, 0, 2)
    assert sl.scl == 1 and sl.line_sda() == 1


def test_nic_timestamp_plumbing_on_loopback() -> None:
    """The socket and control-message plumbing of host/nic_timestamp.py with SOFTWARE stamps on lo and a stand-in 'board' thread that answers a
    feed packet with an order packet (hardware stamps need the card and root and are stage 3)."""
    import socket
    import threading

    from designs.b96_kr260_10g.host import nic_timestamp as n

    srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    srv.bind(("127.0.0.1", 15800)); srv.settimeout(2.0)
    done = threading.Event()

    def board():
        try:
            _, addr = srv.recvfrom(2048)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sendto(bytes(32), ("127.0.0.1", 15801))
        finally:
            done.set()

    th = threading.Thread(target=board, daemon=True); th.start()
    r = n.measure("127.0.0.1", "127.0.0.1", 15800, 15801, 9950, 7, software=True)
    th.join(3.0); srv.close()
    assert r["ok"] and 0 < r["wire_to_wire_ns"] < 5e8, r
