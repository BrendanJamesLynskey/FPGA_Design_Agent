"""Brief 50A: the capture format, VCD, answer (quotes only the capture), queries, the viewer page, plan.tcl and conditions."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from debug_core import capture as C
from debug_core.answer import answer, diverge, facts, query, unquoted_numbers
from debug_core.instruments import MockIla, alarm_bits, conditions, plan_tcl
from debug_core.plan import make_plan, validate
from debug_core.view import page

T1 = Path("designs/t1_dimmer_counter")
INTENT = {"probes": ["count"], "trigger": {"combine": "AND", "conditions": [
    {"signal": "win_wr", "op": "==", "value": 1}, {"signal": "addr", "op": "==", "value": "0x80"}]}, "pre": 16, "post": 32,
    "question": "does count take the written value on the next clock?"}
N, T0 = 1024, 16


def samples(written: int = 0x1234) -> dict[str, list[int]]:
    return {"win_wr": [1 if k == T0 else 0 for k in range(N)], "addr": [0x80 if 5 <= k < 200 else 0 for k in range(N)],
            "count": [3 if k <= T0 else written for k in range(N)]}


@pytest.fixture(scope="module")
def plan():
    return make_plan(T1, INTENT, "capture count when the shell writes COUNT")


@pytest.fixture()
def cap(plan):
    m = MockIla(samples(), T0)
    m.configure(plan)
    m.arm()
    c = m.capture()
    c["readback"] = {"COUNT": 0x1234}
    return c


def test_capture_is_the_common_format(cap) -> None:
    assert not validate(cap, "capture")
    assert cap["timebase"] == {"unit": "cycle", "clock": "CLK100MHZ", "mhz": 100.0, "samples": N, "trigger_sample": T0,
                               "alignment_uncertainty_cycles": 0}
    assert [c["name"] for c in cap["channels"]] == ["win_wr", "addr", "count"]
    assert C.cycles(cap)[0] == -16 and C.cycles(cap)[-1] == 1007


def test_answer_names_what_was_seen_with_values_from_the_capture(cap) -> None:
    a = answer(cap)
    t = a["text"]
    assert a["check"] == []
    assert "At cycle 0: win_wr = 1, addr = 0x80, count = 0x0003" in t
    assert "count was 0x0003 from cycle -16 to 0, then 0x1234 from cycle 1 to 32." in t     # the asked window, -16..32
    assert "The capture holds cycles -16 to 1007; this answer covers cycles -16 to 32, as asked." in t
    assert "COUNT = 0x00001234" in t
    assert t.index("count was") < t.index("win_wr was")          # the channel the question names comes first
    assert a["facts"]["trigger"]["holds"] is True


def test_the_number_check_attributes_each_number_to_its_signal(cap) -> None:
    from debug_core.capture import trim
    asked = trim(cap, -16, 32)
    assert unquoted_numbers("count became 0x1234 at cycle 1", cap, asked) == []
    assert unquoted_numbers("count became 0x4321 at cycle 1", cap, asked) == ["0x4321"]
    assert unquoted_numbers("addr was 0x1234", cap, asked) == ["0x1234"]          # a real value, on the wrong signal
    assert unquoted_numbers("win_wr held high for 3 cycles", cap, asked) == ["3"]  # no blanket small numbers
    assert unquoted_numbers("it overflowed after 77 cycles", cap, asked) == ["77"]
    assert unquoted_numbers("addr was 0x80 at cycle 90", cap, asked) == ["90"]   # outside the answered window


def test_a_trigger_that_does_not_hold_at_cycle_0_is_flagged(plan) -> None:
    s = samples()
    s["win_wr"][T0] = 0
    m = MockIla(s, T0)
    m.configure(plan)
    a = answer(m.capture())
    assert "WARNING: the trigger condition does not hold at cycle 0" in a["text"]


def test_queries(cap) -> None:
    assert query(cap, {"op": "first", "channel": "count", "cmp": "==", "value": "0x1234"}) == {"ok": True, "cycle": 1, "found": True}
    assert query(cap, {"op": "value_at", "channel": "count", "cycle": 0})["text"] == "0x0003"
    assert query(cap, {"op": "count", "channel": "win_wr", "cmp": "==", "value": 1})["count"] == 1
    assert query(cap, {"op": "runs", "channel": "win_wr"})["runs"] == [{"start": 0, "length": 1}]
    assert query(cap, {"op": "changes", "channel": "addr"})["n"] == 2
    assert not query(cap, {"op": "value_at", "channel": "count", "cycle": 5000})["ok"]
    assert not query(cap, {"op": "nope", "channel": "count"})["ok"]
    assert "facts" in query(cap, {"op": "summary"})


def test_diverge_finds_the_first_differing_cycle(plan, cap) -> None:
    m = MockIla(samples(written=0x1235), T0)
    m.configure(plan)
    d = diverge(cap, m.capture())
    assert d["diverged"] and d["cycle"] == 1 and d["differences"] == [{"channel": "count", "a": "0x1234", "b": "0x1235"}]
    assert not diverge(cap, cap)["diverged"]


def test_vcd(cap) -> None:
    v = C.to_vcd(cap)
    assert "$timescale 10000 ps $end" in v and "$var wire 16 # count $end" in v and "$var wire 1 $ TRIGGER $end" in v
    assert re.search(r"#16\n1!\n1\$", v) and "b1001000110100 #" in v


def test_save_load_round_trip(tmp_path, cap) -> None:
    f = C.save(cap, tmp_path / "c.json")
    assert C.load(f)["channels"] == cap["channels"]
    bad = dict(cap, schema="other")
    (tmp_path / "bad.json").write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        C.load(tmp_path / "bad.json")


def test_viewer_page_embeds_the_capture_and_is_self_contained(cap) -> None:
    html = page(cap, "answer </script> text")
    assert '"name":"count"' in html and "<\\/script>" in html and "prefers-color-scheme: dark" in html
    assert not re.search(r"<script[^>]+src=|<link[^>]+href=|https?://", html)     # no network
    assert "glow" not in html and "box-shadow" not in html


def test_plan_tcl_for_ila_capture(plan) -> None:
    sl = {"win_wr": (0, 0, 1), "addr": (1, 0, 8), "count": (1, 8, 16)}
    t = plan_tcl(plan, sl, 1024)
    assert "set fda_depth 1024" in t
    assert "lappend fda_captures [list cap AND 16 [list [list 0 0 0 1 1] [list 1 0 0 8 10000000]]]" in t
    # a larger build reused under other labels
    t2 = plan_tcl(plan, {"ww": (2, 3, 1), "frame_1": (0, 0, 8), "count": (0, 8, 16)}, 4096,
                  labels={"win_wr": "ww", "addr": "frame_1"})
    assert "[list 2 0 3 1 1]" in t2 and "set fda_depth 4096" in t2
    with pytest.raises(ValueError):
        plan_tcl(plan, {"win_wr": (0, 0, 1)}, 1024)


COND = """FDA-COND NOW TEMPERATURE=41.2 VCCINT=0.951 VCCAUX=1.79 VCCBRAM=0.952
FDA-COND MAX TEMPERATURE=42.01 VCCINT=0.9558 VCCAUX=1.7930 VCCBRAM=0.9558
FDA-COND MIN TEMPERATURE=30.10 VCCINT=0.9470 VCCAUX=1.7871 VCCBRAM=0.9470
FDA-COND FLAGS 0000
"""


def test_conditions_and_alarms(tmp_path) -> None:
    (tmp_path / "cap.cond_armed.txt").write_text(COND)
    (tmp_path / "cap.cond_done.txt").write_text(COND.replace("FLAGS 0000", "FLAGS 0002"))
    c = conditions(tmp_path, "cap")
    assert c["armed"]["now"]["VCCINT"] == 0.951 and c["alarms"] == ["ALM1 VCCINT"] and c["verdict"] == "outside ROC"
    (tmp_path / "cap.cond_done.txt").write_text(COND)
    c = conditions(tmp_path, "cap")
    assert c["verdict"] == "outside ROC" and any("min VCCINT 0.947" in x for x in c["outside"])   # latched min below 0.95
    (tmp_path / "cap.cond_armed.txt").write_text(COND.replace("0.9470", "0.9500"))
    (tmp_path / "cap.cond_done.txt").write_text(COND.replace("0.9470", "0.9500"))
    assert conditions(tmp_path, "cap")["verdict"] == "inside ROC"
    assert alarm_bits("0108") == ["OT over-temperature", "ALM3 VCCBRAM"]


def test_facts_of_a_one_bit_signal(cap) -> None:
    f = facts(cap)["channels"]["win_wr"]
    assert f["high_samples"] == 1 and f["high_runs"] == [(0, 1)] and f["n"] == N


@pytest.mark.parametrize("bad,match", [({"count": 0x1FFFF}, "16-bit"), ({"count": -5}, "16-bit"),
                                       ({"count": 1.5}, "16-bit")])
def test_make_capture_refuses_samples_that_do_not_fit(plan, bad, match) -> None:
    s = samples()
    for k, v in bad.items():
        s[k] = list(s[k])
        s[k][3] = v
    with pytest.raises(ValueError, match=match):
        C.make_capture(plan=plan, samples=s, trigger_sample=T0, instrument={"kind": "x", "driver": "x"})


def test_make_capture_refuses_a_trigger_past_the_end(plan) -> None:
    with pytest.raises(ValueError, match="outside"):
        C.make_capture(plan=plan, samples=samples(), trigger_sample=N, instrument={"kind": "x", "driver": "x"})


def test_load_refuses_out_of_range_samples(tmp_path, cap) -> None:
    bad = json.loads(json.dumps(cap))
    bad["channels"][2]["samples"][0] = 1 << 16
    (tmp_path / "b.json").write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="16-bit"):
        C.load(tmp_path / "b.json")


def test_number_check_on_the_board_pwm_capture() -> None:
    """Review of brief 50A: on the committed PWM capture (phase sweeps 0..255) invented counts and values on led fail."""
    from debug_core.capture import trim
    d = Path(__file__).parent / "fixtures" / "golden" / "t1_pwm_period"
    c = C.load(d / "capture.json")
    asked = trim(c, 0, 1023)
    assert unquoted_numbers("led was lit for 200 cycles", c, asked) == ["200"]
    assert unquoted_numbers("led was 0x00C8 at cycle 5", c, asked) == ["0x00C8", "5"]
    assert unquoted_numbers("led was 0x8421 from cycle 1 to 256", c, asked) == []
    assert answer(c)["check"] == []
