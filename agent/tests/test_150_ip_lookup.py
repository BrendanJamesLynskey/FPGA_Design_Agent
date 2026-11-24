"""Brief 150: the IP-library retriever (flow/iplookup.py), the ``ip_lookup`` tool, ``python -m agent ip`` and the labelled set
the retrieval probe uses. Plain Python: no model, no Vivado, no simulator."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from agent.core import TOOLS, dispatch, tool_list
from agent.core.session import ROOT
from flow import ipvariants as iv, iplookup as il

LABELLED = ROOT / "results" / "150_ip_lookup" / "labelled_queries.yaml"


def test_labelled_set_is_well_formed() -> None:
    d = yaml.safe_load(LABELLED.read_text())
    assert len(d["positives"]) == 20 and len(d["decoys"]) == 10
    ids = [p["id"] for p in d["positives"] + d["decoys"]]
    assert len(ids) == len(set(ids))
    assert {p["split"] for p in d["positives"] + d["decoys"]} == {"dev", "test"}
    for p in d["positives"]:
        assert p["accept"] and set(p["accept"]) <= set(iv.entries()), p["id"]


@pytest.mark.parametrize("split", ["dev", "test"])
def test_retrieval_probe_thresholds(split: str) -> None:
    """The probe's own floor (not the measured figure, which is in results/150_ip_lookup): both halves recall at least
    8/10 at rank 3, and the decoys are mostly refused."""
    d = yaml.safe_load(LABELLED.read_text())
    pos = [p for p in d["positives"] if p["split"] == split]
    dec = [p for p in d["decoys"] if p["split"] == split]
    ok = sum(1 for p in pos if {h["block"] for h in il.lookup(p["query"])["hits"]} & set(p["accept"]))
    clean = sum(1 for p in dec if not il.lookup(p["query"])["hits"])
    assert ok >= 8 and clean >= 4, (ok, clean)


def test_a_request_the_library_cannot_answer_says_nothing_fits() -> None:
    r = il.lookup("DDR3 memory controller for a 16-bit SDRAM interface")
    assert r["fits"] is False and r["hits"] == []
    assert r["nearest_miss"] and any("near misses" in n for n in r["notes"])


def test_fifo_decoy_names_the_house_answer() -> None:
    r = il.lookup("asynchronous FIFO to cross a data bus between two clock domains")
    assert not r["fits"] and any("XPM" in n for n in r["notes"])


def test_ten_gigabit_is_not_read_as_gigabit() -> None:
    assert il.lookup("10 Gigabit Ethernet MAC with XGMII")["hits"] == []
    assert il.lookup("gigabit Ethernet MAC for a PHY on RGMII")["hits"][0]["block"] == "eth_mac_rgmii"


def test_variants_are_ranked_against_the_budget() -> None:
    top = il.lookup("FIR filter", budget={"dsp": 0})["hits"][0]
    assert top["block"] == "fir"
    fits = {v["variant"]: v["fits"] for v in top["variants"]}
    assert fits["dsp_bram"] is False and any(fits.values())
    assert any("dsp" in " ".join(v["reasons"]) for v in top["variants"] if not v["fits"])


def test_vhdl_request_is_not_answered_with_systemverilog() -> None:
    r = il.lookup("FIR filter", language="vhdl")
    assert r["hits"] and not r["fits"] and not r["hits"][0]["language_ok"]
    assert any("not available in vhdl" in n for n in r["notes"])
    assert il.snippet("fir", language="vhdl").startswith("-- no vhdl")


def test_every_entry_has_a_readable_instantiation_snippet() -> None:
    for b in iv.entries():
        sn = il.snippet(b)
        top = iv._yaml(b)["top"]
        assert sn.lstrip().startswith(top) and (".clk(clk)" in sn.replace(" ", "") or ".aclk(aclk)" in sn.replace(" ", "")), b      # AXI entries name their clock aclk
        assert "could not be read" not in sn, b


def test_verified_label_is_unknown_without_a_record_and_read_when_present(tmp_path: Path, monkeypatch) -> None:
    assert il.verified_status("fir")["label"] == "unknown"
    ip = tmp_path / "ip_lib"
    (ip / "fir").mkdir(parents=True)
    (ip / "fir" / "verified.json").write_text(json.dumps({"label_kind": "not_assessed", "label": "Not assessed: x",
                                                          "criteria": [{"title": "t", "state": "not_measured"}]}))
    monkeypatch.setattr(il, "IP", ip)
    v = il.verified_status("fir")
    assert v["label"] == "not_assessed" and v["unmet_criteria"] == ["t"]


def test_show_unknown_entry_is_a_clean_error() -> None:
    with pytest.raises(ValueError, match="no library entry"):
        il.show("nonesuch")


def test_tool_is_registered_offered_at_stage_1_and_logs(session) -> None:
    from agent.graph.stages import MACHINE
    tool_list()                                    # registers the tools
    assert "ip_lookup" in TOOLS and not TOOLS["ip_lookup"].hardware
    assert "ip_lookup" in MACHINE[1].tools and all("ip_lookup" not in s.tools for s in MACHINE if s.n != 1)
    r = dispatch(session, "ip_lookup", {"action": "search", "query": "answer ping requests"})
    assert r["ok"] and "icmp_echo" in r["output"]
    r2 = dispatch(session, "ip_lookup", {"action": "search", "query": "UART with a baud rate generator"})
    assert r2["ok"] and "nothing fits" in r2["output"]
    log = [json.loads(x) for x in (session.design / "build" / "ip_lookup.jsonl").read_text().splitlines()]
    assert [x["fits"] for x in log] == [True, False] and log[0]["considered"][0]["block"] == "icmp_echo"
    r3 = dispatch(session, "ip_lookup", {"action": "show", "block": "mdio_master"})
    assert r3["ok"] and "u_mdio_master" in r3["output"]


def test_tool_refuses_bad_arguments(session) -> None:
    assert not dispatch(session, "ip_lookup", {"action": "search"}).get("ok", False)
    assert dispatch(session, "ip_lookup", {"action": "copy", "block": "fir"}).get("refused") or \
        not dispatch(session, "ip_lookup", {"action": "copy", "block": "fir"}).get("ok")
    assert dispatch(session, "ip_lookup", {"action": "show", "block": "../etc"}).get("refused") or \
        not dispatch(session, "ip_lookup", {"action": "show", "block": "../etc"}).get("ok")
    assert not dispatch(session, "ip_lookup", {"action": "show", "block": "nonesuch"})["ok"]


def test_the_planner_prompt_names_the_tool_not_a_cli() -> None:
    from flow import timing_plan as tp
    assert "ip_lookup" in tp.DATAPATHS_CONVENTION and "python3 -m flow.ipvariants --search" not in tp.DATAPATHS_CONVENTION
    assert "ip_lookup" in il.IP_LOOKUP_CONVENTION and "nothing fits" in il.IP_LOOKUP_CONVENTION


# --- python -m agent ip use ---------------------------------------------------------------------------------------------

def _fcs(tmp_path: Path) -> Path:
    d = tmp_path / "fcs"
    shutil.copytree(ROOT / "designs" / "b102_managed_fcs", d)
    return d


def test_use_adds_a_frozen_component_that_validates(tmp_path: Path) -> None:
    from agent.core import managed
    from agent.ip_cmd import use
    d = _fcs(tmp_path)
    code, text = use("mdio_master", d, {}, None, dry_run=True)
    assert code == 0 and not (d / "ip").exists() and "dry run" in text
    code, text = use("mdio_master", d, {}, None, dry_run=False)
    assert code == 0 and (d / "ip" / "mdio_master" / "rtl" / "mdio_master.sv").is_file()
    p = managed.load(d)
    c = p.component("mdio_master")
    assert c.ownership == "frozen" and c.level == "rtl" and c.module == "mdio_master"
    assert managed.trust(p, c)[0] == "documented"
    assert use("mdio_master", d, {}, None, dry_run=False)[0] == 2                 # already there


def test_use_needs_an_existing_manifest(tmp_path: Path) -> None:
    from agent.ip_cmd import use
    code, text = use("fir", tmp_path, {}, None, dry_run=False)
    assert code == 2 and "no project.yaml" in text and not list(tmp_path.iterdir())


def test_cli_search_and_help(capsys) -> None:
    from agent.ip_cmd import main
    assert main(["search", "multicast", "group"]) == 0
    assert "igmp_join" in capsys.readouterr().out
    assert main(["show", "nonesuch"]) == 2
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "near miss is NOT a recommendation" in capsys.readouterr().out


def test_part_is_a_part_name_not_a_path(session) -> None:
    with pytest.raises(ValueError, match="not a device part name"):
        il.lookup("FIR filter", part="../../x")
    r = dispatch(session, "ip_lookup", {"action": "search", "query": "FIR filter", "part": "../../x"})
    assert r.get("refused") or not r.get("ok")


def test_a_variant_with_an_unmeasured_fmax_is_unknown_not_rejected() -> None:
    """Found by the stage-1 trial: crc32_step `word` has no measured Fmax (a register-to-register path with no timed path), so
    a request with a clock marked it as not fitting and the planner wrote a CRC fresh. It is now "unknown", and the budget misses stay "does not fit"."""
    h = il.lookup("CRC-32 reflected word per clock", clock_ns=10)["hits"][0]
    st = {v["variant"]: v["status"] for v in h["variants"]}
    assert h["block"] == "crc32_step" and st["word"] == "unknown"
    f = il.lookup("FIR filter", budget={"dsp": 0})["hits"][0]
    assert {v["variant"]: v["status"] for v in f["variants"]}["dsp_bram"] == "does not fit"


# --- not in scored runs (planner decision 2026-11-22) -------------------------------------------------------------------

def _cfg(tmp_path, **kw):
    from agent.graph.run import Config
    return Config(spec_md=kw.pop("spec_md", tmp_path / "spec.md"), name="x", **kw)


def test_ip_lookup_is_withheld_from_scored_runs_and_fails_closed(tmp_path, monkeypatch) -> None:
    from agent.graph.run import ip_lookup_allowed
    monkeypatch.delenv("FDA_SCORED_RUN", raising=False)
    assert ip_lookup_allowed(_cfg(tmp_path)) is True
    assert ip_lookup_allowed(_cfg(tmp_path, hidden_spec=tmp_path / "full.md")) is False
    assert ip_lookup_allowed(_cfg(tmp_path, spec_tests=True)) is False
    assert ip_lookup_allowed(_cfg(tmp_path, interview="oracle")) is False
    assert ip_lookup_allowed(_cfg(tmp_path, spec_md=ROOT / "benchmark" / "pool" / "t" / "spec.md")) is False
    assert ip_lookup_allowed(object()) is False                      # unreadable config: withheld
    monkeypatch.setenv("FDA_SCORED_RUN", "1")
    assert ip_lookup_allowed(_cfg(tmp_path)) is False


def test_the_plan_offers_ip_lookup_only_when_allowed(tmp_path, monkeypatch) -> None:
    from types import SimpleNamespace
    from agent.graph import run as gr
    tool_list()
    monkeypatch.delenv("FDA_SCORED_RUN", raising=False)
    def core(cfg):
        rt = SimpleNamespace(cfg=cfg, session=SimpleNamespace(stage="x"), meter=SimpleNamespace(stage_limits={}, turns_left=lambda: 1))
        monkeypatch.setattr(gr, "role_inputs", lambda *a, **k: {})
        monkeypatch.setattr(gr, "_p", lambda *a, **k: "")
        return gr.subagent_plan(rt, "rtl", "p", gr.role_allowed("rtl", 1))["core_tools"]
    assert "ip_lookup" in core(_cfg(tmp_path))
    assert "ip_lookup" not in core(_cfg(tmp_path, hidden_spec=tmp_path / "h.md"))
