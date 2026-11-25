"""The design package (brief 174): manifest and hashes, ingest of a small synthetic package, conflicts, the existing-design gates."""

import shutil
from pathlib import Path

import yaml

from flow import package as K

BOM = ("Item Number,Quantity,Part Reference,Manufacturers,Manufacturers Part Number,Description\n"
       "1,2,U1 U2,TI,DP83867CSRGZT,IC PHY Ethernet Single 10/100/1000 Mbps\n"
       "2,1,U3,SiTime,SiT1602BI-25.000,Osc XO 25MHz 1.8V CMOS\n"
       "3,4,R1 R2 R3 R4,Vishay,CRCW040222R0,Res 22R 1% 0402\n")
XDC = ("set_property -dict { PACKAGE_PIN E3 IOSTANDARD LVCMOS33 } [get_ports { clk }];\n"
       "create_clock -period 10.000 -name sys [get_ports { clk }];\n"
       "set_property PACKAGE_PIN H17 [get_ports {led0}]\nset_property -dict { PACKAGE_PIN H17 IOSTANDARD LVCMOS33 } [get_ports led0];\n")


def make_pkg(tmp: Path) -> Path:
    p = tmp / "pkg"
    (p / "board").mkdir(parents=True)
    (p / "spec.md").write_text("# spec\nA board with one PHY.\n")
    (p / "board" / "bom.csv").write_text(BOM)
    (p / "board" / "pins.xdc").write_text(XDC)
    (p / "package.yaml").write_text("name: pkg\npart: xc7a100tcsg324-1\nboard_fixed: true\n")
    return p


def test_manifest_hashes_and_gitignore(tmp_path):
    p = make_pkg(tmp_path)
    m = K.init(p)
    kinds = {e["path"]: e["kind"] for e in m["files"]}
    assert kinds["board/bom.csv"] == "bom" and kinds["board/pins.xdc"] == "xdc" and kinds["spec.md"] == "spec"
    assert K.verify(p) == []
    (p / "board" / "bom.csv").write_text(BOM + "x\n")
    assert K.verify(p) == ["hash changed: board/bom.csv"]
    K.init(p)
    assert K.gitignore(p) == ["board/bom.csv", "board/pins.xdc"]         # new files are private until marked public
    assert "/board/bom.csv" in (p / ".gitignore").read_text()
    (p / "board" / "late.txt").write_text("x")
    assert "not in the manifest: board/late.txt" in K.verify(p)


def test_ingest_facts_carry_sources_and_series_r(tmp_path):
    p = make_pkg(tmp_path)
    K.init(p)
    doc = K.ingest(p)
    ix = K.facts_index(doc)
    phy = ix["chip.phy.DP83867"][0]
    assert phy["value"]["mpn"] == "DP83867CSRGZT" and phy["source"]["file"] == "board/bom.csv"
    assert len(phy["source"]["sha256"]) == 64 and phy["source"]["locator"]
    assert ix["pin.clk"][0]["value"] == {"pin": "E3", "iostandard": "LVCMOS33"}
    assert ix["clock.clk"][0]["value"]["mhz"] == 100.0
    assert ix["bom.series_resistors"][0]["value"]["22R"]["count"] == 4
    assert ix["oscillator.SiT1602BI-25.000"][0]["value"]["mhz"] == 25.0
    assert doc["conflicts"] == []
    assert (p / "board_facts.yaml").exists()


def test_two_sources_disagreeing_are_a_conflict_not_resolved(tmp_path):
    p = make_pkg(tmp_path)
    (p / "board" / "other.xdc").write_text("set_property -dict { PACKAGE_PIN D4 IOSTANDARD LVCMOS33 } [get_ports { clk }];\n")
    K.init(p)
    doc = K.ingest(p)
    c = [x for x in doc["conflicts"] if x["key"] == "pin.clk"]
    assert len(c) == 1 and {v["value"]["pin"] for v in c[0]["values"]} == {"E3", "D4"}
    assert len([r for r in doc["facts"] if r["key"] == "pin.clk"]) == 2     # both kept


def test_board_yaml_phy_error_is_found_even_in_a_comment(tmp_path):
    p = make_pkg(tmp_path)
    K.init(p)
    doc = K.ingest(p)
    text = "name: x\npart: xc7a100tcsg324-1\npl_ethernet:   # Marvell M88E1111 PHYs\n  port_a: {}\n"
    r = K.check_board(doc, yaml.safe_load(text), None, text)
    assert [c["board_yaml"] for c in r["conflicts"]] == ["88E1111"]
    ok = K.check_board(doc, {"part": "xc7a100tcsg324-1", "pl_ethernet": {"phy_part": "DP83867"}}, None, "")
    assert ok["conflicts"] == []
    bad_part = K.check_board(doc, {"part": "xc7a35tcpg236-1"}, None, "")
    assert bad_part["conflicts"][0]["field"] == "part"


def test_bom_xls_without_xlrd_is_reported_not_fatal(tmp_path):
    p = make_pkg(tmp_path)
    (p / "board" / "x_bom.xls").write_bytes(b"\xd0\xcf\x11\xe0")
    K.init(p)
    doc = K.ingest(p)
    try:
        import xlrd  # noqa: F401
    except ImportError:
        assert any(n["file"] == "board/x_bom.xls" for n in doc["not_read"])


def test_allegro_script_is_written_not_run(tmp_path):
    p = make_pkg(tmp_path)
    (p / "board" / "b.brd").write_bytes(b"x")
    K.init(p)
    s = K.allegro_script(p)
    assert s and "DUMPER" in s.read_text() and "owner" in s.read_text().lower()


def test_allegro_dump_lengths_become_facts(tmp_path):
    p = make_pkg(tmp_path)
    d = p / "board" / "allegro_dump"
    d.mkdir()
    (d / "nets.csv").write_text("net,layer,n_segments,n_arcs,length_mm,length_mil,min_width_mil,max_width_mil\n"
                                "HPA03P,c01,2,0,1,1000.0,5,5\nHPA03P,c02,1,0,1,500.5,5,5\nN123,c01,1,0,1,9,5,5\n")
    (p / "package.yaml").write_text("name: pkg\ningest: {net_filter: '^HPA'}\n")
    K.init(p)
    ix = K.facts_index(K.ingest(p))
    assert ix["trace_length_mil.HPA03P"][0]["value"] == 1500.5 and "trace_length_mil.N123" not in ix


# ---- the existing design -------------------------------------------------------------------------------------------

SV_A = "module leaf #(parameter int W = 8) (input logic clk, input logic [W-1:0] d, output logic [W-1:0] q);\n always_ff @(posedge clk) q <= d;\nendmodule\n"
SV_B = "module mid (input logic clk, input logic [7:0] d, output logic [7:0] q);\n  leaf #(.W(8)) u (.clk, .d, .q);\nendmodule\n"
SV_T = "module top (input logic clk, input logic rst, input logic [7:0] d, output logic [7:0] q);\n  mid u_mid (.clk, .d, .q);\nendmodule\n"
RPT = ("    WNS(ns)      TNS(ns)  TNS Failing Endpoints  TNS Total Endpoints      WHS(ns)      THS(ns)  THS Failing Endpoints  THS Total Endpoints\n"
       "    -------      -------  ---------------------  -------------------      -------      -------  ---------------------  -------------------\n"
       "      {w}        0.000                      0                  100        0.050        0.000                      0                  100\n")


def make_existing(tmp: Path) -> Path:
    p = tmp / "ex"
    (p / "existing" / "rtl").mkdir(parents=True)
    (p / "existing" / "reports").mkdir()
    for n, t in (("leaf", SV_A), ("mid", SV_B), ("top", SV_T)):
        (p / "existing" / "rtl" / f"{n}.sv").write_text(t)
    (p / "existing" / "c.xdc").write_text("create_clock -period 8.000 [get_ports clk]\nset_property PACKAGE_PIN A1 [get_ports clk]\n")
    (p / "existing" / "reports" / "timing.rpt").write_text(RPT.format(w="0.500"))
    (p / "existing" / "ip.xci").write_text("<spirit:vendor>xilinx.com</spirit:vendor><spirit:library>ip</spirit:library><spirit:name>fifo_generator</spirit:name><spirit:version>13.2</spirit:version>")
    (p / "existing" / "bd.bd").write_text("{}")
    (p / "package.yaml").write_text("name: ex\nexisting:\n  change: [mid]\n")
    (p / "spec.md").write_text("Change module mid only.\n")
    return p


def test_inventory_and_marks(tmp_path):
    p = make_existing(tmp_path)
    inv = K.write_existing(p)
    assert inv["top"] == "top" and inv["modules"]["top"]["instances"] == [{"module": "mid", "name": "u_mid"}]
    assert inv["modules"]["leaf"]["ports"][1] == {"name": "d", "dir": "input", "width": "[W-1:0]"}
    assert inv["resets"] == ["rst"] and inv["clock_ports"] == ["clk"]
    assert inv["ip"][0]["vlnv"] == "xilinx.com:ip:fifo_generator:13.2"
    assert inv["timing"]["wns"] == 0.5
    assert any(u["file"] == "bd.bd" for u in inv["unreadable"])             # a block design is named as unread
    owned = yaml.safe_load((p / "design.yaml").read_text())["owned"]
    assert "existing/rtl/mid.sv" not in owned and "existing/rtl/leaf.sv" in owned and "existing/c.xdc" in owned


def test_frozen_gates(tmp_path):
    p = make_existing(tmp_path)
    K.write_existing(p)
    ex, w = p / "existing", tmp_path / "work"
    tb = ex / "reports" / "timing.rpt"

    def fresh():
        shutil.rmtree(w, ignore_errors=True)
        shutil.copytree(ex, w)
    fresh()
    (w / "rtl" / "mid.sv").write_text(SV_B.replace("u (", "u2 ("))              # the named module may change
    assert K.frozen_check(p, w) == []
    fresh()
    (w / "rtl" / "leaf.sv").write_text(SV_A + "// touched\n")                    # a frozen file, one comment
    assert K.frozen_check(p, w) == ["frozen file changed: rtl/leaf.sv"]
    fresh()
    (w / "rtl" / "mid.sv").write_text(SV_B.replace("output logic [7:0] q", "output logic [8:0] q"))   # interface of an editable module: allowed
    assert K.frozen_check(p, w) == []
    fresh()
    (w / "rtl" / "mid.sv").write_text(SV_B + "module extra (input logic a); endmodule\n")
    assert K.frozen_check(p, w) == []
    fresh()
    (w / "rtl" / "leaf.sv").unlink()
    assert "frozen file removed: rtl/leaf.sv" in K.frozen_check(p, w)
    fresh()
    after = tmp_path / "after.rpt"
    after.write_text(RPT.format(w="0.200"))
    assert K.frozen_check(p, w, tb, after) == ["timing worse: WNS 0.5 -> 0.2 ns"]
    after.write_text(RPT.format(w="0.700"))
    assert K.frozen_check(p, w, tb, after) == []


def test_frozen_interface_is_checked_apart_from_the_hash(tmp_path):
    """The hash gate already catches a changed frozen file; the interface gate must catch the case where the owned list is shorter
    (a module's file made editable by mistake) and a port is lost."""
    p = make_existing(tmp_path)
    K.write_existing(p)
    d = yaml.safe_load((p / "design.yaml").read_text())
    d["owned"].remove("existing/rtl/leaf.sv")
    (p / "design.yaml").write_text(yaml.safe_dump(d))
    w = tmp_path / "work"
    shutil.copytree(p / "existing", w)
    (w / "rtl" / "leaf.sv").write_text(SV_A.replace("output logic [W-1:0] q", "output logic [W:0] q"))
    assert K.frozen_check(p, w) == ["frozen module leaf: interface changed"]


def test_change_not_named_in_spec_is_a_conflict(tmp_path):
    p = make_existing(tmp_path)
    (p / "spec.md").write_text("Change something else.\n")
    K.init(p)
    doc = K.ingest(p)
    assert any(c["kind"] == "spec_vs_manifest" for c in doc["conflicts"])


def test_encrypted_hdl_is_reported_unreadable(tmp_path):
    p = make_existing(tmp_path)
    (p / "existing" / "rtl" / "enc.sv").write_text("`pragma protect begin_protected\nxx\n")
    inv = K.write_existing(p)
    assert any("encrypted" in u["why"] for u in inv["unreadable"])


def test_offchip_hints_from_dump(tmp_path):
    p = make_pkg(tmp_path)
    d = p / "board" / "allegro_dump"
    d.mkdir()
    (d / "nets.csv").write_text("net,layer,n_segments,n_arcs,length_mm,length_mil,min_width_mil,max_width_mil\n"
                                "HPA03P,c01,2,0,1,7000.0,5,5\nHPA09_N_NC,c01,1,0,1,20,5,5\nHPA_CLK0P_CLK_R,c01,1,0,1,90,5,5\n")
    (p / "package.yaml").write_text("name: pkg\nboard_fixed: true\ningest: {net_filter: '^HPA'}\n")
    K.init(p)
    h = K.offchip_hints(K.ingest(p))
    assert h["board_fixed"] is True and h["net_families"]["HPA"]["lengths_in"] == {"HPA03P": 7.0}
