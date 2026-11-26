"""Brief 241: the advisory `dma_coherency` check and the DMA intake questions."""
from __future__ import annotations

from pathlib import Path

import yaml

from flow import checks as C


def _design(tmp_path: Path, spec: dict, rtl: str = "") -> Path:
    d = tmp_path / "dsn"
    (d / "rtl").mkdir(parents=True)
    (d / "spec.yaml").write_text(yaml.safe_dump({"name": "dsn", **spec}))
    if rtl:
        (d / "rtl" / "top.sv").write_text(rtl)
    return d


def _run(d: Path) -> dict:
    return C.run(d, names=["dma_coherency"], scope="rtl", level="detail")


def _codes(r: dict) -> list[str]:
    return [f["code"] for f in r["checks"][0].get("findings", [])]


def test_hp_port_without_contract_is_flagged(tmp_path):
    d = _design(tmp_path, {"dma": {"ps_memory_port": "S_AXI_HP0"}})
    r = _run(d)
    assert _codes(r) == ["DMA-COH-01"]
    assert r["checks"][0]["status"] == "pass"            # advisory: never a failure


def test_port_found_in_the_sources(tmp_path):
    d = _design(tmp_path, {}, "module top; wire S_AXI_HP1_awvalid; endmodule\n")     # no build.yaml: the design's own rtl/ tree is the source list
    assert _codes(_run(d)) == ["DMA-COH-01"]


def test_contract_declared_is_quiet(tmp_path):
    d = _design(tmp_path, {"dma": {"ps_memory_port": ["S_AXI_HP0_FPD"], "cache_contract": "software_flush_invalidate"}})
    assert _codes(_run(d)) == []


def test_coherent_port_needs_no_contract(tmp_path):
    d = _design(tmp_path, {"dma": {"ps_memory_port": "S_AXI_HPC0_FPD"}})
    assert _codes(_run(d)) == []


def test_hardware_coherent_on_a_non_coherent_port(tmp_path):
    d = _design(tmp_path, {"dma": {"ps_memory_port": "S_AXI_HP2", "cache_contract": "hardware_coherent"}})
    assert _codes(_run(d)) == ["DMA-COH-02"]


def test_does_not_apply_without_a_ps_port(tmp_path):
    d = _design(tmp_path, {}, "module top; endmodule\n")
    r = C.run(d, names="all", scope="rtl", level="summary")
    assert "dma_coherency" in r["skipped"], r.keys()
