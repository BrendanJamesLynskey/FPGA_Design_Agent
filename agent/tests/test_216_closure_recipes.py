"""Brief 216: typed closure recipes, the knowledge-guided order and the budgeted search. No Vivado: recorded outcomes from
results/178_tournament and hand-built reports are the runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.graph import closure_recipes as R
from agent.graph import closure_search as S
from agent.graph import stages

ROOT = Path(__file__).resolve().parents[2]
CTX7 = R.Context(family="7series")
CTXU = R.Context(family="ultrascale+")


def ok(wns, whs=0.05, lut=100, ff=100, clock=5.0, **kw):
    return {"status": "ok", "wns_ns": wns, "whs_ns": whs, "lut": lut, "ff": ff, "clock_ns": clock, **kw}


# ---- recipe validation ----------------------------------------------------------------------------------------------------------------
def test_every_directive_of_the_178_menu_and_probe_is_known():
    from flow import tournament as T
    for m in T.IMPL_MENU:
        for step in ("opt", "place", "phys", "route", "post"):
            if m.get(step):
                assert m[step] in R.DIRECTIVES[step], (m["id"], step)
    for name, st in R._strategies().items():
        for step, d in st.items():
            assert d in R.DIRECTIVES[step], (name, step, d)


def test_named_sets_equal_the_tournament_menu():
    from flow import tournament as T
    for m in T.IMPL_MENU:
        if m["id"] == "default":
            continue
        got = R.IMPL_SETS[m["id"]]
        assert {k: v for k, v in got.items() if v != "Default"} == {k: m[k] for k in ("opt", "place", "phys", "route", "post") if m.get(k) and m[k] != "Default"}


@pytest.mark.parametrize("rid,args,frag", [
    ("nope", {}, "unknown recipe"),
    ("impl_directive", {"step": "place", "directive": "Explorez"}, "not one of"),
    ("impl_directive", {"step": "place", "directive": "Explore", "extra": 1}, "unknown parameter"),
    ("impl_directive", {"step": "route", "directive": "ExtraTimingOpt"}, "not a route directive"),
    ("impl_directive", {"step": "place", "directive": "SSI_BalanceSLLs"}, "stacked-silicon"),
    ("phys_opt_options", {"step": "route", "flags": ["rewire"]}, "not one of"),
    ("phys_opt_options", {"step": "post", "flags": ["rewire", "hold_fix"]}, "hold_fix is offered alone"),
    ("phys_opt_options", {"step": "post", "flags": ["bogus"]}, "not one of"),
    ("phys_opt_options", {"step": "post", "flags": ["fanout_opt"]}, "refused by Vivado 2026.1 after routing"),
    ("fanout_replicate", {"nets": ["a; exec rm -rf /"]}, "not a plain net"),
    ("fanout_replicate", {"nets": ["n{1}"]}, "not a plain net"),
    ("fanout_replicate", {"nets": []}, "non-empty list"),
    ("max_fanout", {"nets": ["n1"], "limit": 4}, "outside"),
    ("max_fanout", {"nets": ["n1"], "limit": True}, "not an integer"),
    ("pblock", {"name": "p", "regions": ["SLICE_X0Y0:DSP48_X1Y1"], "cells": ["u/*"]}, "mixes"),
    ("pblock", {"name": "p", "regions": ["bad"], "cells": ["u/*"]}, "not a site range"),
    ("retime", {"where": "everywhere"}, "not one of"),
    ("register_duplication", {"method": "force_replication"}, "needs nets"),
    ("synth_option", {"option": "flatten_hierarchy", "value": "sideways"}, "not one of"),
    ("synth_option", {"option": "max_dsp", "value": 0}, "not one of"),
    ("amd_strategy", {"name": "Performance_Imaginary"}, "not one of"),
    ("impl_set", {"name": "yolo"}, "not one of"),
])
def test_refusals_carry_a_reason(rid, args, frag):
    with pytest.raises(R.RecipeError) as e:
        R.apply_recipe(R.ImplPlan(), rid, args, CTX7)
    assert frag in str(e.value)


def test_precondition_clashes():
    p = R.apply_recipe(R.ImplPlan(), "amd_strategy", {"name": "Performance_ExtraTimingOpt"}, CTX7)
    with pytest.raises(R.RecipeError, match="already has a directive"):
        R.apply_recipe(p, "impl_set", {"name": "explore"}, CTX7)
    p2 = R.apply_recipe(R.ImplPlan(), "pblock", {"name": "pb", "regions": ["SLICE_X0Y0:SLICE_X9Y9"], "cells": ["u/*"]}, CTX7)
    with pytest.raises(R.RecipeError, match="overlaps"):
        R.apply_recipe(p2, "pblock", {"name": "pb2", "regions": ["SLICE_X5Y5:SLICE_X20Y20"], "cells": ["v/*"]}, CTX7)
    with pytest.raises(R.RecipeError, match="already exists"):
        R.apply_recipe(p2, "pblock", {"name": "pb", "regions": ["SLICE_X50Y0:SLICE_X59Y9"], "cells": ["v/*"]}, CTX7)
    c = R.Context(capacity={"lut": 2000})
    with pytest.raises(R.RecipeError, match="headroom"):
        R.apply_recipe(R.ImplPlan(), "pblock", {"name": "pb", "regions": ["SLICE_X0Y0:SLICE_X9Y9"], "cells": ["u/*"]}, c)
    with pytest.raises(R.RecipeError, match="not in the build's reports"):
        R.apply_recipe(R.ImplPlan(), "fanout_replicate", {"nets": ["n9"]}, R.Context(nets=frozenset({"n1"})))


def test_slr_directive_allowed_only_on_slr_parts():
    p = R.apply_recipe(R.ImplPlan(), "impl_directive", {"step": "place", "directive": "SSI_SpreadLogic_high"}, R.Context(slr=True))
    assert p.d()["place"] == "SSI_SpreadLogic_high"


def test_plans_are_immutable_and_apply_is_pure():
    p0 = R.ImplPlan()
    p1 = R.apply_recipe(p0, "impl_set", {"name": "explore"}, CTX7)
    assert p0.directives == () and p0.applied == () and p1.applied == ("impl_set",)
    assert p1.key() != p0.key()


# ---- the one renderer, and the stage-6 guard -------------------------------------------------------------------------------------------------
def test_render_contains_only_template_commands_and_no_clock_change():
    p = R.apply_recipe(R.ImplPlan(), "amd_strategy", {"name": "Performance_ExtraTimingOpt"}, CTX7)
    p = R.apply_recipe(p, "phys_opt_options", {"step": "post", "flags": ["placement_opt", "rewire"]}, CTX7)
    p = R.apply_recipe(p, "max_fanout", {"nets": ["u/cnt[3]"], "limit": 100}, CTX7)
    tcl = R.render_impl_tcl(p, "/x/a.dcp", "/o")
    assert "place_design -directive ExtraTimingOpt" in tcl and "phys_opt_design -placement_opt -rewire" in tcl
    assert "set_property MAX_FANOUT 100 [get_nets -quiet {u/cnt[3]}]" in tcl
    assert "clock_uncertainty" not in tcl and "false_path" not in tcl and "create_clock" not in tcl


def test_replication_renders_at_the_phys_step_not_after_routing():
    p = R.apply_recipe(R.ImplPlan(), "fanout_replicate", {"nets": ["u/n1"]}, CTX7)
    tcl = R.render_impl_tcl(p, "/x/a.dcp", "/o")
    lines = tcl.splitlines()
    i = next(i for i, ln in enumerate(lines) if "force_replication_on_nets" in ln)
    assert lines[i].startswith("phys_opt_design -fanout_opt") and lines[i - 1].startswith("place_design") and lines[i + 1].startswith("route_design")


def test_default_plan_renders_the_default_flow():
    tcl = R.render_impl_tcl(R.ImplPlan(), "/x/a.dcp", "/o")
    body = [ln for ln in tcl.splitlines() if ln.split()[0].endswith("_design")]
    assert body == ["opt_design", "place_design", "route_design"]


@pytest.mark.parametrize("tcl", ["set_clock_uncertainty -setup 0.5 [get_clocks]", "set_false_path -from a -to b", "source /tmp/x.tcl",
                                 "exec rm -r /", "set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets x]", "my_proc 1"])
def test_guard_refuses_free_form_lines(tcl):
    with pytest.raises(R.FreeFormTclRefused):
        R.guard_rendered_tcl(tcl + "\n")


def test_stage6_takes_a_recipe_and_nothing_else():
    R.guard_stage6_args({"recipe": "retime", "params": {"where": "synth"}})
    for bad in ({"tcl": "place_design"}, {"recipe": "retime", "script": "x"}, {"recipe": "retime", "params": {}, "xdc": "a"}, {"command": "route_design"}):
        with pytest.raises(R.FreeFormTclRefused, match="recipe name"):
            R.guard_stage6_args(bad)
    with pytest.raises(R.FreeFormTclRefused, match="constraint or code"):
        R.guard_stage6_args({"recipe": "fanout_replicate", "params": {"nets": ["x"], "note": "set_clock_uncertainty 1"}})


def test_stage6_has_no_tool_that_takes_tcl():
    from agent.core import tool_list
    by = {t["name"]: t for t in tool_list()}
    st = stages.MACHINE[6]
    assert st.name == "timing-closure"
    checked = 0
    for name in st.tools:
        if name not in by:
            continue
        checked += 1
        props = set((by[name].get("inputSchema") or {}).get("properties") or {})
        assert not props & {"tcl", "script", "command", "cmd", "xdc", "xdc_text", "source"}, (name, props)
    assert checked >= 4


# ---- post validation and rollback ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("after,frag", [
    ({"status": "ok", "wns_ns": 0.2, "whs_ns": 0.05, "lut": 100, "ff": 100, "clock_ns": 4.0}, "clock period changed"),
    ({"status": "ok", "wns_ns": 0.2, "whs_ns": -0.1, "lut": 100, "ff": 100, "clock_ns": 5.0}, "newly negative"),
    ({"status": "ok", "wns_ns": 0.2, "whs_ns": 0.05, "lut": 200, "ff": 100, "clock_ns": 5.0}, "grew"),
    ({"status": "ok", "wns_ns": None, "whs_ns": 0.05, "lut": 100, "ff": 100, "clock_ns": 5.0}, "no setup slack"),
    ({"status": "error: x"}, "did not finish"),
])
def test_post_check_rejects(after, frag):
    why = R.post_check(ok(-0.1), after, R.Context())
    assert any(frag in w for w in why), why


def test_post_check_accepts_a_clean_better_result_and_tolerates_old_hold_failures():
    assert R.post_check(ok(-0.1), ok(0.1)) == []
    assert R.post_check(ok(-0.1, whs=-0.2), ok(0.1, whs=-0.1)) == []          # hold was already negative and did not get worse


def test_budget_overrun_is_rejected():
    c = R.Context(budget={"lut": 110})
    assert any("over its budget" in w for w in R.post_check(ok(-0.1, lut=100), ok(0.1, lut=115), c))


def fake_runner(table):
    """table: {recipe key: outcome}; default key 'x' is a loss."""
    def run(plan, nid):
        return dict(table.get(plan.applied[-1] + ":" + json.dumps(plan.d(), sort_keys=True), ok(-0.5)))
    return run


def test_invalid_candidate_is_rolled_back_and_the_best_stays_the_parent():
    root = ok(-0.3)

    def runner(plan, nid):
        return ok(0.2, clock=4.0)                          # "closes" by moving the clock: invalid

    r = S.search(root, S.Features(wns_ns=-0.3), CTX7, runner, budget=3)
    assert r.best.id == "n0" and r.best.plan == R.ImplPlan()
    assert r.journal.rolled_back() == r.runs == 3
    assert all(n.verdict.startswith("invalid") for n in r.nodes[1:])


def test_a_better_valid_candidate_is_kept_and_its_plan_is_the_result():
    root = ok(-0.3)
    calls = []

    def runner(plan, nid):
        calls.append(plan.applied)
        return ok(0.12, lut=105) if plan.d().get("place") == "ExtraTimingOpt" else ok(-0.4)

    r = S.search(root, S.Features(wns_ns=-0.3), CTX7, runner, budget=6, margin=0.1)
    assert r.stop == "timing met" and r.best.outcome["wns_ns"] == 0.12
    assert r.best.plan.d()["place"] == "ExtraTimingOpt"
    assert r.runs == len(calls) <= 6


def test_a_worse_candidate_is_rolled_back_not_kept():
    r = S.search(ok(-0.3), S.Features(wns_ns=-0.3), CTX7, lambda p, n: ok(-0.6), budget=2)
    assert r.best.id == "n0" and not any(n.kept for n in r.nodes[1:]) and r.journal.rolled_back() == 2


def test_hopeless_slack_stops_without_a_run():
    r = S.search(ok(-4.0), S.Features(wns_ns=-4.0), CTX7, lambda p, n: pytest.fail("ran"), budget=6)
    assert r.runs == 0 and r.hopeless and "RTL loop" in r.stop


def test_met_root_runs_nothing():
    r = S.search(ok(0.4), S.Features(wns_ns=0.4), CTX7, lambda p, n: pytest.fail("ran"), budget=6)
    assert r.runs == 0 and r.stop == "the root already meets timing"


def test_budget_is_never_exceeded_and_a_plan_runs_once():
    seen = []

    def runner(plan, nid):
        seen.append(plan.key())
        return ok(-0.5)

    r = S.search(ok(-0.3), S.Features(wns_ns=-0.3), CTX7, runner, budget=4)
    assert r.runs <= 4 and len(seen) == len(set(seen))


def test_unavailable_synthesis_checkpoint_costs_no_run():
    def runner(plan, nid):
        return {"status": "no synth checkpoint", "synth_key": "x"} if plan.needs_synth() else ok(-0.5)

    f = S.Features(wns_ns=-0.3, logic_levels=6)
    r = S.search(ok(-0.3), f, CTX7, runner, budget=3)
    assert r.runs == 3 and any(row["verdict"] == "unavailable" for row in r.journal.rows)


# ---- the order -----------------------------------------------------------------------------------------------------------------------------
def keys(f, ctx=CTX7, priors=None, plan=None, exclude=None):
    return [c.key for c in S.order(f, plan or R.ImplPlan(), ctx, priors, exclude=exclude)]


def test_hold_failure_puts_the_hold_repair_first():
    k = keys(S.Features(wns_ns=-0.1, whs_ns=-0.2))
    assert k[0] == "phys:post:hold_fix"


def test_high_fanout_net_puts_replication_first_and_names_the_net():
    f = S.Features(wns_ns=-0.2, max_fanout=400, fanout_nets=("u/cnt[3]",))
    cs = S.order(f, R.ImplPlan(), CTX7)
    assert cs[0].recipe == "fanout_replicate" and cs[0].args["nets"] == ["u/cnt[3]"] and "400 loads" in cs[0].reason


def test_logic_bound_path_offers_retiming_before_the_general_sweep():
    k = keys(S.Features(wns_ns=-0.2, logic_levels=7))
    assert k.index("retime:synth") < k.index("amd:Performance_Explore")


def test_routing_bound_path_ranks_netdelay_and_timing_opt_first():
    k = keys(S.Features(wns_ns=-0.2, route_pct=70.0))
    assert k[0] in ("amd:Performance_NetDelay_high", "amd:Performance_ExtraTimingOpt")


def test_high_utilisation_offers_congestion_sets():
    assert "amd:Congestion_SpreadLogic_high" in keys(S.Features(wns_ns=-0.2, util_pct=85.0))
    assert "amd:Congestion_SpreadLogic_high" not in keys(S.Features(wns_ns=-0.2, util_pct=20.0))


def test_slr_directives_never_offered_on_a_monolithic_part():
    for name in keys(S.Features(wns_ns=-0.2, util_pct=90.0)):
        assert "SSI" not in name and "SLR" not in name


def test_order_is_deterministic_and_leaves_out_clashes():
    f = S.Features(wns_ns=-0.2, logic_levels=5)
    assert keys(f) == keys(f)
    p = R.apply_recipe(R.ImplPlan(), "amd_strategy", {"name": "Performance_Explore"}, CTX7)
    assert not any(k.startswith("amd:") or k in R.IMPL_SETS for k in keys(f, plan=p))


def test_priors_from_the_recorded_178_runs_and_leave_one_out():
    pr = S.Priors.from_178()
    assert pr.gain, "no 178 data read"
    assert "retime:synth" in pr.gain and len(pr.gain["retime:synth"]) == 2            # lzc and mac, the two designs where retime ran
    k = "amd:Performance_RefinePlacement"
    d0 = pr.designs[k][0]
    assert pr.n(k, exclude=d0) == pr.n(k) - pr.designs[k].count(d0)
    assert abs(pr.score(k)) < max(abs(g) for g in pr.gain[k])                         # shrunk towards zero
    assert S.Priors().score(k) == 0.0


def test_priors_move_the_order_but_rules_lead():
    pr = S.Priors()
    pr.add("d1", "amd:Performance_RefinePlacement", 0.9)
    pr.add("d2", "amd:Performance_RefinePlacement", 0.9)
    base = keys(S.Features(wns_ns=-0.2))
    withp = keys(S.Features(wns_ns=-0.2), priors=pr)
    assert withp.index("amd:Performance_RefinePlacement") < base.index("amd:Performance_RefinePlacement")
    # a hold failure still comes first, whatever the priors say
    assert keys(S.Features(wns_ns=-0.2, whs_ns=-0.1), priors=pr)[0] == "phys:post:hold_fix"


def test_features_from_a_build_digest():
    dg = {"timing": {"wns_ns": -0.2, "whs_ns": 0.01, "period_ns": 5.0}, "setup_path": {"logic_levels": 6, "route_pct": 61.0, "destination": "x/D"},
          "setup_features": {"carry_chain": 8, "max_fanout": 250, "max_fanout_net": "u/n1"}}
    f = S.Features.from_digest(dg)
    assert (f.wns_ns, f.logic_levels, f.route_pct, f.max_fanout, f.fanout_nets, f.clock_ns) == (-0.2, 6, 61.0, 250, ("u/n1",), 5.0)


PATH = """Slack (VIOLATED) :        -0.161ns  (required time - arrival time)
  Source:                 a_q_reg[3]/C
                            (rising edge-triggered cell FDRE clocked by clk  {rise@0.000ns fall@1.500ns period=3.000ns})
  Destination:            u_dut/acc_reg[38]/D
  Data Path Delay:        3.159ns  (logic 1.691ns (53.538%)  route 1.468ns (46.462%))
  Logic Levels:           10  (CARRY8=6 LUT3=1 LUT6=3)
    SLICE_X15Y98         FDRE (Prop_CFF_SLICEL_C_Q)
                                                      0.114     0.155 r  a_q_reg[3]/Q
                         net (fo=37, routed)          0.267     0.422    u_dut/a_q[3]
                         net (fo=2, routed)           0.115     0.674    u_dut/acc0__275_carry_i_3_n_0
"""


def test_features_from_a_recorded_path_report():
    f = S.Features.from_path_report(PATH, whs_ns=0.05)
    assert (f.wns_ns, f.clock_ns, f.logic_levels, f.route_pct, f.max_fanout, f.fanout_nets, f.destination) == (
        -0.161, 3.0, 10, 46.462, 37, ("u_dut/a_q[3]",), "u_dut/acc_reg[38]/D")
    assert keys(f)[0] == "retime:synth"                                        # 10 logic levels: the retiming rule leads


# ---- recorded reports: the search on the 178 outcomes --------------------------------------------------------------------------------------
def test_search_on_recorded_lzc_outcomes_finds_a_passing_set_within_budget():
    d = json.loads((ROOT / "results/178_tournament/runs/lzc_treebarrel_k26_w32/impl_top2.json").read_text())
    rec = {c["id"].split("/", 1)[1]: c for c in d["candidates"] if c["id"].startswith("retime/") and c["status"] == "ok"}
    root = rec["default"]
    ctx = CTXU
    table = {}
    for n in R._strategies():
        if "amd:" + n in rec:
            table[R.apply_recipe(R.ImplPlan(), "amd_strategy", {"name": n}, ctx).key()] = rec["amd:" + n]
    assert table, "no recorded strategy matched"

    def runner(plan, nid):
        return {**table[plan.key()], "status": "ok", "clock_ns": 1.0}

    only = lambda f, p, c: [x for x in S.order(f, p, c) if x.recipe == "amd_strategy" and R.apply_recipe(p, x.recipe, x.args, c).key() in table]
    r = S.search(root, S.Features(wns_ns=root["wns_ns"]), ctx, runner, budget=4, beam=4, ordering=only, margin=0.15)
    assert r.runs <= 4 and r.best.outcome["wns_ns"] >= root["wns_ns"]


def test_run_hygiene_not_run_stops_are_left_out_of_the_analysis():
    import sys
    sys.path.insert(0, str(ROOT / "tools" / "stats"))
    import fpga_ablate as F
    recs = [{"arm": "c", "design": "a", "wns_ns": 0.1}, {"arm": "t", "design": "a", "wns_ns": 0.2, "gain": 0.1},
            {"arm": "t", "design": "b", "stop_reason": "slot_refused"}, {"arm": "t", "design": "c", "stop_reason": "rate_limited"}]
    ran, skipped = F.split_not_run(recs)
    assert len(ran) == 2 and len(skipped) == 2
    assert F.paired_numeric(recs, "t", "c", "wns_ns")["designs"] == 1


def test_paired_numeric_bootstrap_matches_ablate_on_a_known_case():
    import sys
    sys.path.insert(0, str(ROOT / "tools" / "stats"))
    import fpga_ablate as F
    recs = [{"arm": "c", "design": d, "g": 0.0} for d in "abcd"] + [{"arm": "t", "design": d, "g": 0.2} for d in "abcd"]
    r = F.paired_numeric(recs, "t", "c", "g")
    assert r["effect"] == pytest.approx(0.2) and (r["lo"], r["hi"]) == (pytest.approx(0.2), pytest.approx(0.2)) and r["better"] == 4 and r["p_sign"] == 0.125
