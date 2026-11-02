"""Resource sanity gate, architecture schema and approval record (brief 05d)."""

import shutil
from pathlib import Path

import pytest
import yaml

from flow import architecture as ar
from flow import gates

DATA = Path(__file__).parent / "data"
ARCH = {"schema": ar.SCHEMA, "blocks": [{"name": "t", "function": "x"}], "interfaces": [],
        "clock_domains": [{"name": "sys", "clock": "CLK100MHZ"}], "crossings": [],
        "predicted_resources": {"lut": [300, 700], "ff": [300, 700], "bram_tile": 0, "dsp": 0}}


def synth_dir(tmp_path, arch):
    d = tmp_path / "design"
    b = d / "build" / "base"
    b.mkdir(parents=True)
    for n in ("check_timing_synth", "drc_synth", "methodology_synth", "qor_assessment_synth", "timing_summary_synth",
              "utilization_synth"):
        shutil.copy(DATA / f"good_{n}.rpt", b / f"{n}.rpt")
    if arch is not None:
        (d / "architecture.yaml").write_text(yaml.safe_dump(arch))
    return b


def test_in_range_passes_and_gate_is_in_post_synth(tmp_path):
    b = synth_dir(tmp_path, ARCH)
    u = gates.parse_utilization((b / "utilization_synth.rpt").read_text())
    arch = {**ARCH, "predicted_resources": {"lut": [u["lut"], u["lut"]], "ff": [u["ff"], u["ff"]], "bram_tile": 0, "dsp": 0}}
    (b.parent.parent / "architecture.yaml").write_text(yaml.safe_dump(arch))
    st = gates.evaluate(b)["stages"]["post_synth"]
    assert st["gates"]["post_synth_resources_in_range"] is True and st["resource_sanity"]["pass"]


def test_far_outside_the_range_fails_with_raw_numbers(tmp_path):
    b = synth_dir(tmp_path, {**ARCH, "predicted_resources": {"lut": [10, 20], "ff": [10, 20], "bram_tile": 0, "dsp": 0}})
    st = gates.evaluate(b)["stages"]["post_synth"]
    assert st["gates"]["post_synth_resources_in_range"] is False
    rows = st["resource_sanity"]["resources"]
    assert rows["lut"]["direction"] == "above" and rows["lut"]["pass"] is False
    assert any("lut used" in f for f in ar.resource_failures(st["resource_sanity"]))


def test_factor_is_read_from_gates_yaml_and_overridable():
    util = {"lut": 150, "ff": 100, "bram_tile": 0, "dsp": 0}
    arch = {"predicted_resources": {"lut": [50, 100], "ff": [50, 100], "bram_tile": 0, "dsp": 0}}
    assert ar.gates_config()["resource_sanity"]["factor"] == 2.0
    assert ar.resource_check(util, arch)["pass"]                 # 150 <= 100 x 2
    assert not ar.resource_check(util, arch, factor=1.2)["pass"]
    assert not ar.resource_check({**util, "dsp": 1}, arch)["pass"]            # a predicted 0 allows 0 only
    assert ar.resource_check({**util, "lut": 30}, arch)["resources"]["lut"]["pass"]    # 50 / 2 = 25 <= 30
    assert ar.resource_check({**util, "lut": 20}, arch)["resources"]["lut"]["direction"] == "below"


def test_no_architecture_means_no_gate(tmp_path):
    b = synth_dir(tmp_path, None)
    assert "post_synth_resources_in_range" not in gates.evaluate(b)["stages"]["post_synth"]["gates"]


def test_schema_errors_name_the_key():
    assert ar.check_architecture(ARCH) == []
    bad = {**ARCH, "predicted_resources": {"lut": [5, 1]}, "crossings": [{"from": "x", "to": "sys", "primitive": "magic"}]}
    errs = "; ".join(ar.check_architecture(bad))
    assert "predicted_resources.lut" in errs and "predicted_resources has no 'ff'" in errs and "magic" in errs


def test_approval_is_invalidated_by_a_later_edit(tmp_path):
    (tmp_path / "architecture.yaml").write_text(yaml.safe_dump(ARCH))
    (tmp_path / "ARCHITECTURE.md").write_text("# a\n## Block diagram\n```\nx\n```\n")
    assert ar.approval_status(tmp_path)[0] is False
    ar.write_approval(tmp_path, "owner", "agent")
    assert ar.approval_status(tmp_path) == (True, "")
    (tmp_path / "ARCHITECTURE.md").write_text("changed")
    ok, why = ar.approval_status(tmp_path)
    assert not ok and "changed after" in why
