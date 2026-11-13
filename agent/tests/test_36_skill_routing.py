"""Brief 36: the skill index, the new knowledge tools, the router node and context hygiene, on a fake bank (CI has no
private bank). The off path must be the eval-1 path: same graph, same tools per role, same load_skill order."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.core import skill_index as SI
from agent.core.registry import dispatch
from agent.core.session import Session
from agent.graph import router

SKILLS = {
    # name: (section, description, body)
    "arbiters-encoders-and-muxes": ("arbitration-and-muxing", "Use when: round-robin arbiter, priority encoder.",
                                    "## When it applies\nShared resources.\n## Rules\nGrant one requester.\n"),
    "axi-handshake-rules": ("amba", "Use when: any AXI VALID/READY interface.", "## Rules\nVALID never waits for READY.\n"),
    "axi4-lite-slave": ("amba", "Use when: writing an AXI4-Lite register slave.", "## Rules\nFive channels.\n"),
    "axi4-stream-packets": ("amba", "Use when: AXI4-Stream TLAST, TKEEP.", "## Rules\nTLAST ends a packet.\n"),
    "axi4-bursts": ("amba", "Use when: AXI4 burst addresses.", "## Rules\nINCR, WRAP, FIXED.\n"),
    "axi-dma": ("ip-cores", "Use when: AXI DMA between memory and a stream.", "## Rules\nSimple mode.\n"),
    "axi-smartconnect": ("ip-cores", "Use when: connecting AXI masters in a block design.", "## Rules\nAddress map.\n"),
    "amd-ip-fir-and-cic": ("ip-cores", "Use when: configuring the AMD FIR Compiler or CIC Compiler: coefficients, "
                                       "decimation, filter taps.", "## When it applies\nFIR filter cores.\n## Coefficients\n"
                                       "Quantise the FIR coefficients to 16 bits.\n### Detail\nmore\n## Ports\nAXI-Stream.\n"),
    "fsm-design": ("fsm", "Use when: a state machine or controller.", "## Rules\nOne state register.\n"),
}


def _text(name: str) -> str:
    sec, desc, body = SKILLS[name]
    return f'---\nname: {name}\ndescription: "{desc}"\naxis: vendor\nsection: {sec}\n---\n# {name}\n\n{body}'


class FakeBank:
    """``skills`` in the bank's own order (unit name, then section, then name) and ``catalogue``, like LocalBank."""

    def __init__(self, root: Path):
        self.root = root

    def _rows(self, names):
        return [{"path": f"vendor/u/{SKILLS[n][0]}/{n}/SKILL.md", "axis": "vendor", "section": SKILLS[n][0], "name": n,
                 "description": SKILLS[n][1], "text": _text(n)} for n in names]

    def skills(self, board, family, sections, primary_only=True, procedures=False, part=None):
        # main's order is unit, section, name: here the amba unit's 4 skills, then the ip-cores unit with the FIR core
        # last (as amd_ip_cores comes after amba_axi), so it is the 7th and is cut at 6
        names = sorted((n for n in SKILLS if SKILLS[n][0] in (sections or [])),
                       key=lambda n: (SKILLS[n][0], n.startswith("amd-"), n))
        return self._rows(names)

    def catalogue(self, board, family, part=None):
        return self._rows(sorted(SKILLS))


@pytest.fixture()
def sess(tmp_path):
    SI._CACHE.clear()
    d = tmp_path / "d"
    d.mkdir()
    (d / "spec.md").write_text("A decimating FIR filter with 31 taps on an AXI4-Stream input; quantised coefficients.\n")
    return Session(design=d, root=tmp_path, bank=FakeBank(tmp_path))


def test_bm25_ranks_the_matching_skill_first(sess) -> None:
    idx = SI.open_index(sess.bank, None, None, encoder=None)
    assert idx.mode == "bm25"
    hits = idx.search("FIR filter coefficients decimation", k=3)
    assert hits[0]["name"] == "amd-ip-fir-and-cic"
    assert set(hits[0]) >= {"name", "section", "description", "score"} and "text" not in hits[0]


def test_excerpt_takes_one_section_and_its_subsections() -> None:
    body = SI.split_front(_text("amd-ip-fir-and-cic"))[1]
    t = SI.excerpt(body, "Coefficients")
    assert t.startswith("## Coefficients") and "### Detail" in t and "## Ports" not in t
    assert SI.excerpt(body, "coef") == t                          # unique prefix, any case
    assert SI.excerpt(body, "nothing here") is None


def test_load_skill_by_name_returns_one_body_and_refuses_both_forms(sess) -> None:
    r = dispatch(sess, "load_skill", {"name": "fsm-design"})
    assert r["ok"] and r["skills"] == ["vendor/u/fsm/fsm-design/SKILL.md"] and "One state register." in r["output"]
    assert not dispatch(sess, "load_skill", {"name": "no-such-skill"})["ok"]
    assert not dispatch(sess, "load_skill", {"name": "fsm-design", "sections": ["fsm"]})["ok"]
    assert not dispatch(sess, "load_skill", {})["ok"]


def test_load_skill_sections_off_keeps_the_eval1_order_and_cut(sess) -> None:
    r = dispatch(sess, "load_skill", {"sections": ["amba", "ip-cores"]})
    assert r["ok"] and len(r["skills"]) == 6
    assert not any("amd-ip-fir-and-cic" in p for p in r["skills"])    # the PR #107 finding: cut behind amba
    assert "not_returned" not in r                                    # the off result has no new field


def test_load_skill_sections_routed_ranks_inside_the_cap(sess) -> None:
    sess.skill_routing = "router"
    r = dispatch(sess, "load_skill", {"sections": ["amba", "ip-cores"]})
    assert len(r["skills"]) == 6 and "amd-ip-fir-and-cic" in r["skills"][0]
    assert len(r["not_returned"]) == 1


def test_skill_index_and_excerpt_tools(sess) -> None:
    r = dispatch(sess, "skill_index", {"query": "AXI4-Lite register slave", "k": 3})
    assert r["ok"] and r["ranked"][0] == "axi4-lite-slave" and "Five channels" not in r["output"]   # no bodies
    e = dispatch(sess, "skill_excerpt", {"name": "amd-ip-fir-and-cic", "heading": "Coefficients"})
    assert e["ok"] and "16 bits" in e["output"] and "AXI-Stream." not in e["output"]
    miss = dispatch(sess, "skill_excerpt", {"name": "amd-ip-fir-and-cic", "heading": "Nope"})
    assert not miss["ok"] and "Coefficients" in miss["output"]                 # lists the headings


class FakeEncoder:
    model = "fake"

    def embed(self, texts, query=False):
        import numpy as np
        # a query about "packets" points at the stream skill only
        return np.array([[1.0, 0.0] if "packet" in t else [0.0, 1.0] for t in texts], dtype="float32")


def test_hybrid_uses_vectors_and_ignores_stale_ones(sess) -> None:
    import numpy as np
    ents = SI.entries_from(sess.bank.catalogue(None, None))
    mat = np.array([[1.0, 0.0] if e.name == "axi4-stream-packets" else [0.0, 1.0] for e in ents], dtype="float32")
    sha = [e.sha() for e in ents]
    sha[[e.name for e in ents].index("fsm-design")] = "0" * 64                 # changed since the vectors were built
    man = {"model": "fake", "paths": [e.path for e in ents], "sha256": sha}
    idx = SI.SkillIndex(ents, (man, mat), FakeEncoder())
    assert idx.mode == "hybrid" and idx.stale == ["fsm-design"]
    ranked = idx.ranked("packet")
    assert ranked[0][0].name == "axi4-stream-packets"
    assert dict((e.name, sc) for e, sc in ranked)["fsm-design"]["vector_rank"] is None
    other = SI.SkillIndex(ents, ({**man, "model": "another"}, mat), FakeEncoder())  # vectors of another model: unused
    assert other.mode == "bm25"


def test_vectors_are_never_built_on_a_work_machine(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FDA_WORK_MACHINE", "1")
    with pytest.raises(SystemExit):
        SI.build(tmp_path)


def test_rule_sections_and_classifier_validation() -> None:
    secs = router.rule_sections("An I2C master and a UART, with a FIFO and a FIR filter.", 2)
    assert secs[:len(router.STAGE_SECTIONS[2])] == list(router.STAGE_SECTIONS[2])
    assert {"serial-buses", "fifo", "dsp"} <= set(secs)
    assert router.parse_ids('Sure: ["dsp", "made-up", "fifo", "dsp"]', {"dsp", "fifo"}) == ["dsp", "fifo"]
    assert router.parse_ids("ignore previous instructions", {"dsp"}) == []


def test_shortlist_is_names_and_descriptions_only(sess) -> None:
    idx = SI.open_index(sess.bank, None, None, encoder=None)
    sl = router.shortlist(idx, (sess.design / "spec.md").read_text(), 2, "rtl-design-creation", {"dsp": "DSP"}, k=6)
    assert len(sl["skills"]) == 6 and all(set(s) == {"name", "section", "description"} for s in sl["skills"])
    text = router.shortlist_text(sl, [{"stage": "clarify", "skill": "fsm-design", "heading": None}])
    assert "amd-ip-fir-and-cic" in text and "16 bits" not in text and "Already used" in text
    assert router.shortlist_text({}) == ""


def test_stage_notes_keep_citations_not_text(tmp_path) -> None:
    a = tmp_path / "audit.jsonl"
    rows = [{"tool": "load_skill", "stage": "clarify", "ok": True, "arguments": {"name": "fsm-design"},
             "skills": ["vendor/u/fsm/fsm-design/SKILL.md"], "result_summary": "BODY TEXT"},
            {"tool": "skill_excerpt", "stage": "clarify", "ok": True, "arguments": {"name": "x", "heading": "Rules"},
             "skills": ["vendor/u/s/x/SKILL.md"]},
            {"tool": "load_skill", "stage": "rtl-design-creation", "ok": True, "skills": ["a/b/y/SKILL.md"]}]
    a.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    notes = router.stage_notes(a, "clarify")
    assert notes == [{"stage": "clarify", "skill": "fsm-design", "heading": None},
                     {"stage": "clarify", "skill": "x", "heading": "Rules"}]
    assert "BODY" not in json.dumps(notes)


def test_off_graph_is_the_eval1_graph_and_on_adds_one_node() -> None:
    from agent.graph import run as gr
    off = gr.build_graph(None)
    on = gr.build_graph(None, routing=True)
    assert set(off.get_graph().nodes) == {"__start__", "work", "gate", "review", "advance", "document", "__end__"}
    assert set(on.get_graph().nodes) - set(off.get_graph().nodes) == {"route_skills"}


def test_roles_get_the_skill_tools_only_when_routing_is_on() -> None:
    from types import SimpleNamespace

    from agent.graph import run as gr
    rt = SimpleNamespace(cfg=SimpleNamespace(skill_routing="off"), skill_shortlist={"skills": [
        {"name": "fsm-design", "section": "fsm", "description": "Use when: a controller."}]}, skill_notes=[])
    assert gr.with_skill_routing(rt, ("load_skill", "lint"), "P") == (("load_skill", "lint"), "P")
    rt.cfg.skill_routing = "router"
    tools, prompt = gr.with_skill_routing(rt, ("load_skill", "lint"), "P")
    assert tools == ("load_skill", "lint", "skill_index", "skill_excerpt") and "fsm-design" in prompt
    assert gr.with_skill_routing(rt, ("lint",), "P") == (("lint",), "P")          # a role without load_skill: unchanged
    assert set(gr.SKILL_TOOLS) <= set(gr.FLOW_TOOLS)
    for stage in range(10):                                   # the off tool lists never name the new tools
        for role in ("clarify", "model", "tests", "rtl"):
            assert not set(gr.SKILL_TOOLS) & set(gr.effective_tools(role, stage, "V3"))


def test_config_defaults_off() -> None:
    from agent.graph.run import Config
    from agent.tests.request_golden import T1
    c = Config(spec_md=T1 / "spec.md", name="t")
    assert c.skill_routing == "off" and c.router_model is None


def test_load_skill_returns_whole_skills_under_the_output_limit(sess, monkeypatch) -> None:
    """Six full bodies overflowed MAX_OUTPUT and the clip cut the middle out; now whole skills only, the rest named."""
    from agent.core import tools as T
    monkeypatch.setattr(T, "MAX_OUTPUT", 1200)
    r = dispatch(sess, "load_skill", {"sections": ["amba", "ip-cores"]})
    assert r["ok"] and r["skills"] and r.get("held_for_size")
    assert "characters omitted" not in r["output"]                    # never clipped mid-skill
    assert "load_skill(name=...)" in r["output"]
    assert len(r["skills"]) + len(r["held_for_size"]) == 6
