"""Brief 88: the timing playbook offers a carry-split and a verdict-register strategy, and sends a DSP mapping only where
the RTL has a multiply."""
from agent.graph import closure_playbook as pb


def dg(dest="j_reg[10]/R", mult=None, carry=6, levels=12):
    d = {"timing": {"period_ns": 8.0}, "setup_path": {"destination": dest, "data_path_ns": 7.9},
         "setup_features": {"lut_arith": True, "carry_chain": carry, "logic_levels": levels}}
    if mult is not None:
        d["rtl_has_multiply"] = mult
    return d


def ids(d):
    return [s.id for s, _ in pb.applicable("G2", d, {"G3": {"value": {}, "target": {}}})]


def test_no_multiply_no_dsp_map():
    got = ids(dg(mult=False))
    assert "t_dsp_map" not in got and got[0] in ("t_carry_split", "t_verdict_reg")


def test_multiply_unknown_keeps_dsp_map_first():
    assert ids(dg())[0] == "t_dsp_map"          # drivers that do not scan the RTL keep the earlier behaviour
    assert ids(dg(mult=True))[0] == "t_dsp_map"


def test_control_pin_offers_verdict_register():
    assert "t_verdict_reg" in ids(dg(dest="busy_reg/CE", mult=False))
    assert "t_verdict_reg" not in ids(dg(dest="r_csum_reg[15]/D", mult=False))


def test_new_strategies_are_rtl_stage_and_ready():
    for i in ("t_carry_split", "t_verdict_reg"):
        s = pb.BY_ID[i]
        assert s.stage == "rtl" and s.phase == "ready" and s.goal == "G2"
