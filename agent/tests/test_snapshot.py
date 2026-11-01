"""Rewind restores the exact files and the Vivado checkpoints (hash check) (05b)."""

from agent.graph.snapshot import Snapshots, manifest


def test_rewind_restores_exact_files_and_dcp(tmp_path):
    d = tmp_path / "design"
    (d / "rtl").mkdir(parents=True)
    (d / "build" / "base").mkdir(parents=True)
    (d / "spec.yaml").write_text("name: t\n")
    snaps = Snapshots(tmp_path / "run", d)
    s0 = snaps.take(0, "clarify")
    (d / "rtl" / "top.sv").write_text("module top; endmodule\n")
    (d / "build" / "base" / "post_synth.dcp").write_bytes(b"DCP-A")
    (d / "build" / "base" / "gates.json").write_text("{}")
    s2 = snaps.take(2, "rtl-design-creation", checkpoint_id="cp-2")
    (d / "rtl" / "top.sv").write_text("module top(input a); endmodule\n")
    (d / "rtl" / "extra.sv").write_text("// later\n")
    (d / "build" / "base" / "post_synth.dcp").write_bytes(b"DCP-B")
    (d / "build" / "base" / "post_route.dcp").write_bytes(b"ROUTE")
    snaps.take(6, "timing-closure")
    r = snaps.rewind(2)
    assert r["verified"] and r["checkpoint_id"] == "cp-2"
    assert manifest(d) == s2["manifest"]
    assert (d / "build" / "base" / "post_synth.dcp").read_bytes() == b"DCP-A"
    assert not (d / "build" / "base" / "post_route.dcp").exists() and not (d / "rtl" / "extra.sv").exists()
    r0 = snaps.rewind(0)
    assert r0["verified"] and manifest(d) == s0["manifest"] and not (d / "rtl" / "top.sv").exists()
