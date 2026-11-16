"""Tests of the reference model, the host client and the fuzzer (no hardware, no network)."""

import binascii
import random
import zlib
from pathlib import Path

import pytest

from showcase.udp_endpoint.host import fuzz
from showcase.udp_endpoint.host.client import Client, CommandError, SimTransport
from showcase.udp_endpoint.model import udp_ref as u

HERE = Path(__file__).resolve().parents[1]


def test_crc32_matches_zlib_and_the_residue_constant():
    rng = random.Random(7)
    for n in (0, 1, 5, 64):
        d = bytes(rng.randrange(256) for _ in range(n))
        assert u.crc32(d) == zlib.crc32(d) == binascii.crc32(d)
        assert u.crc32(d + u.crc32(d).to_bytes(4, "little")) == 0x2144DF1C      # CRC of message plus its own CRC, a constant
    assert u.crc32(b"123456789") == 0xCBF43926


def test_read_write_status_round_trip():
    c = Client(SimTransport())
    assert c.read(u.REG_ID) == u.ID_VALUE
    c.write(u.REG_S1, 0xDEADBEEF)
    assert c.read(u.REG_S1) == 0xDEADBEEF
    st = c.status()
    assert st["ok"] == 3 and st["tlm_on"] is False
    assert c.read(u.REG_CMDS) == 4


def test_errors_and_consumed_sequence_numbers():
    c = Client(SimTransport())
    with pytest.raises(CommandError) as e:
        c.read(8)
    assert e.value.status == u.BAD_ADDR
    with pytest.raises(CommandError) as e:
        c.write(u.REG_ID, 1)
    assert e.value.status == u.READ_ONLY
    assert c.read(u.REG_ID) == u.ID_VALUE            # the failed commands consumed their numbers and the next one is accepted
    assert c.status()["protocol"] == 2


def test_replay_and_old_numbers_change_nothing():
    t = SimTransport()
    c = Client(t, first_seq=10)
    c.write(u.REG_S0, 5)
    r = c.send(u.WRITE, (u.REG_S0).to_bytes(2, "big") + (99).to_bytes(4, "big"), seq=10)      # replay
    assert r["status"] == u.BAD_SEQ
    r = c.send(u.WRITE, (u.REG_S0).to_bytes(2, "big") + (99).to_bytes(4, "big"), seq=3)       # older
    assert r["status"] == u.BAD_SEQ
    r = c.send(u.READ, (u.REG_S0).to_bytes(2, "big"), seq=1000)                                   # a gap is fine
    assert int.from_bytes(r["payload"], "big") == 5 and r["status"] == u.OK
    c.seq = 1001
    st = c.status()
    assert (st["replay"], st["out_of_order"]) == (1, 1)
    r = c.send(u.READ, (u.REG_S0).to_bytes(2, "big"), seq=1001 + 0x8000)                        # exactly half the span ahead is "older"
    assert r["status"] == u.BAD_SEQ


def test_sequence_wraps():
    c = Client(SimTransport(), first_seq=0xFFFE)
    for _ in range(4):
        c.read(u.REG_ID)
    assert c.seq == 2 and c.status()["ok"] == 4


def test_framing_drops_do_not_reply_or_change_state():
    t = SimTransport()
    c = Client(t)
    c.write(u.REG_S0, 1)
    good = u.build_command(u.WRITE, 1, (u.REG_S0).to_bytes(2, "big") + (2).to_bytes(4, "big"))
    for bad in (good[:-1], good + b"\0", b"", good[:3], bytes([1, 200, 0, 1]) + b"x" * 30, good[:-1] + bytes([good[-1] ^ 1])):
        assert t.exchange(bad) == []
    st = c.status()
    assert (st["truncated"], st["oversize"], st["bad_crc"]) == (3, 2, 1)       # b"" and good[:3] are truncated, good + b"\0" oversize
    assert c.read(u.REG_S0) == 1


def test_byte_serial_equals_whole_datagram():
    a, b = u.Endpoint(), u.Endpoint()
    pkt = u.build_command(u.READ, 4, (0).to_bytes(2, "big"))
    out = None
    for i, x in enumerate(pkt):
        out = a.push(x, i == len(pkt) - 1)
    assert out == b.datagram(pkt)


def test_telemetry_pacer_rate_limits_and_counts_overruns():
    e = u.Endpoint()
    c = Client(SimTransport(e))
    c.start_telemetry(10)
    e.tick(9)
    assert e.tlm_pending is None
    e.tick(1)
    f = e.take_telemetry()
    assert u.parse_response(f)["type"] == u.TLM_TYPE and u.parse_response(f)["seq"] == 0
    e.tick(10)                                       # due, not taken
    e.tick(10)                                       # due again while held: overrun, not queued
    assert e.tlm_overruns == 1 and e.tlm_frames == 2
    assert u.parse_response(e.take_telemetry())["seq"] == 1 and e.take_telemetry() is None
    c.start_telemetry(2)                             # below the minimum: raised to 4
    assert e.period == u.PERIOD_MIN
    c.stop_telemetry()
    e.tick(50)
    assert e.tlm_pending is None and e.tlm_frames == 2


def test_fuzzer_passes_the_model_and_catches_three_seeded_faults():
    assert fuzz.run(SimTransport(), 3, 600)["ok"]

    class AcceptsBadCrc(u.Endpoint):
        def _finish(self, pkt, need, over):
            if need and len(pkt) == need and not over:
                pkt = pkt[:-4] + u.crc32(pkt[:-4]).to_bytes(4, "little")
            return super()._finish(pkt, need, over)

    class HangsOnTruncated(u.Endpoint):
        def datagram(self, payload):                 # the buffer is not cleared when a packet ends early: the next packet is glued on
            r = super().datagram(payload)
            return r

        def _finish(self, pkt, need, over):
            if need is not None and len(pkt) < need:
                self._buf = bytearray(pkt)
                self._need = need
                return None
            return super()._finish(pkt, need, over)

    class LosesSequence(u.Endpoint):
        def _execute(self, typ, seq, payload):
            self.last_seq = (seq - 1) & 0xFFFF       # the order is not remembered: every replay looks new
            return super()._execute(typ, seq, payload)

    for cls in (AcceptsBadCrc, HangsOnTruncated, LosesSequence):
        log = fuzz.run(SimTransport(cls()), 3, 600)
        assert not log["ok"], cls.__name__


def test_protocol_md_is_current_and_numbers():
    assert (HERE / "protocol.md").read_text() == u.protocol_text()
    r = u.max_command_rate()
    assert r["READ"]["cycles"] == 10 + 3 + 13 and r["WRITE"]["cycles"] == 14 + 3 + 9


def test_spec_yaml_numbers_agree_with_the_model():
    import yaml
    s = yaml.safe_load((HERE / "spec.yaml").read_text())
    assert s["parameters"]["MAX_PAYLOAD"] == u.MAX_PAYLOAD and s["parameters"]["PERIOD_MIN"] == u.PERIOD_MIN
    assert s["parameters"]["PERIOD_DEFAULT"] == u.PERIOD_DEFAULT and s["parameters"]["N_REGS"] == u.N_REGS
    r = u.max_command_rate(s["clock_hz"])
    assert s["numbers"]["read_cycles"] == r["READ"]["cycles"] and s["numbers"]["write_cycles"] == r["WRITE"]["cycles"]
