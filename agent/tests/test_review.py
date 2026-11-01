"""Review pages are self-contained and carry the flow's own numbers (05b)."""

import json
import re

from agent.graph.review import write_index, write_page


def test_page_shows_gate_numbers_and_is_self_contained(tmp_path):
    d = tmp_path / "designs" / "x"
    (d / "build" / "base").mkdir(parents=True)
    (d / "spec.yaml").write_text("title: X\ntop: x_top\nports: []\nopen_questions: []\n")
    (d / "ARCHITECTURE.md").write_text("# X\n\n## Block diagram\n\n```\n[uart] -> [core] -> [leds]\n```\n")
    (d / "build" / "base" / "gates.json").write_text(json.dumps({
        "timing": {"wns_ns": 3.911, "tns_ns": 0.0, "whs_ns": 0.106, "ths_ns": 0.0},
        "utilization": {"lut": 495, "lut_available": 63400, "ff": 488, "ff_available": 126800},
        "power": {"total_w": 0.15, "confidence": "Low"}, "power_environment": {"junction_c": 42.7, "ambient_c": 40.0}}))
    vcd = tmp_path / "w.vcd"
    vcd.write_text("$var reg 1 ! clk $end\n$enddefinitions $end\n#0\n0!\n#5\n1!\n#10\n0!\n")
    p = write_page(d, 6, "timing-closure", {"gates": [["setup", True, ""]], "vcd": vcd,
                                            "approval": {"decision": "approve", "by": "human", "note": "ok"}})
    h = p.read_text()
    for s in ("3.911", "495 of 63400", "0.15", "42.7", "[uart] -&gt; [core]", "polyline", "prefers-color-scheme:dark"):
        assert s in h, s
    assert not re.search(r'(src|href)="https?:', h)
    i = write_index(d, [{"n": 6, "stage": "timing-closure", "page": str(p), "passed": True,
                         "approval": {"decision": "approve", "by": "human"}}])
    assert "06_timing-closure.html" in i.read_text() and "human" in i.read_text()
