"""Brief 54: the build manifest and build ID, the bitstream reader and comparison, the release bundle and its checker,
and the build-ID checks of the board flow. No Vivado and no board: synthetic .bit files are built here packet by packet
(AMD UG470 packet format), and the committed sample bundle (a real 2026.1 build) is checked as it stands."""

from __future__ import annotations

import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from flow import bitstream, manifest, program, release

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "results" / "54_reproducible" / "sample_bundle"


# ---- synthetic bitstreams ------------------------------------------------------------------------------------------
def _t1(reg: int, words: list[int]) -> list[int]:
    return [0x30000000 | (reg << 13) | len(words), *words]


def make_bit(usr_access: int | None = 0x1234ABCD, frames: list[int] | None = None, date: str = "2026/11/12",
             time: str = "03:00:00") -> bytes:
    """A small but well-formed .bit: header, sync, RCRC, a few register writes, frame data, the CRC check, DESYNC."""
    frames = frames if frames is not None else [0x0, 0x1, 0xDEADBEEF] * 101
    words: list[int] = [0xFFFFFFFF] * 8 + [0x000000BB, 0x11220044, 0xFFFFFFFF, 0xFFFFFFFF, bitstream.SYNC, 0x20000000]
    crc = 0
    body: list[tuple[int, list[int]]] = [(4, [0x7])]                       # CMD RCRC
    body += [(0x09, [0x02003FE5]), (0x0C, [0x03631093]), (0x01, [0x0]), (4, [0x1])]   # COR0, IDCODE, FAR, WCFG
    for reg, data in body:
        words += _t1(reg, data)
        crc = 0 if (reg == 4 and data == [0x7]) else crc
        if not (reg == 4 and data == [0x7]):
            for d in data:
                crc = bitstream.crc_step(crc, reg, d)
    # frame data: a Type 1 FDRI header with count 0, then a Type 2 packet
    words += [0x30000000 | (2 << 13), 0x50000000 | len(frames), *frames]
    for d in frames:
        crc = bitstream.crc_step(crc, 2, d)
    if usr_access is not None:
        words += _t1(0x0D, [usr_access])
        crc = bitstream.crc_step(crc, 0x0D, usr_access)
    words += _t1(0x00, [crc])
    words += _t1(4, [0xD]) + [0x20000000] * 4                            # DESYNC, NOOPs
    data = struct.pack(f">{len(words)}I", *words)

    def field(k: str, text: str) -> bytes:
        b = text.encode() + b"\x00"
        return k.encode() + struct.pack(">H", len(b)) + b

    hdr = b"\x00\x09\x0f\xf0\x0f\xf0\x0f\xf0\x0f\xf0\x00\x00\x01"
    hdr += field("a", "top;COMPRESS=TRUE;UserID=0XFFFFFFFF;Version=2026.1") + field("b", "7a100tcsg324")
    hdr += field("c", date) + field("d", time) + b"e" + struct.pack(">I", len(data))
    return hdr + data


def test_reader_finds_usr_access_and_checks_the_crc(tmp_path: Path) -> None:
    f = tmp_path / "a.bit"
    f.write_bytes(make_bit(0x1234ABCD))
    i = bitstream.info(f)
    assert i["usr_access"] == "1234ABCD"
    assert i["header"]["b"] == "7a100tcsg324" and i["header"]["c"] == "2026/11/12"
    assert i["crc_checks"] and i["crc_all_match"]
    f.write_bytes(make_bit(None))
    assert bitstream.usr_access(f) is None


def test_crc_check_catches_a_changed_word(tmp_path: Path) -> None:
    raw = bytearray(make_bit())
    i = raw.find(struct.pack(">I", 0xDEADBEEF))
    raw[i + 3] ^= 0x01                                   # one frame bit flipped, CRC word left as it was
    f = tmp_path / "bad.bit"
    f.write_bytes(bytes(raw))
    assert not bitstream.info(f)["crc_all_match"]


def test_diff_names_every_difference(tmp_path: Path) -> None:
    a, b, c, d = (tmp_path / f"{n}.bit" for n in "abcd")
    a.write_bytes(make_bit(0x11111111))
    b.write_bytes(make_bit(0x11111111))
    assert bitstream.diff(a, b)["identical"]
    c.write_bytes(make_bit(0x22222222, time="04:05:06"))
    r = bitstream.diff(a, c)
    assert not r["identical"] and r["same_packet_sequence"]
    assert r["explained"]["kinds"] == ["crc", "header-time", "usr-access"]
    assert r["explained"]["only_documented"]
    fr = [0x0, 0x1, 0xDEADBEEF] * 101
    fr[150] ^= 0x4
    d.write_bytes(make_bit(0x11111111, frames=fr))
    r = bitstream.diff(a, d)
    assert "register-FDRI" in r["explained"]["kinds"] and not r["explained"]["only_documented"]
    fd = next(x for x in r["register_writes"] if x["reg"] == "FDRI")
    assert fd["first_words"] == [150] and fd["first_frames"] == [1]


def test_not_a_bit_file(tmp_path: Path) -> None:
    f = tmp_path / "x.bit"
    f.write_bytes(b"hello")
    with pytest.raises(bitstream.BitError):
        bitstream.read(f)


# ---- manifest and build ID ---------------------------------------------------------------------------------------
def _show(root: Path, design: str = "designs/t1_dimmer_counter", threads: int = 4, variant: str = "base") -> dict:
    r = subprocess.run([sys.executable, str(root / "flow" / "manifest.py"), "show", design, "--threads", str(threads),
                        "--variant", variant, "--vivado-version", "2026.1"],
                       cwd=root, capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def _copy_tree(dst: Path) -> Path:
    """The parts of the repo a T1 build reads, copied to another directory (no git there)."""
    for d in ("flow", "shell", "boards", "designs/t1_dimmer_counter", "knowledge"):
        shutil.copytree(ROOT / d, dst / d, ignore=shutil.ignore_patterns("build", "__pycache__", "sim_build", "tests"))
    (dst / "designs" / "__init__.py").write_text("")
    return dst


def test_manifest_has_the_keys_brief_53_reads() -> None:
    m = _show(ROOT)
    for k in ("inputs", "tools", "kb_pin", "flow"):
        assert k in m
    assert all(len(h) == 64 for h in m["inputs"].values())
    assert m["tools"]["vivado"] == "2026.1"
    assert set(m["flow"]) >= {"commit", "dirty"}
    assert {"rtl", "xdc", "tcl", "build_yaml", "flow_py"} <= set(m["input_roles"].values())
    assert "flow/build.tcl" in m["inputs"] and "flow/program.tcl" not in m["inputs"]   # board-side Tcl is not an input
    assert m["settings"]["threads"] == 4 and m["settings"]["directives"]["place_design"] == "Default"
    assert len(m["build_id"]) == 8 and manifest.build_id_of(m) == (m["build_id"], m["build_id_sha256"])
    assert not any("$ROOT" not in l and str(ROOT) in l for l in m["inputs_tcl"])           # no absolute paths hashed


def test_build_id_is_the_same_in_another_directory_and_changes_with_one_line(tmp_path: Path) -> None:
    here = _show(ROOT)
    other = _copy_tree(tmp_path / "clone")
    there = _show(other)
    assert there["build_id"] == here["build_id"], "the build ID depends on where the tree is"
    assert there["flow"]["commit"] is None                     # not a git checkout: recorded, never hashed
    # one source line changed: the input hash, the stamp and the build ID all change
    rtl = other / "designs" / "t1_dimmer_counter" / "rtl" / "dimmer_counter.sv"
    rtl.write_text(rtl.read_text() + "\n// brief 54 mutation\n")
    mut = _show(other)
    assert mut["build_id"] != here["build_id"]
    key = "designs/t1_dimmer_counter/rtl/dimmer_counter.sv"
    assert mut["inputs"][key] != here["inputs"][key]
    # an option that changes results changes it too; the variant is part of it
    assert _show(ROOT, threads=2)["build_id"] != here["build_id"]
    assert _show(ROOT, variant="ila")["build_id"] != here["build_id"]


def test_provenance_is_recorded_but_not_hashed() -> None:
    m = _show(ROOT)
    m2 = json.loads(json.dumps(m))
    m2["flow"] = {"commit": "0" * 12, "dirty": True}
    m2["kb_pin"] = "deadbee"
    m2["tools"]["python"] = "0.0"
    m2["created"] = "never"
    assert manifest.build_id_of(m2)[0] == m["build_id"]
    m2["settings"]["switches"]["FDA_INCREMENTAL"] = "1"
    assert manifest.build_id_of(m2)[0] != m["build_id"]


def test_check_catches_a_wrong_build_id_and_bitstream(tmp_path: Path) -> None:
    m = _show(ROOT)
    assert manifest.check(m) == []
    f = tmp_path / "x.bit"
    f.write_bytes(make_bit(int(m["build_id"], 16)))
    assert manifest.check(m, f) == []
    f.write_bytes(make_bit(0x0BADF00D))
    assert any("USR_ACCESS" in e for e in manifest.check(m, f))
    bad = dict(m, build_id="00000000")
    assert any("not the hash" in e for e in manifest.check(bad))


def test_every_committed_design_has_a_manifest() -> None:
    """The CI job's first half: a manifest can be computed for every design with a build.yaml, twice, identically."""
    for d in sorted((ROOT / "designs").glob("*/build.yaml")):
        a = _show(ROOT, f"designs/{d.parent.name}")
        b = _show(ROOT, f"designs/{d.parent.name}")
        assert a["build_id"] == b["build_id"], d.parent.name


def test_runner_and_build_tcl_carry_the_build_id() -> None:
    sh = (ROOT / "flow" / "run_vivado.sh").read_text()
    assert sh.index("manifest.py\" pre") < sh.index("build_cache.py\"")      # the flow key covers the build ID
    assert "manifest.py\" post" in sh
    tcl = (ROOT / "flow" / "build.tcl").read_text()
    assert tcl.index("BITSTREAM.CONFIG.USR_ACCESS") < tcl.index("write_bitstream -force")
    from flow import build_cache
    assert not any(s.startswith("set build_id") for s in build_cache.SKIP_LINES)


# ---- release bundle -----------------------------------------------------------------------------------------------
def _fake_build(tmp_path: Path, dirty: bool = False) -> Path:
    """A design folder whose build/base looks like a finished run: manifest (consistent), gates, reports, bitstream."""
    design = tmp_path / "designs" / "t1_dimmer_counter"
    bdir = design / "build" / "base"
    bdir.mkdir(parents=True)
    m = _show(ROOT)
    m["flow"] = {"commit": "abc123def456", "dirty": dirty}
    bit = bdir / f"{m['top']}.bit"
    bit.write_bytes(make_bit(int(m["build_id"], 16)))
    m["outputs"] = {"bit": {"file": bit.name, "sha256": manifest.sha256_file(bit), "usr_access": m["build_id"].upper()}}
    m["tools"].update({"vivado_ran": "2026.1", "vivado_sw_build": "1", "vivado_licence_tier": "BASIC"})
    m["tools_consistent"] = True
    (bdir / "manifest.json").write_text(json.dumps(m))
    (bdir / "gates.json").write_text(json.dumps({"pass": True, "first_failed_stage": None,
                                                 "timing": {"wns_ns": 1.0, "tns_ns": 0, "whs_ns": 0.1, "ths_ns": 0},
                                                 "utilization": {"lut": 10, "ff": 20, "bram_tile": 0, "dsp": 0},
                                                 "power": {"total_w": 0.1}, "power_environment": {"junction_c": 41}}))
    (bdir / "run.json").write_text("{}")
    for r in ("timing_summary.rpt", "utilization.rpt", "power.rpt", "drc.rpt", "methodology.rpt", "cdc.rpt"):
        (bdir / r).write_text(f"{r}\n")
    (design / "build" / "review").mkdir()
    (design / "build" / "review" / "review_index.html").write_text("<p>review</p>")
    return design


def test_bundle_is_made_and_checked(tmp_path: Path) -> None:
    design = _fake_build(tmp_path)
    out = release.make(design, "base", tmp_path / "bundle")
    r = release.check(out)
    assert r["pass"], r
    files = (out / "SHA256SUMS").read_text()
    for f in ("manifest.json", "gates.json", "reports/timing_summary.rpt", "review/review_index.html", "RELEASE.md",
              "t1_dimmer_counter_top.bit"):
        assert f"  {f}\n" in files
    assert r["build_id"] in (out / "RELEASE.md").read_text()


def test_checker_catches_tampering(tmp_path: Path) -> None:
    out = release.make(_fake_build(tmp_path), "base", tmp_path / "bundle")
    (out / "reports" / "power.rpt").write_text("edited\n")
    assert not release.check(out)["checks"]["sha256sums"]["pass"]
    out = release.make(_fake_build(tmp_path / "2"), "base", tmp_path / "bundle2")
    (out / "extra.txt").write_text("not listed")
    assert not release.check(out)["checks"]["sha256sums"]["pass"]
    out = release.make(_fake_build(tmp_path / "3"), "base", tmp_path / "bundle3")
    bit = out / "t1_dimmer_counter_top.bit"
    bit.write_bytes(make_bit(0x0BADF00D))
    r = release.check(out)["checks"]
    assert not r["bitstream_usr_access_is_build_id"]["pass"] and not r["bitstream_hash_in_manifest"]["pass"]


def test_make_refuses_failed_gates_and_dirty_trees(tmp_path: Path) -> None:
    design = _fake_build(tmp_path, dirty=True)
    with pytest.raises(release.ReleaseError, match="uncommitted"):
        release.make(design, "base", tmp_path / "b")
    out = release.make(design, "base", tmp_path / "b", allow_dirty=True)
    assert not release.check(out)["checks"]["clean_tree"]["pass"]
    assert release.check(out, allow_dirty=True)["pass"]
    g = design / "build" / "base" / "gates.json"
    g.write_text(json.dumps(dict(json.loads(g.read_text()), **{"pass": False, "first_failed_stage": "post_route"})))
    with pytest.raises(release.ReleaseError, match="gates failed"):
        release.make(design, "base", tmp_path / "c", allow_dirty=True)


def test_committed_sample_bundle_passes_the_checker() -> None:
    """The CI job's second half: the sample bundle (a real Vivado 2026.1 build of T1, brief 54) checks on its own."""
    assert SAMPLE.is_dir(), "results/54_reproducible/sample_bundle is missing"
    bundles = [d for d in SAMPLE.iterdir() if (d / "SHA256SUMS").is_file()]
    assert bundles
    for b in bundles:
        r = release.check(b)
        assert r["pass"], {k: v for k, v in r["checks"].items() if not v["pass"]}
        assert bitstream.info(b / "t1_dimmer_counter_top.bit")["crc_all_match"]


# ---- board flow ---------------------------------------------------------------------------------------------------
def test_build_id_comparison_and_conditions() -> None:
    assert program.check_build_id("ae066748", "0xAE066748", "jtag")["match"]
    assert not program.check_build_id("ae066748", "0x00000000", "jtag")["match"]
    assert program.check_build_id(None, "0x1", "jtag")["checked"] is False
    assert program.check_shell_build_id({"build_stamp": 0xDFD4624E}, "dfd4624e")["match"]
    with pytest.raises(program.hw.HwError, match="mismatch"):
        program.check_shell_build_id({"build_stamp": 0x1}, "dfd4624e")
    assert program.check_shell_build_id({"build_stamp": 0x1}, None)["checked"] is False
    text = ("FDA-COND NOW TEMPERATURE=41.2 VCCINT=0.998 VCCAUX=1.79 VCCBRAM=0.999\n"
            "FDA-COND MAX TEMPERATURE=41.5 VCCINT=1.0011 VCCAUX=1.7988 VCCBRAM=1.0005\n"
            "FDA-COND MIN TEMPERATURE=40.9 VCCINT=0.9961 VCCAUX=1.7871 VCCBRAM=0.9968\nFDA-COND FLAGS 0000\n")
    c = program.parse_conditions(text)
    assert c["inside_roc"] and c["flags"] == "0000" and c["now"]["VCCINT"] == 0.998
    c = program.parse_conditions(text.replace("VCCAUX=1.79 ", "VCCAUX=1.95 "))
    assert not c["inside_roc"] and c["outside"] == ["now VCCAUX 1.95"]
    assert program.parse_conditions("")["read"] is False
