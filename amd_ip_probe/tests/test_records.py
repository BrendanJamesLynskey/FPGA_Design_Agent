"""Brief 69: the committed records, the summary table and the agent's notes agree (no simulator needed).

The records are made by `amd_ip_probe/run_probe.py` under a local Vivado 2026.1 and cannot be re-made in CI; these tests
fail when a record is missing or incomplete, when a cell of the summary says something its record does not, when the
table in the results README is out of date, or when a note for the agent names an IP that was not measured.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "amd_ip_probe"))
sys.path.insert(0, str(ROOT))
import ips  # noqa: E402
import summarise  # noqa: E402
import summary_spec as S  # noqa: E402
from flow import amd_ip_notes  # noqa: E402

RES = ROOT / "results" / "69_amd_ip_conventions"


def test_every_bench_has_a_record_and_a_column():
    assert sorted(S.IPS) == sorted(ips.IPS), "summary columns and benches differ"
    for ip, e in ips.IPS.items():
        assert (ROOT / "amd_ip_probe" / "tb" / f"{e['tb']}.sv").exists()
        assert (RES / f"{ip}.json").exists(), f"no record for {ip}"


def test_records_are_complete_vivado_2026_1_and_finished():
    for ip in S.IPS:
        r = json.loads((RES / f"{ip}.json").read_text())
        assert r["meta"]["vivado"] == "2026.1", ip
        assert r["errors"] == [], ip
        assert r["probes"][-1]["probe"] == "done", f"{ip}: the bench did not reach its last line"
        assert not any(p["probe"] == "timeout" for p in r["probes"])
        assert r["meta"]["requires_license"] == "0", f"{ip}: licence text {r['meta']['requires_license']!r}"
        bench = ROOT / r["bench"]
        import hashlib
        assert hashlib.sha256(bench.read_bytes()).hexdigest()[:16] == r["bench_sha256"], f"{ip}: the bench changed since the record was made"


def test_protocol_checker_saw_no_rule_broken():
    for ip in S.IPS:
        r = json.loads((RES / f"{ip}.json").read_text())
        for p in r["probes"]:
            assert p["values"].get("chk", "0x000") == "0x000", f"{ip}/{p['probe']}: checker mask {p['values']['chk']}"


def test_summary_cells_match_their_records():
    assert summarise.problems() == []


def test_readme_table_is_current():
    assert summarise.readme_ok(), "run: python3 amd_ip_probe/summarise.py --write"


def test_notes_cover_each_ip_and_scan_finds_them():
    assert set(S.NOTES) == set(S.IP_NAME.values())
    text = "create_ip -name axi_gpio -vendor xilinx.com -library ip -module_name g\ncreate_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 ic\n"
    assert amd_ip_notes.ips_in(text) == {"axi_gpio", "smartconnect"}
    assert amd_ip_notes.ips_in("create_ip -vendor xilinx.com -name axi_dma -module_name d") == {"axi_dma"}
    assert amd_ip_notes.ips_in("xilinx.com:ip:axi_bram_ctrl:4.1") == set()
    rep = amd_ip_notes.notes_for({"axi_dma"})
    assert rep["axi_dma"]["record"].endswith("dma.json")
    assert any("eight times" in n for n in rep["axi_dma"]["notes"])


def test_scan_a_design_folder(tmp_path):
    (tmp_path / "ip.tcl").write_text("create_ip -name axi_uartlite -vendor xilinx.com -module_name u\n")
    (tmp_path / "x_regs.sv").write_text("module x_regs; endmodule\n")
    rep = amd_ip_notes.scan([tmp_path])
    assert list(rep["ips"]) == ["axi_uartlite"] and rep["mixes_generated_blocks"]
    assert "pops" in amd_ip_notes.render(rep)
