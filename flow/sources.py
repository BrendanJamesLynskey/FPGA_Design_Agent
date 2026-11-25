"""One place that says which files are a design's HDL sources and which language each is in (brief 153, review item F9).

Before brief 153 every check found its RTL with its own suffix glob (``rtl/*.sv``, ``.sv/.v/.svh/.vh``), so a VHDL design had no
files to read, the check found nothing, and passed. The rule now:

1. A scan asks this module for the design's files (:func:`design_rtl`, :func:`build_sources`), by language, never by a glob of its own.
2. A scan that cannot read a language says so. :func:`no_reader` returns the one-line text ("no reader for .vhd: ...") a check
   puts in its ``parts`` (so the check is PARTIAL, never a clean pass), a gate puts in its ``why`` (so it is not run), and a
   command prints. A scan that finds no RTL for a design that has RTL fails closed the same way.

Languages: ``sv`` (``.sv`` ``.v``), ``header`` (``.svh`` ``.vh``, read as part of SystemVerilog), ``vhdl`` (``.vhd`` ``.vhdl``).
VHDL comments run from ``--`` to the end of the line; SystemVerilog has ``//`` and ``/* */``: :func:`strip_comments` takes the language.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import yaml

ROOT = Path(__file__).resolve().parents[1]

SV_EXT = (".sv", ".v")
HEADER_EXT = (".svh", ".vh")
VHDL_EXT = (".vhd", ".vhdl")
HDL_EXT = SV_EXT + HEADER_EXT + VHDL_EXT


def language(p: Path | str) -> str | None:
    """``sv``, ``header``, ``vhdl``, or None for a file that is not HDL."""
    s = Path(p).suffix.lower()
    if s in SV_EXT:
        return "sv"
    if s in HEADER_EXT:
        return "header"
    if s in VHDL_EXT:
        return "vhdl"
    return None


def by_language(files: Iterable[Path | str]) -> dict[str, list[Path]]:
    """``{"sv": [...], "header": [...], "vhdl": [...]}`` (every key present), each list in the order given; non-HDL files dropped."""
    out: dict[str, list[Path]] = {"sv": [], "header": [], "vhdl": []}
    for f in files:
        lang = language(f)
        if lang:
            out[lang].append(Path(f))
    return out


def vhdl_files(files: Iterable[Path | str]) -> list[Path]:
    return by_language(files)["vhdl"]


def sv_files(files: Iterable[Path | str], headers: bool = False) -> list[Path]:
    g = by_language(files)
    return g["sv"] + (g["header"] if headers else [])


def build_sources(design: Path, root: Path = ROOT) -> list[Path]:
    """The build's own source list: flow/prepare.py's expansion of ``build.yaml`` ``sources`` (pathlib glob, so ``**`` recurses), no
    duplicates, every language. With no readable build.yaml, the design's own ``rtl/`` tree (SystemVerilog, Verilog and VHDL)."""
    try:
        b = yaml.safe_load((design / "build.yaml").read_text()) or {}
    except (OSError, yaml.YAMLError):
        return sorted(p for p in design.glob("rtl/**/*") if p.is_file() and language(p) in ("sv", "vhdl"))
    out: list[Path] = []
    for g in b.get("sources") or []:
        out += [p for p in sorted(root.glob(g)) if p not in out]
    return out


def design_rtl(design: Path) -> list[Path]:
    """The design's own HDL files in ``rtl/`` (not the shell, not the build): SystemVerilog, Verilog and VHDL, sorted by name."""
    rtl = Path(design) / "rtl"
    if not rtl.is_dir():
        return []
    return sorted(p for p in rtl.iterdir() if p.is_file() and language(p) in ("sv", "vhdl"))


def has_vhdl(design: Path) -> bool:
    return bool(vhdl_files(design_rtl(design)))


def no_reader(files: Iterable[Path | str], reads: Iterable[str], who: str, headers_ok: bool = True) -> str | None:
    """The fail-closed text for ``files`` a scan cannot read, or None when it can read every one.

    ``reads`` names the languages the scan reads (``"sv"``, ``"vhdl"``); ``who`` is the scan's name for the message. Headers count
    as SystemVerilog. The text names the suffixes, the number and the first file names, so the reader of a digest sees what was not
    read and by which check."""
    reads = set(reads)
    if headers_ok and "sv" in reads:
        reads.add("header")
    skipped = [Path(f) for f in files if language(f) and language(f) not in reads]
    if not skipped:
        return None
    sfx = sorted({p.suffix.lower() for p in skipped})
    names = ", ".join(p.name for p in skipped[:3]) + (f" (+{len(skipped) - 3} more)" if len(skipped) > 3 else "")
    ok = " and ".join("VHDL" if r == "vhdl" else "SystemVerilog" for r in sorted(reads - {"header"})) or "nothing"
    return f"no reader for {', '.join(sfx)} ({len(skipped)} file(s): {names}): {who} reads {ok} only"


_SV_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)
_VHDL_COMMENT = re.compile(r"/\*.*?\*/|--[^\n]*", re.S)      # VHDL-2008 also has /* */


def strip_comments(text: str, lang: str = "sv") -> str:
    """Comments blanked (newlines kept, so line numbers stay right) for ``sv`` (and headers) or ``vhdl``."""
    rx = _VHDL_COMMENT if lang == "vhdl" else _SV_COMMENT
    return rx.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def parse_vhdl_literal(expr: str) -> int | None:
    """The integer value of a VHDL literal: a bit string (``x"47524159"``, ``b"0101"``, ``o"17"``, ``X"4752_4159"``), a based literal
    (``16#4752_4159#``), a decimal integer, or a short string of characters (``"GRAY"``, read as ASCII, most significant first).
    None for anything else (a name, an expression, a literal with ``U``/``X``/``Z``/``-`` digits)."""
    e = expr.strip()
    m = re.fullmatch(r'(?i)(?:\d+)?([xbo])\s*"([0-9a-f_]+)"', e)
    if m:
        digits = m.group(2).replace("_", "")
        return int(digits, {"x": 16, "b": 2, "o": 8}[m.group(1).lower()]) if digits else None
    m = re.fullmatch(r"(\d+)\s*#([0-9a-fA-F_]+)#", e)
    if m:
        return int(m.group(2).replace("_", ""), int(m.group(1)))
    if re.fullmatch(r"\d[\d_]*", e):
        return int(e.replace("_", ""))
    s = re.fullmatch(r'"([^"]{1,8})"', e)
    if s:
        return int.from_bytes(s.group(1).encode("ascii", "replace"), "big")
    return None


# ---------------------------------------------------------------------------------------------------------------------
# what each reader does with a VHDL file (the table `python -m flow.sources` prints; tools/vhdl_parity_probe.py measures it)
# ---------------------------------------------------------------------------------------------------------------------
#: (reader id of the probe, what it is, what it does with VHDL). "reads" = the VHDL is parsed; "no reader" = the result says it did not read it.
COVERAGE: list[tuple[str, str, str]] = [
    ("R01", "check `lint`", "reads: GHDL lint (analysis -Wall, synthesis of the top) when the build's top is a VHDL entity; no reader when a SystemVerilog top sits over VHDL"),
    ("R02", "check `standards`", "reads: the rules run on the GHDL netlist of the VHDL (signal initial values removed)"),
    ("R03", "check `resets` (source part)", "reads: Yosys with the ghdl plugin, one front end per language"),
    ("R04", "check `xpm_sim`", "reads: an `xpm_cdc_*` instance in VHDL (component, entity or plain) without `SIM_ASSERT_CHK => 1`"),
    ("R05", "check `constants`", "reads: the `generic map` of the `fpga_shell` instance (literal, constant or generic default); anything else makes the check PARTIAL"),
    ("R06", "check `axi`", "reads: text of Tcl, XDC, YAML and HDL (language-neutral)"),
    ("R07", "check `axi_profile`", "no reader: it compares generated SystemVerilog register blocks; the generator emits no VHDL (PARTIAL when `interfaces:` is declared)"),
    ("R08", "check `fsm` (fsm_coverage)", "no reader: the state table comes from a SystemVerilog `typedef enum` (NOT RUN, with the reason)"),
    ("R09", "`cdc_inject.design_crosses`", "reads: `attribute ASYNC_REG of ...` and `xpm_cdc_*` / `xpm_fifo_async` instances in VHDL"),
    ("R10", "CDC injection run", "no reader: the injection rewrites SystemVerilog synchroniser registers; a VHDL crossing FAILS the run closed"),
    ("R11", "spec-test role (`agent.graph.spectest`)", "reads: the VHDL as its GHDL netlist (a synthesis view, not VHDL simulation semantics)"),
    ("R12", "spec-test evidence key (`rtl_hash`)", "reads: every `rtl/` file, all languages"),
    ("R13", "trace matrix v1 (`legacy_items`)", "reads: every `rtl/` file, all languages"),
    ("R14", "`hw_dry_check` (constant-0 BUILD_STAMP)", "reads: `BUILD_STAMP => x\"00000000\"` in a VHDL instance"),
    ("R15", "managed RTL import", "no reader: a VHDL component is reported as not read (the import simulates Verilog under Icarus)"),
    ("R16", "review (`infer_top`)", "reads: the top entity no other VHDL file instantiates"),
    ("R17", "inspect schematics", "no reader: Yosys with slang draws SystemVerilog only; the page and the notes say so"),
    ("--", "trace matrix elements and inline waivers", "reads: `entity` as the element, `-- req:` tags and `-- std-waive:` comments"),
]

HELP = """What runs on a VHDL design, and what to watch for (brief 153).

The files of a design are found once (this module), by language: .sv .v (SystemVerilog and Verilog), .svh .vh (headers) and .vhd .vhdl
(VHDL). A check that cannot read a language says so; it does not pass. How to read the results:

- PARTIAL in the check digest, or NOT RUN, with "no reader for .vhd": the check did not read your VHDL. It is not a pass for that part.
  Fix the part that was read, and verify the part that was not by the route in docs/vhdl.md.
- The lint of a VHDL design is GHDL's (analysis -Wall, then synthesis of the top), not Verilator's. Its findings are listed under the
  tool name `verilator` with the code `GHDL` (they map to the lint catch-all rule HDL-LINT-00).
- The derived-constants check reads a VHDL design ID from a literal (x"47524159", 16#47524159#, "GRAY") or from a constant or generic
  default whose value is such a literal. A function call or any other expression leaves the check PARTIAL, not clean.
- VHDL comments start with `--`. Tags and waivers: `-- req: ...` and `-- std-waive: RULE reason owner: X; date: YYYY-MM-DD`.
- The spec-test role and the hidden-test scorer simulate the GHDL netlist of your VHDL (a synthesis view; an incomplete sensitivity
  list or a 'U' start value is not seen). Use the native GHDL route (docs/vhdl.md) for a block without the shell.
- The CDC injection run cannot inject into VHDL: a VHDL design with a clock-domain crossing FAILS that run closed until it has an injector.
- The flow records no VHDL code coverage (brief 156 measured it: GHDL 4.1.0 `--coverage` gives statement lines, NVC gives statement, branch,
  toggle and expression bins; results/156_vhdl_tools) and has no VHDL register-map generator: the register map's VHDL is yours.
"""


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m flow.sources", description=HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("design", nargs="?", help="a design directory: list its HDL files by language, then the table")
    a = ap.parse_args(argv)
    if a.design:
        d = Path(a.design)
        g = by_language(build_sources(d))
        own = by_language(design_rtl(d))
        print(f"{d.name}: build list: {len(g['sv'])} SystemVerilog/Verilog, {len(g['header'])} header, {len(g['vhdl'])} VHDL file(s); "
              f"own rtl/: {len(own['sv'])} SystemVerilog/Verilog, {len(own['vhdl'])} VHDL")
        for lang in ("sv", "vhdl"):
            for f in g[lang]:
                print(f"  {lang:5} {f.relative_to(ROOT) if f.is_relative_to(ROOT) else f}")
    print("reader                                  what it does with a VHDL file")
    for rid, name, what in COVERAGE:
        print(f"{rid:3} {name:36} {what}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
