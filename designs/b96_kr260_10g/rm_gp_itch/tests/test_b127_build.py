"""The build file of rm_gp_itch against what the design says it is (brief 127): every source exists, the variant's three files replace the base's, brief 110's blocks are the unchanged ones, the generics are
the ones the core needs, and the architecture lists the two new crossings."""
from __future__ import annotations

from pathlib import Path

import yaml

DESIGN = Path(__file__).parent.parent
ROOT = DESIGN.parents[2]
B = yaml.safe_load((DESIGN / "build.yaml").read_text())
A = yaml.safe_load((DESIGN / "architecture.yaml").read_text())


def test_every_source_exists_and_the_variant_replaces_three_base_files() -> None:
    srcs = B["sources"]
    assert all((ROOT / s).is_file() for s in srcs), [s for s in srcs if not (ROOT / s).is_file()]
    names = [Path(s).name for s in srcs]
    assert len(names) == len(set(names)), "a module file listed twice"
    for n in ("b96_core.sv", "rx_path.sv", "tx_path.sv"):
        assert f"designs/b96_kr260_10g/rm_gp_itch/rtl/{n}" in srcs and f"designs/b96_kr260_10g/rtl/{n}" not in srcs
    assert "designs/b96_kr260_10g/rtl/rx_path_legacy.sv" not in srcs


def test_brief_110_blocks_are_the_unchanged_ones() -> None:
    for n in ("mold_rx", "itch_dec", "book_core", "risk_glue", "ouch_enter", "itch_pkg"):
        assert f"designs/b110_itch_ouch/rtl/{n}.sv" in B["sources"]
    assert not any("b119" in s for s in B["sources"]), "tcp_fast is a hook, not in the build until PR #245 is merged"


def test_generics_and_top() -> None:
    g = B["generics"]
    assert B["top"] == "kr260_10g_top" and B["part"] == "xck26-sfvc784-2LV-c"
    assert g["RATE_MATCH"] == "1'b1" and g["RM_OWN"] == "1'b1" and g["TRADE"] == "1'b0"


def test_architecture_lists_the_new_crossings_and_blocks() -> None:
    sig = " ".join(c["signal"] for c in A["crossings"])
    assert "CFG2" in sig and "STAT2" in sig
    assert {"udp_strip", "itch_top", "order_seg", "tx_mux", "itch_path"} <= {b["name"] for b in A["blocks"]}
    assert not any("RATE_MATCH = 0 only" in c["signal"] for c in A["crossings"])
