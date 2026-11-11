"""Brief 30: the host-side instrument drivers, on synthetic data and fakes (no board, no instrument). Each driver has a
known answer and a seeded fault that must fail. Drivers for instruments that were not connected (M2K, Pluto, Red Pitaya)
are tested only to this level, and the report says so."""
from __future__ import annotations

import socket
import threading

import numpy as np
import pytest

from hil.instruments import audio, logic_decode as ld, models, pluto_sa, redpitaya
from hil.instruments import shell_instruments as si
from hil.instruments.board_lock import BoardBusy, BoardLock, prefix_of


# ------------------------------------------------------------------------------------------------ board lock
def test_board_lock_take_release_and_refusal(tmp_path):
    p = tmp_path / "board.lock"
    a = BoardLock("FPGA b30: audio run, 12:00", p)
    a.take()
    with pytest.raises(BoardBusy):
        BoardLock("Other: job", p).take()
    assert BoardLock("Other: job", p).release() is False          # not theirs: left alone
    assert p.exists()
    assert a.release() is True and not p.exists()
    assert prefix_of("FPGA b30: x") == "FPGA b30:"
    with pytest.raises(ValueError):
        prefix_of("no colon here")


# ------------------------------------------------------------------------------------------------ models
def test_frame_crc_known_values():
    import zlib
    assert models.frame_crc32([1, 2, 3], 8) == zlib.crc32(bytes([1, 2, 3]))
    assert models.frame_crc32([0x030201], 24) == zlib.crc32(bytes([1, 2, 3]))      # little-endian words


def test_dnl_of_flat_histogram_is_zero():
    d, i = models.dnl_inl([100] * 16)
    assert max(abs(x) for x in d) < 1e-12 and max(abs(x) for x in i) < 1e-12
    h = [100] * 16
    h[7] = 150
    d, _ = models.dnl_inl(h)
    assert max(d) > 0.4                                              # the wide bin shows


# ------------------------------------------------------------------------------------------------ audio
def tone(f, a=0.05, fs=48000, secs=4.0, noise=1e-5, h2=0.0):
    t = np.arange(int(fs * secs)) / fs
    return a * np.sin(2 * np.pi * f * t) + h2 * a * np.sin(2 * np.pi * 2 * f * t) + noise * np.random.default_rng(1).standard_normal(len(t))


def test_audio_known_tone_passes_and_silence_fails():
    m = audio.measure_tone(tone(1000.0, h2=0.01), 48000, 1000.0)
    assert abs(m["freq_hz"] - 1000.0) < 0.2 and abs(m["level_dbfs_rms"] - (-29.03)) < 0.2 and abs(m["thd_percent"] - 1.0) < 0.1
    assert audio.tone_check(m, 1000.0)["pass"]
    m0 = audio.measure_tone(tone(1000.0, a=1e-5, noise=3e-5), 48000, 1000.0)      # seeded fault: no tone at the pins
    r = audio.tone_check(m0, 1000.0)
    assert not r["pass"] and not r["checks"]["level"] or not r["checks"]["sinad"]


def test_audio_wrong_frequency_and_distortion_fail():
    assert not audio.tone_check(audio.measure_tone(tone(1010.0), 48000, 1000.0), 1000.0)["checks"]["freq"]
    assert not audio.tone_check(audio.measure_tone(tone(1000.0, h2=0.2), 48000, 1000.0), 1000.0)["checks"]["thd"]


# ------------------------------------------------------------------------------------------------ decode
def uart_wave(data, spb, idle=3):
    x = [1] * idle * spb
    for b in data:
        for lv in [0] + [(b >> i) & 1 for i in range(8)] + [1]:
            x += [lv] * spb
    return x + [1] * idle * spb


def test_uart_decode_and_seeded_baud_fault():
    data = [0x00, 0xA5, 0x5A, 0xFF, 0x41]
    x = uart_wave(data, 10)
    assert ld.uart(x, 1e6, 100e3) == data
    assert ld.uart(x, 1e6, 80e3) != data                                  # decoding at the wrong baud rate must not pass


def test_spi_decode_modes():
    for mode in range(4):
        cpol, cpha = mode >> 1, mode & 1
        lead = 1 - cpol
        words = [(0x9F, 0x12), (0x3C, 0xE1)]
        clk, mosi, miso, cs = [cpol], [0], [0], [1]
        for wm, ws in words:
            prev_m = prev_s = 0
            for k in range(8):
                bm, bs = (wm >> (7 - k)) & 1, (ws >> (7 - k)) & 1
                # CPHA 0: data is valid before the leading edge; CPHA 1: it changes at the leading edge
                slots = [(cpol, bm if cpha == 0 else prev_m, bs if cpha == 0 else prev_s), (lead, bm, bs), (lead, bm, bs), (cpol, bm, bs)]
                for c, m_, s_ in slots:
                    clk.append(c); mosi.append(m_); miso.append(s_); cs.append(0)
                prev_m, prev_s = bm, bs
            clk.append(cpol); mosi.append(0); miso.append(0); cs.append(1)
        got = ld.spi(clk, mosi, miso, cs, mode)
        assert got == words, f"mode {mode}: {got}"
    for i in (2, 3, 4):                                                                  # a seeded fault: the first bit of the first word is wrong
        mosi[i] ^= 1
    assert ld.spi(clk, mosi, miso, cs, mode) != words


def test_i2c_decode_write_with_nack():
    scl, sda = [1, 1], [1, 1]

    def bit(b):
        scl.extend([0, 0, 1, 1]); sda.extend([b, b, b, b])
    sda.append(0); scl.append(1)                                          # START
    for byte in (0x50 << 1, 0xA5):
        for k in range(8):
            bit((byte >> (7 - k)) & 1)
        bit(0)                                                            # ACK
    bit(1)                                                                # a ninth bit of 1 on the last: NACK of a further byte
    scl.extend([0, 0, 1]); sda.extend([0, 0, 0]); scl.append(1); sda.append(1)   # STOP
    tx = ld.i2c(scl, sda)
    assert tx and tx[0]["addr"] == 0x50 and tx[0]["read"] is False and tx[0]["data"][0] == 0xA5 and tx[0]["acks"][:2] == [True, True]


def test_edge_delay():
    x = [0] * 5 + [1] * 5 + [0] * 5 + [1] * 5
    y = [0] * 8 + [1] * 5 + [0] * 5 + [1] * 4
    assert ld.edge_delay_ns(x, y, 1e6) == [3000.0, 3000.0]


# ------------------------------------------------------------------------------------------------ Pluto analyser maths
def test_stitch_places_tones_and_refuses_tx_without_attenuation():
    fs = 2.5e6
    n = 1 << 14
    t = np.arange(n) / fs
    f_tones = [100.5e6, 101.9e6, 103.3e6]
    centres = pluto_sa.sweep_centres(100e6, 104e6, fs)
    blocks = []
    for fc in centres:
        iq = 1e-4 * (np.random.default_rng(2).standard_normal(n) + 1j * np.random.default_rng(3).standard_normal(n))
        for ft in f_tones:
            if abs(ft - fc) < fs * 0.4:
                iq = iq + (0.1 if ft == f_tones[0] else 0.001) * np.exp(2j * np.pi * (ft - fc) * t)
        iq = iq + 0.05                                               # a DC offset: must not appear as a spur at the centre
        blocks.append(iq)
    f, p = pluto_sa.stitch(blocks, centres, fs)
    top = sorted(f for f, _ in pluto_sa.peaks(f, p, 3))
    assert all(abs(a - b) < 2e3 for a, b in zip(top, f_tones)), top
    assert pluto_sa.spur_free_dynamic_range(f, p, f_tones[0]) > 35
    with pytest.raises(PermissionError):
        pluto_sa.tracking_sweep("ip:pluto.local", 400e6, 500e6, atten_db=20.0)
    with pytest.raises(ValueError):
        pluto_sa.tracking_sweep("ip:pluto.local", 100e6, 200e6, atten_db=40.0)       # below the stock range


# ------------------------------------------------------------------------------------------------ Red Pitaya SCPI
def fake_server():
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
    log = []

    def run():
        c, _ = srv.accept()
        buf = b""
        while True:
            d = c.recv(4096)
            if not d:
                break
            buf += d
            while b"\r\n" in buf:
                line, buf = buf.split(b"\r\n", 1)
                s = line.decode(); log.append(s)
                if s.endswith("?"):
                    c.sendall(({"*IDN?": "FAKE,STEMlab", "ACQ:TRIG:STAT?": "TD"}.get(s) or "{0.1,0.2,0.3}").encode() + b"\r\n")
        c.close()
    threading.Thread(target=run, daemon=True).start()
    return srv, log


def test_redpitaya_scpi_and_forbidden_commands():
    srv, log = fake_server()
    rp = redpitaya.RedPitaya("127.0.0.1", srv.getsockname()[1])
    assert rp.idn() == "FAKE,STEMlab"
    rp.generate(1, "sine", 1000.0, 0.5)
    assert rp.acquire(1) == [0.1, 0.2, 0.3]
    for bad in ("SYSTEM:REBOOT", "FPGA:LOAD x", "OVERLAY:LOAD", "rm -rf /"):
        with pytest.raises(redpitaya.ScpiError):
            rp.send(bad)
    with pytest.raises(redpitaya.ScpiError):
        rp.generate(1, "sine", 1000.0, 1.5)
    rp.close()
    assert "SOUR1:FUNC SINE" in log


# ------------------------------------------------------------------------------------------------ shell instrument hosts on a fake shell
class FakeShell:
    def __init__(self):
        self.mem, self.W = {}, si.WINDOW

    def write(self, a, v): self.mem[a] = v
    def read(self, a): return self.mem.get(a, 0)


def test_xadc_conversions_and_hosts():
    f = FakeShell()
    for i, c in enumerate((0x9A5, 0x556, 0xB20, 0x557)):
        f.mem[si.WINDOW + 0x40 + i] = c
    r = si.XadcHost(f).read()
    assert abs(r["tj_c"] - (0x9A5 * 503.975 / 4096 - 273.15)) < 1e-9 and abs(r["vccint_v"] - 1.0) < 0.001
    f.mem.update({si.WINDOW + 0x10: 500, si.WINDOW + 0x11: 25_000_000, si.WINDOW + 0x12: 7, si.WINDOW + 0x13: 50_000_000})
    d = si.FreqDutyHost(f).read()
    assert d["freq_hz"] == 1000.0 and d["duty"] == 0.5


def test_lfsr_frame_matches_rtl_recurrence():
    fr = si.lfsr_frame(4)
    assert fr[0] == 0xACE1 and fr[1] == ((0xACE1 << 1) & 0xFFFFFF) | (((0xACE1 >> 23) ^ (0xACE1 >> 22) ^ (0xACE1 >> 21) ^ (0xACE1 >> 16)) & 1)
