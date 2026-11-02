"""The upgraded review pages (brief 05d, addition 5): RTL diff, buses in hex, constraints traced to the inventory,
traceability and standards tables, in a page with no external script."""

import re
from pathlib import Path

from agent.graph import review as rv

ROOT = Path(__file__).resolve().parents[2]
T1 = ROOT / "designs" / "t1_dimmer_counter"


def test_sv_highlight_marks_keywords_numbers_and_comments_and_escapes():
    h = rv.sv_highlight("always_ff @(posedge clk) q <= 8'hFF; // a < b\n")
    assert '<span class="k">always_ff</span>' in h and '<span class="n">8&#x27;hFF</span>' in h
    assert '<span class="c">// a &lt; b</span>' in h and "<script" not in h


def test_diff_html_marks_added_and_removed_lines():
    d = "diff --git a/rtl/a.sv b/rtl/a.sv\n--- a/rtl/a.sv\n+++ b/rtl/a.sv\n@@ -1,2 +1,2 @@\n-assign x = 1;\n+assign x = 2;\n keep\n"
    h = rv.diff_html([{"path": "rtl/a.sv", "diff": d}])
    assert 'class="del"' in h and 'class="add"' in h and "rtl/a.sv" in h and "diff --git" not in h
    assert "No change" in rv.diff_html([])


VCD = """$timescale 1ns $end
$scope module t $end
$var wire 1 ! clk $end
$var wire 8 " count [7:0] $end
$upscope $end
$enddefinitions $end
#0
0!
b00000000 "
#10
1!
#20
0!
b10101111 "
#40
1!
b10110000 "
#80
"""


def test_buses_are_shown_as_hex_values(tmp_path):
    f = tmp_path / "w.vcd"
    f.write_text(VCD)
    sig, last = rv.parse_vcd(VCD)
    assert sig['"']["width"] == 8 and sig['"']["changes"][1] == (20, "10101111") and last == 80
    svg = rv.vcd_svg(f)
    assert ">af<" in svg and ">b0<" in svg and "count[7:0]" in svg and "1 of them buses" in svg


def test_constraints_are_shown_in_full_with_each_pin_traced_to_the_inventory(tmp_path):
    (tmp_path / "design.xdc").write_text((T1 / "design.xdc").read_text())
    h = rv.constraints_html(tmp_path, ROOT / "boards" / "nexys_a7_100t")
    assert "create_clock" in h or "PACKAGE_PIN E3" in h
    row = re.search(r"<td>BTNC</td><td>N17</td><td>([^<]*)</td><td>([^<]*)</td>", h)
    assert row and "master XDC port BTNC" in row.group(1) and row.group(2).startswith("buttons")
    assert "SW[3]" in h and "not in the master XDC" not in h


def test_traceability_and_standards_tables():
    v = {"traceability": [{"requirement": "R1", "method": "simulation", "artefact": "t.x", "result": "pass", "detail": "ok"},
                          {"requirement": "R2", "method": "hardware", "artefact": "uart_tests", "result": "pending",
                           "detail": "no bring-up result"}]}
    h = rv.traceability_html(v)
    assert "PASS" in h and "not run" in h and "uart_tests" in h
    std = {"rules": [{"id": "STD-CLK-01", "title": "no gated clocks", "status": "fail", "stage": "rtl",
                      "findings": [{"file": "rtl/a.sv", "line": 3, "message": "gclk"}]},
                     {"id": "STD-REV-01", "title": "x", "status": "review_only", "stage": "review", "findings": []}]}
    h = rv.standards_html(std)
    assert "FAIL" in h and "rtl/a.sv:3" in h and "review only" in h


def test_page_has_no_external_script_and_both_themes():
    page = rv._page("t", "<p>x</p>")
    assert "<script" not in page and "src=" not in page and "prefers-color-scheme:dark" in page
