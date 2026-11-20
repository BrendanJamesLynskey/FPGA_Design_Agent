"""Brief 114: the blind document cross-read (flow/doc_crossread.py). Everything here runs with no model: the reader is a stub that returns
hand-written facts, and the code files are the real fixtures of results/114_doc_crossread/cases/ (the 96D five-word driver, the 96D2 ten-word driver,
three correct register files and four planted mistakes). The measured behaviour of a live reader is in results/114_doc_crossread/RESULTS.md."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flow import doc_crossread as D

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "results" / "114_doc_crossread" / "cases"


def code(case: str, *names: str) -> dict:
    return D.extract_code([CASES / case / "code" / n for n in names])


def F(id: str, subject: str, kind: str, **kw) -> dict:
    d = {"id": id, "subject": subject, "field": kw.pop("field", None), "aliases": kw.pop("aliases", []), "kind": kind, "unit": None, "applies_to": "all",
         "for_target": True, "statement": "", "names": kw.pop("names", []), "ref": None, "quote": "", "quote_ok": True, "page_ok": True, "page": 1,
         "value": kw.pop("value", None), "values": kw.pop("values", None), "lo": kw.pop("lo", None), "hi": kw.pop("hi", None)}
    d.update(kw)
    return d


def status(case: str, names: tuple[str, ...], facts: list[dict]) -> dict[str, str]:
    r = D.compare(facts, code(case, *names))
    return {x["fact"]["id"]: x["status"] for x in r["rows"]}


# ---- the evaluator ----------------------------------------------------------------------------------------------------------------

def ev(src: str, ns: dict | None = None, funcs: dict | None = None):
    import ast
    return D.Evaluator(ns or {}, funcs or {}).ev(ast.parse(src, mode="eval").body)


def test_evaluator_arithmetic_comprehensions_and_limits() -> None:
    assert ev("[0x10 + i for i in range(3)]") == [16, 17, 18]
    assert ev("(1 << 80) - 1 >> 78") == 3
    assert ev("[0] * 5 + [1] * 2") == [0, 0, 0, 0, 0, 1, 1]
    assert ev("{k: v for k, v in zip([1], [2])}" if False else "{1: 2}") == {1: 2}
    for bad in ("__import__('os')", "open('x')", "[0] * 10**9", "1 << 100000", "x.y", "(lambda: 1)()"):
        with pytest.raises(D.Unresolved):
            ev(bad)


def test_evaluator_calls_only_simple_functions_of_the_file() -> None:
    import ast
    tree = ast.parse("def w(n, k=1):\n    '''doc'''\n    if n < 0:\n        raise ValueError\n    m = n * k\n    return [m + i for i in range(2)]\n")
    fn = {"w": tree.body[0]}
    assert ev("w(4, k=2)", funcs=fn) == [8, 9]
    with pytest.raises(D.Unresolved):
        ev("w(-1)", funcs=fn)
    loop = ast.parse("def w(n):\n    while True:\n        pass\n").body[0]
    with pytest.raises(D.Unresolved):
        ev("w(1)", funcs={"w": loop})


# ---- the code side ----------------------------------------------------------------------------------------------------------------

def facts_by_name(c: dict) -> dict:
    return {f["name"]: f["value"] for f in c["facts"]}


def test_python_side_reads_the_five_word_driver_and_evaluates_the_ten_word_helpers() -> None:
    five = facts_by_name(code("h1_96d_five_word", "hw.py", "eyescan.py"))
    assert len(five["QUALIFIER"]) == 5 and five["A_ES_QUALIFIER0"] == 0x3F and "A_ES_QUALIFIER5" not in five
    ten = code("h2_96d2_ten_word", "hw.py", "eyescan.py")
    v = facts_by_name(ten)
    assert len(v["QUALIFIER"]) == len(v["SDATA_MASK_32"]) == 10 and v["A_ES_QUALIFIER5"] == 0xE7
    assert v["QUALIFIER_ADDRS"] == [0x3F, 0x40, 0x41, 0x42, 0x43, 0xE7, 0xE8, 0xE9, 0xEA, 0xEB]      # word_addrs(), a function of eyescan.py, evaluated
    assert v["SDATA_MASK_32"] == [0xFFFF] * 3 + [0, 0] + [0xFFFF] * 5                                   # words_of(sdata_mask_160(32)), two helpers deep
    assert ten["not_parsed"] == []


def test_systemverilog_and_c_declarations() -> None:
    sv = facts_by_name(code("f2_timer", "tb_timer.sv"))
    assert sv["TCSR1"] == 0x10 and sv["LOAD"] == 0x20 and sv["CASC"] == 0x800
    g = code("f3_gpio", "tb_gpio.sv")
    assert facts_by_name(g)["GIER"] == 0x11C and any(f.get("declared_width") == 9 for f in g["facts"] if f["name"] == "IER")
    h = code("f4_zb_accel", "zb_accel_regs.h")
    assert facts_by_name(h)["ZB_ACCEL_ID_MAGIC_RESET"] == 0x64B3 and h["common_prefix"] == ["ACCEL", "ZB"]


def test_what_is_not_parsed_is_listed_not_hidden(tmp_path: Path) -> None:
    p = tmp_path / "x.sv"
    p.write_text("localparam int A = 5, B = 'x;\nlocalparam [3:0] T = '{1, 2};\nlocalparam int C = A + 1; // comment 99\nlocalparam int D = $bits(foo);\n")
    c = D.extract_code([p])
    assert facts_by_name(c) == {"A": 5, "C": 6} and {u["name"] for u in c["not_parsed"]} >= {"T", "D"}
    q = tmp_path / "y.py"
    q.write_text("import os\nA = os.getpid()\nB = 3\n")
    c = D.extract_code([q])
    assert facts_by_name(c) == {"B": 3} and c["not_parsed"][0]["name"] == "A"


# ---- the comparison ---------------------------------------------------------------------------------------------------------------

UG576 = [F("1", "ES_QUALIFIER", "word_count", value=10), F("2", "ES_QUAL_MASK", "word_count", value=10), F("3", "ES_SDATA_MASK", "word_count", value=10),
         F("4", "ES_QUALIFIER5", "address", value=0xE7), F("5", "ES_QUAL_MASK5", "address", value=0xEC), F("6", "ES_SDATA_MASK9", "address", value=0xF5),
         F("7", "ES_QUALIFIER0", "address", value=0x3F), F("8", "ES_CONTROL", "address", value=0x3C), F("9", "es_control_status", "address", value=0x253),
         F("10", "USE_PCS_CLK_PHASE_SEL", "condition", names=["USE_PCS_CLK_PHASE_SEL", "ES_CLK_PHASE_SEL"])]


def test_the_96d_five_word_driver_is_flagged_on_word_count_and_addresses() -> None:
    s = status("h1_96d_five_word", ("hw.py", "eyescan.py"), UG576)
    assert (s["1"], s["2"], s["3"]) == ("disagree",) * 3          # five words against ten
    assert (s["4"], s["5"], s["6"]) == ("disagree",) * 3          # 0x0E7.., 0x0EC.., 0x0F5 are nowhere in the code
    assert (s["7"], s["8"], s["9"]) == ("agree",) * 3             # the five-word block's own addresses are right
    assert s["10"] == "not_in_code"                               # a condition the code never mentions


def test_the_96d2_ten_word_driver_agrees() -> None:
    s = status("h2_96d2_ten_word", ("hw.py", "eyescan.py"), UG576)
    assert {k: v for k, v in s.items() if k != "10"} == {k: "agree" for k in "123456789"}
    assert s["10"] == "not_in_code"


def test_agree_by_value_is_marked_and_a_wrong_address_is_not_rescued_by_value() -> None:
    r = D.compare([F("1", "TOTALLY_OTHER_NAME", "address", value=0x3F), F("2", "TOTALLY_OTHER_NAME", "address", value=0x777)], code("h1_96d_five_word", "hw.py", "eyescan.py"))
    assert [(x["status"], x["tier"]) for x in r["rows"]] == [("agree", "value"), ("not_in_code", None)]


def test_register_files_correct_and_planted() -> None:
    uart = [F("1", "Rx FIFO", "address", value=0), F("2", "Tx FIFO", "address", value=4), F("3", "STAT_REG", "address", value=8), F("4", "CTRL_REG", "address", value=12)]
    assert set(status("f1_uartlite", ("tb_uartlite.sv",), uart).values()) == {"agree"}
    assert status("p1_uartlite_stat_ctrl_swapped", ("tb_uartlite.sv",), uart) == {"1": "agree", "2": "agree", "3": "disagree", "4": "disagree"}
    tim = [F("1", "TCSR0", "address", value=0), F("2", "LOAD0", "bit_range", lo=5, hi=5), F("3", "ENT0", "bit_range", lo=7, hi=7), F("4", "CASC", "bit_range", lo=11, hi=11)]
    assert set(status("f2_timer", ("tb_timer.sv",), tim).values()) == {"agree"}
    assert status("p2_timer_load_bit", ("tb_timer.sv",), tim) == {"1": "agree", "2": "disagree", "3": "agree", "4": "agree"}
    gp = [F("1", "GPIO_DATA", "address", value=0), F("2", "GPIO2_TRI", "address", value=12), F("3", "GIER1", "address", value=0x11C), F("4", "IP IER1", "address", value=0x128)]
    assert set(status("f3_gpio", ("tb_gpio.sv",), gp).values()) == {"agree"}
    zb = [F("1", "ID", "reset_value", value=0x64B30100), F("2", "ID", "reset_value", field="VERSION", value=0x100), F("3", "ID", "bit_range", field="VERSION", lo=0, hi=15),
          F("4", "ID", "bit_range", field="MAGIC", lo=16, hi=31), F("5", "COEF3", "address", value=0x4C)]
    assert set(status("f4_zb_accel", ("zb_accel_regs.h",), zb).values()) == {"agree"}
    assert status("p3_zb_accel_id_reset", ("zb_accel_regs.h",), zb) == {"1": "disagree", "2": "disagree", "3": "agree", "4": "agree", "5": "agree"}
    assert status("p4_zb_accel_version_width", ("zb_accel_regs.h",), zb) == {"1": "agree", "2": "agree", "3": "disagree", "4": "agree", "5": "agree"}


def test_other_variants_are_not_compared() -> None:
    r = D.compare([F("1", "ES_QUALIFIER", "word_count", value=5, applies_to="UltraScale", for_target=False)], code("h2_96d2_ten_word", "hw.py", "eyescan.py"))
    assert r["rows"][0]["status"] == "other_variant"


# ---- the document and the reader --------------------------------------------------------------------------------------------------

def doc(text: str = "Table 4-20\nES_QUALIFIER0  16-bit  0x03F\nten 16-bit words for UltraScale+") -> dict:
    return {"source": "x", "pages": [230], "text": "[[page 230]]\n" + text, "sha256": "0", "chars": len(text), "page_text": {230: text}}


def test_quotations_are_checked_against_the_excerpt_by_code() -> None:
    reply = {"facts": [
        {"id": "F1", "subject": "ES_QUALIFIER0", "kind": "address", "value": "0x03F", "page": 230, "quote": "es_qualifier0 16-bit\n 0x03F"},
        {"id": "F2", "subject": "ES_QUALIFIER0", "kind": "word_count", "value": 10, "page": 231, "quote": "ten 16-bit words"},
        {"id": "F3", "subject": "X", "kind": "address", "value": 1, "page": 230, "quote": "words are never mentioned like this"},
        {"id": "F4", "subject": "X", "kind": "nonsense", "value": 1},
        {"id": "F5", "subject": "X", "kind": "bit_range", "value": 1}]}
    facts, problems = D.validate_facts(reply, doc())
    by = {f["id"]: f for f in facts}
    assert by["F1"]["value"] == 0x3F and by["F1"]["quote_ok"] and by["F1"]["page_ok"]
    assert by["F2"]["quote_ok"] and not by["F2"]["page_ok"] and by["F2"]["found_on_pages"] == [230]
    assert not by["F3"]["quote_ok"] and "F4" not in by and "F5" not in by
    assert any("quotation" in p for p in problems) and any("kind" in p for p in problems) and any("lo" in p for p in problems)


def test_reader_sees_only_the_document_and_gets_one_repair_round(tmp_path: Path) -> None:
    (tmp_path / "graph" / "doc_crossread").mkdir(parents=True)
    for n, t in (("system", "SYS"), ("user", "T=<<TOPIC>> G=<<TARGET>> D=<<DOCUMENT>>"), ("repair", "FIX <<PROBLEMS>>")):
        (tmp_path / "graph" / "doc_crossread" / f"{n}.txt").write_text(t)
    seen: list[str] = []

    def llm(system: str, user: str) -> str:
        seen.append(user)
        return "not json" if len(seen) == 1 else json.dumps({"facts": [{"id": "F1", "subject": "S", "kind": "address", "value": 1, "page": 230, "quote": "ES_QUALIFIER0"}]})
    import hashlib
    # the loader needs a manifest: build it the way the knowledge repository's tool does
    mf = {"version": 1, "prompts": {f"graph/doc_crossread/{n}": {"file": f"graph/doc_crossread/{n}.txt", "bytes": 1,
                                                                   "sha256": hashlib.sha256((tmp_path / "graph" / "doc_crossread" / f"{n}.txt").read_bytes()).hexdigest()}
                                    for n in ("system", "user", "repair")}}
    (tmp_path / "MANIFEST.json").write_text(json.dumps(mf))
    import os
    os.environ["FDA_PROMPTS_UNPINNED"] = "1"
    try:
        r = D.read_document(doc(), "the topic", "the target", llm, prompt_root=tmp_path)
    finally:
        del os.environ["FDA_PROMPTS_UNPINNED"]
    assert r["repairs"] == 1 and len(r["facts"]) == 1 and r["facts"][0]["quote_ok"]
    assert "T=the topic G=the target D=[[page 230]]" in seen[0] and "FIX" in seen[1] and "not valid JSON" in seen[1]


def test_end_to_end_with_a_stored_reply_and_the_cli(tmp_path: Path, capsys) -> None:
    d = tmp_path / "excerpt.txt"
    d.write_text("UART Lite register map\nTable 2-4\nSTAT_REG at offset 08h\nCTRL_REG at offset 0Ch\n")
    reply = tmp_path / "reply.json"
    reply.write_text(json.dumps({"facts": [
        {"id": "F1", "subject": "STAT_REG", "kind": "address", "value": "0x08", "page": 1, "ref": "Table 2-4", "quote": "STAT_REG at offset 08h", "for_target": True},
        {"id": "F2", "subject": "CTRL_REG", "kind": "address", "value": "0x0C", "page": 1, "quote": "CTRL_REG at offset 0Ch"}]}))
    from flow.doc_crossread import main
    rc = main(["--doc", str(d), "--code", str(CASES / "p1_uartlite_stat_ctrl_swapped/code/tb_uartlite.sv"), "--facts", str(reply), "--topic", "uart", "--json"])
    rec = json.loads(capsys.readouterr().out)
    assert rc == 2 and rec["summary"] == {"disagree": 2} and all(r["doc"]["quote_ok"] for r in rec["rows"])
    rc = main(["--doc", str(d), "--code", str(CASES / "f1_uartlite/code/tb_uartlite.sv"), "--facts", str(reply), "--topic", "uart"])
    out = capsys.readouterr().out
    assert rc == 0 and "2 agree" in out and "limits:" in out
    assert "raw_replies" not in rec and "raw_replies" not in rec["reader"]          # the record keeps hashes, never prompt text or replies


def test_the_agent_tool_is_registered_and_read_only() -> None:
    from agent.core import registry
    from agent.core import tools as _t  # noqa: F401
    t = registry.TOOLS["doc_crossread"]
    assert not t.hardware and "doc_crossread" not in registry.CODE_RUNNING_TOOLS
    assert set(t.input_schema["properties"]) >= {"doc", "code", "facts_file"} and t.input_schema["additionalProperties"] is False
