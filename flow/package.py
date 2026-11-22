"""The design package (brief 174): spec.md, every board material and, optionally, an existing design in one folder.

    python -m flow.package init <dir>                  list the files, write/refresh package.yaml (SHA-256, kind, public flag)
    python -m flow.package verify <dir>                check every listed file against its hash
    python -m flow.package gitignore <dir>             write <dir>/.gitignore: private files stay on disk, only the manifest is committed
    python -m flow.package ingest <dir>                extract facts to <dir>/board_facts.yaml, with a conflict list
    python -m flow.package allegro-script <dir>        write the owner-run script that dumps an Allegro .brd to CSV (never run here)
    python -m flow.package check <dir> [--board B]     compare board_facts.yaml with boards/<B>/board.yaml
    python -m flow.package offchip <dir>               an off_chip: fragment from the facts: board_fixed, trace-length range per net family
    python -m flow.package existing <dir>              inventory <dir>/existing, write existing_inventory.yaml and the design.yaml marks
    python -m flow.package frozen-check <dir> <work>   gates on an edited copy of existing/: frozen files, interfaces, constraints, timing

Every fact carries its source (file, locator, SHA-256) and a confidence. Facts that disagree between sources are
listed as conflicts and never resolved silently. The convention is in docs/design_package.md.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml


class _NoAlias(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True

KINDS = ("spec", "schematic_pdf", "schematic_source", "board_file", "bom", "xdc", "board_xml", "ibis", "datasheet",
         "allegro_dump", "photo", "notes", "ref", "existing", "other")
# chip families the BOM reader recognises: (role, regex on the manufacturer part number)
CHIPS = (("phy", r"DP83\d{3}|88E1\d{3}|KSZ\d{4}|RTL8211|VSC85\d\d|LAN87\d\d|DP838\d\d"),
         ("memory", r"MT4\dA|MT40A|MT41|IS43|IS46|W9\d{4}|MX25|MT25Q|S25FL|N25Q|M24C|24LC|93LC|AT24"),
         ("usb_uart_bridge", r"FT\d{3,4}[A-Z]*"),
         ("usb_phy", r"USB3320|USB3300|USB\d{4}"),
         ("clock_buffer", r"LMK1C|CDCLVC|SI53\d\d|ADN\d{4}"))
IOSTD_VCCO = {"LVCMOS12": 1.2, "LVCMOS15": 1.5, "LVCMOS18": 1.8, "LVCMOS25": 2.5, "LVCMOS33": 3.3, "LVTTL": 3.3,
              "SSTL15": 1.5, "SSTL135": 1.35, "SSTL18": 1.8, "HSTL_I_18": 1.8, "LVDS_25": 2.5, "LVDS": 1.8}


def today() -> str:
    return datetime.date.today().isoformat()


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def kind_of(rel: str) -> str:
    n, low = Path(rel).name, rel.lower()
    ext = Path(rel).suffix.lower()
    if n == "spec.md" or n.lower() == "spec.md":
        return "spec"
    if low.startswith("existing/"):
        return "existing"
    if low.startswith("refs/"):
        return "ref"
    if "allegro_dump" in low and ext == ".csv":
        return "allegro_dump"
    if ext == ".xdc":
        return "xdc"
    if ext in (".ibs", ".ibis"):
        return "ibis"
    if ext in (".brd", ".kicad_pcb", ".odb", ".tgz") and ("brd" in low or "kicad" in low or "odb" in low or ext == ".brd"):
        return "board_file"
    if ext == ".xml" and ("board" in low or "part0_pins" in low):
        return "board_xml"
    if ext in (".dsn", ".kicad_sch", ".sch"):
        return "schematic_source"
    if "bom" in low and ext in (".xls", ".xlsx", ".csv", ".tsv"):
        return "bom"
    if ext == ".pdf" and ("sch" in low or "schem" in low):
        return "schematic_pdf"
    if ext == ".pdf":
        return "datasheet"
    if ext in (".png", ".jpg", ".jpeg"):
        return "photo"
    if ext in (".md", ".txt"):
        return "notes"
    return "other"


# ---------------------------------------------------------------------------------------------- manifest

def load_manifest(pkg: Path) -> dict[str, Any]:
    f = pkg / "package.yaml"
    return yaml.safe_load(f.read_text()) if f.exists() else {"name": pkg.name, "files": []}


def save_manifest(pkg: Path, m: dict[str, Any]) -> None:
    head = ("# The package manifest (brief 174, docs/design_package.md). Every file under board/, refs/ and existing/ is listed\n"
            "# with its kind, source, licence, SHA-256 and a public flag. Files with public: false stay on disk and are git-ignored\n"
            "# (flow.package gitignore); only this manifest and the derived facts (board_facts.yaml) are committed.\n")
    (pkg / "package.yaml").write_text(head + yaml.dump(m, Dumper=_NoAlias, sort_keys=False, width=140))


def package_files(pkg: Path) -> list[str]:
    out = []
    for sub in ("spec.md", "board", "refs", "existing"):
        p = pkg / sub
        if p.is_file():
            out.append(sub)
        elif p.is_dir():
            out += [str(q.relative_to(pkg)) for q in sorted(p.rglob("*")) if (q.is_file() or q.is_symlink()) and "__pycache__" not in q.parts]
    return out


def init(pkg: Path) -> dict[str, Any]:
    """List the files, keep the entries a human wrote (source, licence, public), refresh kind and hash. A new file is private."""
    m = load_manifest(pkg)
    old = {e["path"]: e for e in m.get("files") or []}
    files = []
    for rel in package_files(pkg):
        e = dict(old.get(rel, {}))
        e["path"] = rel
        e["kind"] = e.get("kind") or kind_of(rel)
        e.setdefault("source_url", None)
        e.setdefault("licence", None)
        e.setdefault("public", rel == "spec.md")
        e["sha256"] = sha256(pkg / rel)
        e["bytes"] = (pkg / rel).stat().st_size
        files.append(e)
    m["files"] = files
    m.setdefault("board_fixed", False)
    save_manifest(pkg, m)
    return m


def verify(pkg: Path) -> list[str]:
    """Problems: a listed file whose hash changed, an unlisted file, a missing public file. A missing private file is not a problem
    (a clone has the manifest only), it is reported as 'absent'."""
    m = load_manifest(pkg)
    bad = []
    listed = set()
    for e in m.get("files") or []:
        listed.add(e["path"])
        p = pkg / e["path"]
        if not p.exists():
            if e.get("public"):
                bad.append(f"missing public file {e['path']}")
            continue
        if sha256(p) != e.get("sha256"):
            bad.append(f"hash changed: {e['path']}")
    bad += [f"not in the manifest: {r}" for r in package_files(pkg) if r not in listed]
    return bad


def gitignore(pkg: Path) -> list[str]:
    m = load_manifest(pkg)
    priv = [e["path"] for e in m.get("files") or [] if not e.get("public")]
    body = ("# written by flow.package gitignore: files with public: false stay on disk, the manifest holds their hashes\n"
            + "\n".join(f"/{p}" for p in priv) + "\n")
    (pkg / ".gitignore").write_text(body)
    return priv


# ---------------------------------------------------------------------------------------------- facts

class Facts:
    def __init__(self, pkg: Path, manifest: dict[str, Any]):
        self.pkg = pkg
        self.rows: list[dict[str, Any]] = []
        self.unread: list[dict[str, str]] = []
        self.hash = {e["path"]: e.get("sha256") for e in manifest.get("files") or []}

    def add(self, key: str, value: Any, file: str, locator: str, confidence: str, **extra: Any) -> None:
        row = {"key": key, "value": value,
               "source": {"file": file, "locator": locator, "sha256": self.hash.get(file) or (sha256(self.pkg / file) if (self.pkg / file).exists() else None)},
               "confidence": confidence}
        row.update(extra)
        self.rows.append(row)


def _norm(v: Any) -> str:
    return re.sub(r"[^a-z0-9.]", "", str(v).lower())


def parse_xdc(text: str) -> dict[str, Any]:
    """Uncommented PACKAGE_PIN / IOSTANDARD / create_clock lines; commented create_clock lines are returned apart (Digilent keeps the clock that way)."""
    pins: dict[str, dict[str, str]] = defaultdict(dict)
    clocks: list[dict[str, Any]] = []
    commented: list[dict[str, Any]] = []
    for ln, raw in enumerate(text.splitlines(), 1):
        is_c = raw.lstrip().startswith("#")
        line = raw.lstrip("# \t")
        m = re.search(r"set_property\s+(?:-dict\s*\{\s*)?(PACKAGE_PIN|IOSTANDARD)\s+(\S+?)\s*(?:\})?\s*\[get_ports\s+\{?\s*([^\]\s}]+)", line)
        if m and not is_c:
            pins[m.group(3)][m.group(1)] = m.group(2)
            pins[m.group(3)].setdefault("line", str(ln))
        d = re.search(r"-dict\s*\{\s*PACKAGE_PIN\s+(\S+)\s+IOSTANDARD\s+(\S+)\s*\}\s*\[get_ports\s+\{?\s*([^\]\s}]+)", line)
        if d and (not is_c or raw.lstrip().startswith("#set_property")):    # Digilent's master XDC lists every pin commented out
            pins[d.group(3)].update({"PACKAGE_PIN": d.group(1), "IOSTANDARD": d.group(2), "line": str(ln), "commented": is_c})
        c = re.search(r"create_clock\s.*?-period\s+([\d.]+).*?get_ports\s+\{?\s*([^\]\s}]+)", line)
        if c:
            (commented if is_c else clocks).append({"port": c.group(2), "period_ns": float(c.group(1)), "line": ln})
    return {"pins": dict(pins), "clocks": clocks, "commented_clocks": commented}


def read_bom(path: Path) -> tuple[list[dict[str, str]], str | None]:
    """Rows with Part Reference, Manufacturers Part Number, Description, Quantity. .xls needs xlrd; .csv/.tsv need nothing."""
    ext = path.suffix.lower()
    keymap = {"quantity": "qty", "qty": "qty", "partreference": "refs", "reference": "refs", "designator": "refs",
              "manufacturerspartnumber": "mpn", "manufacturerpartnumber": "mpn", "mpn": "mpn", "partnumber": "mpn",
              "description": "desc", "manufacturers": "mfr", "manufacturer": "mfr"}

    def norm_rows(rows: list[list[Any]]) -> list[dict[str, str]]:
        hdr = None
        out = []
        for r in rows:
            cells = [str(c).strip() for c in r]
            if hdr is None:
                m = [keymap.get(re.sub(r"[^a-z]", "", c.lower())) for c in cells]
                if "mpn" in m or "refs" in m:
                    hdr = m
                continue
            d = {hdr[i]: cells[i] for i in range(min(len(hdr), len(cells))) if hdr[i]}
            if d.get("mpn") or d.get("desc"):
                out.append(d)
        return out
    if ext in (".csv", ".tsv"):
        with open(path, newline="", errors="replace") as f:
            return norm_rows(list(csv.reader(f, delimiter="\t" if ext == ".tsv" else ","))), None
    if ext == ".xls":
        try:
            import xlrd  # type: ignore
        except ImportError:
            return [], "the BOM is .xls and xlrd is not installed (pip install xlrd in a venv), or save it as .csv"
        s = xlrd.open_workbook(str(path)).sheet_by_index(0)
        return norm_rows([s.row_values(r) for r in range(s.nrows)]), None
    return [], f"BOM format {ext} not read (save it as .csv)"


def ingest_bom(F: Facts, rel: str) -> None:
    rows, err = read_bom(F.pkg / rel)
    if err:
        F.unread.append({"file": rel, "why": err})
        return
    res: dict[str, list[str]] = defaultdict(list)
    for i, r in enumerate(rows, 2):
        mpn, desc, refs = r.get("mpn", ""), r.get("desc", ""), r.get("refs", "")
        loc = f"BOM row {i}"
        for role, rx in CHIPS:
            m = re.match(rx, mpn, re.I) or re.search(rx, mpn, re.I)
            if m:
                fam = re.match(r"[A-Za-z]+\d+[A-Za-z]*\d*", mpn)
                fam_s = (re.match(r"DP83\d{3}|88E1\d{3}|KSZ\d{4}|RTL8211[A-Z]*|VSC85\d\d|FT\d{3,4}[A-Z]*|USB\d{4}", mpn, re.I) or fam or m).group(0)
                F.add(f"chip.{role}.{fam_s.upper()}", {"mpn": mpn, "refs": re.split(r"[,\s]+", refs.strip()), "qty": r.get("qty"), "description": desc},
                      rel, loc, "high")
                break
        if desc.lower().startswith("osc"):
            f = re.search(r"([\d.]+)\s*MHz", desc, re.I)
            F.add(f"oscillator.{mpn}", {"mhz": float(f.group(1)) if f else None, "refs": re.split(r"[,\s]+", refs.strip()), "description": desc},
                  rel, loc, "high")
        rm = re.match(r"Res\s+(\d+(?:[KkMR]\d*)?|\d+\.\d+[KkM]?)\s", desc)
        if rm:
            res[rm.group(1)] += re.split(r"[,\s]+", refs.strip()) if refs else []
    series = {v: refs for v, refs in res.items() if _ohms(v) is not None and _ohms(v) <= 100}
    if series:
        F.add("bom.series_resistors", {v: {"ohm": _ohms(v), "count": len(refs)} for v, refs in sorted(series.items(), key=lambda kv: _ohms(kv[0]) or 0)},
              rel, "BOM, rows whose description starts 'Res' and whose value is 100 ohm or less (every use of the value, not only series ones)", "medium")


def _ohms(v: str) -> float | None:
    m = re.fullmatch(r"(\d+)([RKMkm])(\d*)", v)
    if m:
        mult = {"R": 1, "K": 1e3, "k": 1e3, "M": 1e6, "m": 1e6}[m.group(2)]
        return float(f"{m.group(1)}.{m.group(3) or 0}") * mult
    try:
        return float(v)
    except ValueError:
        return None


def pdf_text(path: Path) -> str | None:
    if path.suffix.lower() in (".txt",):
        return path.read_text(errors="replace")
    try:
        return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, timeout=120, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None


def ingest_schematic(F: Facts, rel: str, bom_parts: dict[str, str]) -> None:
    txt = pdf_text(F.pkg / rel)
    if txt is None:
        F.unread.append({"file": rel, "why": "pdftotext failed or is not installed"})
        return
    pages = txt.split("\f")
    for i, pg in enumerate(pages, 1):
        sq = re.sub(r"[ \t]+", " ", pg)
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*MHz\s+(LVDS|LVCMOS|LVPECL|CMOS|HCSL)\s*\(([^)]+)\)", sq, re.I):
            F.add(f"clock_label.{m.group(3).strip()}", {"mhz": float(m.group(1)), "standard": m.group(2).upper()}, rel, f"page {i}, oscillator label text", "medium")
        for m in re.finditer(r"\b([A-Z][A-Z0-9_]{3,})_R\s+(\d+(?:\.\d+)?[KkMR]?)\s+(R\d{1,3})\b", sq):
            F.add(f"series_r.{m.group(1)}", {"ohm": _ohms(m.group(2)) if _ohms(m.group(2)) is not None else m.group(2), "ref": m.group(3)}, rel,
                  f"page {i}, text next to the net: heuristic, check on the drawing", "low")
        for fam, mpn in bom_parts.items():
            if re.search(re.escape(fam), sq, re.I):
                F.add(f"chip_on_schematic.{fam}", True, rel, f"page {i}", "medium")
    # one fact per chip family: keep the first page only
    seen = set()
    F.rows = [r for r in F.rows if not (r["key"].startswith("chip_on_schematic.") and (r["key"] in seen or seen.add(r["key"])))]


def ingest_xdc(F: Facts, rel: str) -> None:
    x = parse_xdc((F.pkg / rel).read_text(errors="replace"))
    for port, d in sorted(x["pins"].items()):
        if "PACKAGE_PIN" in d:
            F.add(f"pin.{port}", {"pin": d["PACKAGE_PIN"], "iostandard": d.get("IOSTANDARD")}, rel,
                  f"line {d['line']}" + (" (listed, commented out in the vendor master file)" if d.get("commented") else ""), "high")
    stds = sorted({d.get("IOSTANDARD") for d in x["pins"].values() if d.get("IOSTANDARD")})
    for s in stds:
        if s in IOSTD_VCCO:
            F.add(f"iostandard.{s}.vcco_v", IOSTD_VCCO[s], rel, f"standard {s} used on {sum(1 for d in x['pins'].values() if d.get('IOSTANDARD') == s)} ports", "medium",
                  note="the bank's VCCO that the standard needs; the bank per pin is not in an XDC")
    for c in x["clocks"]:
        F.add(f"clock.{c['port']}", {"mhz": round(1000 / c["period_ns"], 6)}, rel, f"line {c['line']}", "high")
    for c in x["commented_clocks"]:
        F.add(f"clock.{c['port']}", {"mhz": round(1000 / c["period_ns"], 6)}, rel, f"line {c['line']} (commented out in the vendor file)", "medium")


def ingest_board_xml(F: Facts, rel: str) -> None:
    import xml.etree.ElementTree as ET
    try:
        root = ET.parse(F.pkg / rel).getroot()
    except ET.ParseError as e:
        F.unread.append({"file": rel, "why": f"XML error {e}"})
        return
    for el in root.iter():
        t = el.tag.split("}")[-1]
        if t == "component" and el.get("part_name"):
            F.add("part", el.get("part_name"), rel, f"component {el.get('name')} part_name", "high")
        if t == "pin" and el.get("loc") and el.get("name"):
            F.add(f"board_pin.{el.get('name')}", {"pin": el.get("loc")}, rel, f"part0_pins index {el.get('index')}", "high")


def ingest_allegro(F: Facts, rel_dir: str, net_filter: str) -> None:
    d = F.pkg / rel_dir
    f = d / "nets.csv"
    rx = re.compile(net_filter)
    tot: dict[str, float] = defaultdict(float)
    for r in csv.DictReader(open(f, newline="")):
        if rx.search(r["net"]):
            tot[r["net"]] += float(r["length_mil"])
    vias: dict[str, int] = {}
    if (d / "net_vias.csv").exists():
        vias = {r["net"]: int(r["n_vias"]) for r in csv.DictReader(open(d / "net_vias.csv", newline=""))}
    rel = f"{rel_dir}/nets.csv"
    for n, mil in sorted(tot.items()):
        F.add(f"trace_length_mil.{n}", round(mil, 1), rel, f"sum of per-layer segment lengths of net {n} (Allegro dump, copper only, no SOM)", "medium", vias=vias.get(n))
    meta = d / "meta.txt"
    if meta.exists() and "units_divisor" in meta.read_text():
        F.add("allegro.parse", {"net_rows_kept": len(tot), "filter": net_filter}, f"{rel_dir}/meta.txt", "meta.txt", "medium",
              note="the parse is not independently verified against another CAD tool")


def ingest(pkg: Path) -> dict[str, Any]:
    m = init(pkg) if not (pkg / "package.yaml").exists() else load_manifest(pkg)
    F = Facts(pkg, m)
    files = {e["path"]: e for e in m.get("files") or []}
    spec_mentions = set()
    if (pkg / "spec.md").exists():
        spec_mentions = {w.lower() for w in re.findall(r"[A-Za-z0-9_]+", (pkg / "spec.md").read_text())}
    if m.get("part"):
        F.add("part", m["part"], "package.yaml", "declared by the user in the manifest", "user-declared")
        F.hash["package.yaml"] = sha256(pkg / "package.yaml") if (pkg / "package.yaml").exists() else None
    bom_parts: dict[str, str] = {}
    for rel, e in files.items():
        if not (pkg / rel).exists():
            if e["kind"] not in ("spec", "existing"):
                F.unread.append({"file": rel, "why": "absent (private file not on this machine); facts from it come from the committed board_facts.yaml"})
            continue
        k = e["kind"]
        if k == "xdc":
            ingest_xdc(F, rel)
        elif k == "bom":
            ingest_bom(F, rel)
        elif k == "board_xml":
            ingest_board_xml(F, rel)
        elif k in ("board_file", "schematic_source", "ibis", "photo"):
            F.unread.append({"file": rel, "why": {"board_file": "board file read through the owner-run Allegro dump (allegro-script) or not at all: no KiCad/ODB++/IPC-2581 reader yet",
                                                   "schematic_source": "schematic source (DSN/KiCad) not read; the PDF text is used",
                                                   "ibis": "IBIS not read by the ingest; tools/ibis_extract.py reads it for the off-chip check",
                                                   "photo": "a photo is kept, not read"}[k]})
    bom_fams = {}
    for r in F.rows:
        if r["key"].startswith("chip.") and r["source"]["file"] in files:
            bom_fams[r["key"].split(".")[-1]] = r["value"]["mpn"]
    for rel, e in files.items():
        if e["kind"] == "schematic_pdf" and (pkg / rel).exists():
            ingest_schematic(F, rel, bom_fams)
    dumps = sorted({str(Path(r).parent) for r, e in files.items() if e["kind"] == "allegro_dump" and r.endswith("nets.csv") and (pkg / r).exists()})
    for d in dumps:
        ingest_allegro(F, d, (m.get("ingest") or {}).get("net_filter", r"^(?!N\d+$)"))
    if not any(e["kind"] == "allegro_dump" for e in files.values()) and any(e["kind"] == "board_file" for e in files.values()):
        F.unread.append({"file": "(board file)", "why": "no Allegro dump CSV yet: run the script that `allegro-script` writes, then ingest again (trace lengths)"})
    conflicts = find_conflicts(F.rows)
    for ch in (m.get("existing") or {}).get("change") or []:
        if ch.lower() not in spec_mentions:
            conflicts.append({"key": f"existing.change.{ch}", "kind": "spec_vs_manifest", "note": f"package.yaml says to change '{ch}' but spec.md never names it", "values": []})
    out = {"package": m.get("name", pkg.name), "generated": today(), "board_fixed": bool(m.get("board_fixed", False)),
           "facts": F.rows, "conflicts": conflicts, "not_read": F.unread}
    (pkg / "board_facts.yaml").write_text(
        "# Generated by `python -m flow.package ingest` (brief 174): every fact names its source file, locator and SHA-256.\n"
        "# Do not edit by hand; change the inputs and ingest again.\n" + yaml.dump(out, Dumper=_NoAlias, sort_keys=False, width=160))
    return out


def find_conflicts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Same key, different value, from different source files: reported, never resolved. A fact seen on the schematic and in the
    BOM is not a conflict (it is corroboration)."""
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by[r["key"]].append(r)
    out = []
    for k, rs in by.items():
        if k.startswith(("chip.", "oscillator.", "trace_length", "series_r.", "bom.", "chip_on", "allegro", "iostandard.")):
            continue
        vals = {}
        for r in rs:
            vals.setdefault(_norm(r["value"]), r)
        if len(vals) > 1 and len({r["source"]["file"] for r in rs}) > 1:
            out.append({"key": k, "kind": "sources_disagree", "values": [{"value": r["value"], "source": r["source"]} for r in vals.values()]})
    # two different PHY families in one board's BOM are not a conflict; two different clock figures for one label are
    cl: dict[str, set[float]] = defaultdict(set)
    for r in rows:
        if r["key"].startswith("clock_label."):
            cl[r["key"]].add(r["value"]["mhz"])
    for k, v in cl.items():
        if len(v) > 1:
            out.append({"key": k, "kind": "sources_disagree", "values": sorted(v)})
    return out


# ---------------------------------------------------------------------------------------------- compare with boards/<B>/board.yaml

def facts_index(doc: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    d: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in doc.get("facts") or []:
        d[r["key"]].append(r)
    return d


def check_board(facts_doc: dict[str, Any], board: dict[str, Any], board_dir: Path | None = None, board_text: str = "") -> dict[str, list[dict[str, Any]]]:
    """Facts against the flow's board.yaml: conflicts (they disagree), confirmations (a fact the board file marked unconfirmed is now sourced)."""
    ix = facts_index(facts_doc)
    conflicts, confirms, missing = [], [], []

    def src(rs: list[dict[str, Any]]) -> str:
        r = rs[0]["source"]
        return f"{r['file']}, {r['locator']}"
    for r in ix.get("part", []):
        if _norm(r["value"]) != _norm(board.get("part", "")):
            conflicts.append({"field": "part", "board_yaml": board.get("part"), "fact": r["value"], "source": src([r])})
    phys = {k.split(".")[-1]: rs for k, rs in ix.items() if k.startswith("chip.phy.")}
    pe = board.get("pl_ethernet") or board.get("ethernet") or {}
    claimed = str(pe.get("phy_part") or "")
    if phys:
        have = sorted(phys)
        if claimed:
            if not any(_norm(claimed).startswith(_norm(h)) or _norm(h).startswith(_norm(claimed)) for h in have):
                conflicts.append({"field": "pl_ethernet.phy_part", "board_yaml": claimed, "fact": have, "source": src(next(iter(phys.values())))})
        else:
            missing.append({"field": "pl_ethernet.phy_part", "fact": have, "note": "board.yaml names no PHY part as data; add phy_part"})
            for role, rx in CHIPS[:1]:                       # the part named only in a comment or a string still counts
                for mm in sorted({x.upper() for x in re.findall(rx, board_text, re.I)}):
                    if not any(_norm(mm).startswith(_norm(h)) or _norm(h).startswith(_norm(mm)) for h in have):
                        conflicts.append({"field": "pl_ethernet (PHY part in the text of board.yaml)", "board_yaml": mm, "fact": have,
                                          "source": src(next(iter(phys.values())))})
    clk = board.get("clock") or {}
    for r in ix.get(f"clock.{clk.get('port')}", []):
        if abs(float(r["value"]["mhz"]) - float(clk.get("freq_mhz", 0))) > 1e-6:
            conflicts.append({"field": "clock.freq_mhz", "board_yaml": clk.get("freq_mhz"), "fact": r["value"]["mhz"], "source": src([r])})
        else:
            confirms.append({"field": "clock.freq_mhz", "value": clk.get("freq_mhz"), "source": src([r])})
    oscs = {float(r["value"]["mhz"]): r for k, rs in ix.items() if k.startswith("oscillator.") for r in rs if r["value"].get("mhz")}
    if clk.get("freq_mhz") and float(clk["freq_mhz"]) in oscs and not ix.get(f"clock.{clk.get('port')}"):
        confirms.append({"field": "clock.freq_mhz", "value": clk["freq_mhz"], "source": src([oscs[float(clk["freq_mhz"])]]),
                         "note": "weaker: an oscillator of this frequency is on the BOM; the schematic's clock labels say which net it drives"})
    for gname, g in (board.get("gt") or {}).items():
        rc = (g or {}).get("refclk") or {}
        if rc.get("mhz"):
            lab = [r for k, rs in ix.items() if k.startswith("clock_label.") for r in rs if abs(r["value"]["mhz"] - float(rc["mhz"])) < 1e-6]
            if lab:
                confirms.append({"field": f"gt.{gname}.refclk.mhz", "value": rc["mhz"], "source": src(lab), "label": next(k for k in ix if k.startswith("clock_label.") and ix[k][0] is lab[0])})
            elif oscs:
                conflicts.append({"field": f"gt.{gname}.refclk.mhz", "board_yaml": rc["mhz"], "fact": sorted(oscs), "source": src(next(iter(oscs.values())))})
    if board_dir is not None and board.get("master_xdc") and (board_dir / board["master_xdc"]).exists():
        mine = parse_xdc((board_dir / board["master_xdc"]).read_text(errors="replace"))["pins"]
        for k, rs in ix.items():
            if k.startswith("pin."):
                port = k[4:]
                if port in mine and mine[port].get("PACKAGE_PIN") and mine[port]["PACKAGE_PIN"] != rs[0]["value"]["pin"]:
                    conflicts.append({"field": f"pin.{port}", "board_yaml": mine[port]["PACKAGE_PIN"], "fact": rs[0]["value"]["pin"], "source": src(rs)})
                elif port in mine and mine[port].get("IOSTANDARD") and rs[0]["value"].get("iostandard") and mine[port]["IOSTANDARD"] != rs[0]["value"]["iostandard"]:
                    conflicts.append({"field": f"iostandard.{port}", "board_yaml": mine[port]["IOSTANDARD"], "fact": rs[0]["value"]["iostandard"], "source": src(rs)})
    return {"conflicts": conflicts, "confirmations": confirms, "missing_in_board_yaml": missing}


def offchip_hints(doc: dict[str, Any]) -> dict[str, Any]:
    """A fragment for a spec's off_chip: section from the facts: board_fixed, and per net family (HPA, HPB, ...) the trace length range in
    inches and any series resistor found on those nets. Which port is on which net needs the pin list of the board file (not dumped yet),
    so the groups are by net family and the user's ports are matched by hand."""
    ix = facts_index(doc)
    fam: dict[str, dict[str, float]] = defaultdict(dict)
    for k, rs in ix.items():
        mm = re.match(r"trace_length_mil\.((HP[AB])\w+)$", k)
        if mm and not mm.group(1).endswith(("_NC", "_R")):             # unconnected stubs and the clock's 0 ohm pad are not signal lines
            fam[mm.group(2)][mm.group(1)] = round(rs[0]["value"] / 1000.0, 2)
    sr = {k[len("series_r."):]: ix[k][0]["value"] for k in ix if k.startswith("series_r.")}
    return {"board_fixed": bool(doc.get("board_fixed")),
            "net_families": {f: {"lengths_in": dict(sorted(v.items(), key=lambda kv: kv[1])),
                                 "note": "carrier copper only (no SOM routing); pick the nets of your ports by hand: the pin-to-net mapping is not in the dump"}
                             for f, v in sorted(fam.items())},
            "series_r_facts": sr,
            "bom_series_resistors": (ix.get("bom.series_resistors") or [{"value": None}])[0]["value"]}


# ---------------------------------------------------------------------------------------------- Allegro owner-run script

ALLEGRO_SCRIPT = """#!/bin/sh
# Owner-run (brief 174): dump an Allegro .brd to CSV (nets, layers, vias) for flow.package ingest.
# Agents must not run this (the auto-mode classifier refuses locally built binaries on vendor CAD files, and the parser is GPL).
# Needs a dump program: KiCad 10's Allegro importer (GPL, kicad/pcbnew/pcb_io/allegro) plus a small dumper that writes
# nets.csv (net,layer,n_segments,n_arcs,length_mm,length_mil,min_width_mil,max_width_mil), net_vias.csv (net,n_vias), layers.csv and meta.txt.
# Set DUMPER to that built binary. Brief 162 used one built from the KiCad sources; it is not committed (GPL, scratch only).
set -e
BRD="{brd}"
OUT="{out}"
DUMPER="${{DUMPER:?set DUMPER to the built dump program}}"
mkdir -p "$OUT"
systemd-run --user --scope -p MemoryMax=4G nice -n 15 "$DUMPER" "$BRD" "$OUT"
echo "wrote $OUT; now: python -m flow.package init {pkg} && python -m flow.package ingest {pkg}"
"""


def allegro_script(pkg: Path) -> Path | None:
    m = load_manifest(pkg)
    brds = [e["path"] for e in m.get("files") or [] if e["kind"] == "board_file" and e["path"].endswith(".brd")]
    if not brds:
        return None
    out = pkg / "board" / "dump_allegro.sh"
    out.write_text(ALLEGRO_SCRIPT.format(brd=str(pkg / brds[0]), out=str(pkg / "board" / "allegro_dump"), pkg=str(pkg)))
    out.chmod(0o755)
    return out


# ---------------------------------------------------------------------------------------------- the existing design

HDL_EXT = (".sv", ".v", ".vh", ".svh", ".vhd", ".vhdl")


def _strip(t: str) -> str:
    t = re.sub(r"/\*.*?\*/", " ", t, flags=re.S)
    return re.sub(r"//[^\n]*", " ", t)


def _balanced(t: str, i: int) -> tuple[str, int]:
    """t[i] == '('; the text inside the balanced parentheses and the index after the closing one."""
    d, j = 0, i
    while j < len(t):
        if t[j] == "(":
            d += 1
        elif t[j] == ")":
            d -= 1
            if d == 0:
                return t[i + 1:j], j + 1
        j += 1
    return t[i + 1:], len(t)


def _split_top(s: str) -> list[str]:
    parts, d, cur = [], 0, ""
    for ch in s:
        if ch in "([{":
            d += 1
        elif ch in ")]}":
            d -= 1
        if ch == "," and d == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    return parts + [cur] if cur.strip() else parts


def parse_verilog(text: str) -> dict[str, Any]:
    """Modules with parameters and ANSI ports (direction, width, name), plus the module names each one instantiates."""
    t = _strip(text)
    if "`pragma protect" in t or "`protect" in t:
        return {"encrypted": True, "modules": {}}
    mods: dict[str, Any] = {}
    spans = []
    for m in re.finditer(r"\bmodule\s+(?:automatic\s+)?(\w+)\s*", t):
        i = m.end()
        params = ""
        if t[i:i + 1] == "#":
            j = t.index("(", i)
            params, i = _balanced(t, j)
            while t[i:i + 1].isspace():
                i += 1
        ports = []
        if t[i:i + 1] == "(":
            body, i = _balanced(t, i)
            cur = {"dir": "", "width": ""}
            for p in _split_top(body):
                p = " ".join(p.split())
                dm = re.match(r"(input|output|inout)\b\s*(.*)", p)
                if dm:
                    cur = {"dir": dm.group(1), "width": ""}
                    p = dm.group(2)
                p = re.sub(r"^(wire|logic|reg|signed|var)\s+", "", p)
                wm = re.match(r"((?:\[[^\]]*\]\s*)+)(.*)", p)
                if wm:
                    cur = {**cur, "width": re.sub(r"\s+", "", wm.group(1))}
                    p = wm.group(2)
                name = re.match(r"(\w+)", p.strip())
                if name and cur["dir"]:
                    ports.append({"name": name.group(1), "dir": cur["dir"], "width": cur["width"]})
        pnames = [" ".join(p.split()) for p in _split_top(params)] if params else []
        mods[m.group(1)] = {"params": pnames, "ports": ports, "instances": []}
        spans.append((m.group(1), i))
    for n, start in spans:
        end = t.find("endmodule", start)
        body = t[start:end if end > 0 else len(t)]
        for im in re.finditer(r"(?m)^\s*(\w+)\s*(?:#\s*\(.*?\)\s*)?(\w+)\s*\(", body, flags=re.S):
            if im.group(1) != n and im.group(1) not in ("module", "if", "else", "for", "case", "assign", "always", "initial", "function", "task", "generate", "begin", "end"):
                mods[n]["instances"].append({"module": im.group(1), "name": im.group(2)})   # candidates: inventory() keeps the ones defined somewhere
    return {"encrypted": False, "modules": mods}


def parse_vhdl(text: str) -> dict[str, Any]:
    t = _strip(re.sub(r"--[^\n]*", " ", text))
    mods: dict[str, Any] = {}
    for m in re.finditer(r"\bentity\s+(\w+)\s+is\b(.*?)\bend\b", t, flags=re.S | re.I):
        ports = []
        pm = re.search(r"\bport\s*\(", m.group(2), re.I)
        if pm:
            body, _ = _balanced(m.group(2), pm.end() - 1)
            for p in body.split(";"):
                pp = re.match(r"\s*([\w,\s]+?)\s*:\s*(in|out|inout|buffer)\s+(.*)", p, re.I | re.S)
                if pp:
                    for n in pp.group(1).split(","):
                        ports.append({"name": n.strip(), "dir": pp.group(2).lower(), "width": " ".join(pp.group(3).split())})
        mods[m.group(1)] = {"params": [], "ports": ports, "instances": []}
    for n in mods:
        for im in re.finditer(r"(\w+)\s*:\s*(?:entity\s+\w+\.)?(\w+)\s*(?:generic|port)\s+map", t, re.I):
            if im.group(2) in mods and im.group(2) != n:
                mods[n]["instances"].append({"module": im.group(2), "name": im.group(1)})
    return {"encrypted": False, "modules": mods}


def parse_timing_summary(text: str) -> dict[str, float] | None:
    m = re.search(r"WNS\(ns\)\s+TNS\(ns\).*?WHS\(ns\)\s+THS\(ns\).*?\n\s*-+.*?\n\s*(-?[\d.]+)\s+(-?[\d.]+)\s+\d+\s+\d+\s+(-?[\d.]+)\s+(-?[\d.]+)", text, re.S)
    return {"wns": float(m.group(1)), "tns": float(m.group(2)), "whs": float(m.group(3)), "ths": float(m.group(4))} if m else None


def parse_utilization(text: str) -> dict[str, int]:
    out = {}
    for name, key in (("Slice LUTs", "lut"), ("CLB LUTs", "lut"), ("LUT as Logic", "lut_logic"), ("Slice Registers", "ff"), ("CLB Registers", "ff"),
                      ("Block RAM Tile", "bram"), ("DSPs", "dsp")):
        m = re.search(r"\|\s*" + re.escape(name) + r"\*?\s*\|\s*(\d+)\s*\|", text)
        if m and key not in out:
            out[key] = int(m.group(1))
    return out


def inventory(ex: Path) -> dict[str, Any]:
    """Top, hierarchy, interfaces, clocks, resets, IP, constraints, last known timing and utilisation, and what could not be read."""
    inv: dict[str, Any] = {"root": "existing", "modules": {}, "unreadable": [], "ip": [], "constraints": [], "files": {}}
    all_mods: dict[str, Any] = {}
    for p in sorted(ex.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        rel = str(p.relative_to(ex))
        inv["files"][rel] = sha256(p)
        ext = p.suffix.lower()
        try:
            if ext in (".sv", ".v", ".vhd", ".vhdl") and "/reports/" not in "/" + rel:
                r = (parse_vhdl if ext in (".vhd", ".vhdl") else parse_verilog)(p.read_text(errors="replace"))
                if r["encrypted"]:
                    inv["unreadable"].append({"file": rel, "why": "encrypted/protected HDL (`pragma protect): interface unknown"})
                for n, mdef in r["modules"].items():
                    mdef["file"] = rel
                    if n in all_mods:
                        inv["unreadable"].append({"file": rel, "why": f"module {n} also defined in {all_mods[n]['file']}"})
                    all_mods[n] = mdef
            elif ext == ".xdc":
                x = parse_xdc(p.read_text(errors="replace"))
                inv["constraints"].append({"file": rel, "ports_with_pins": len(x["pins"]), "clocks": x["clocks"]})
            elif ext == ".xci":
                t = p.read_text(errors="replace")
                v = (re.search(r"<spirit:vendor>([^<]+)", t), re.search(r"<spirit:library>([^<]+)", t), re.search(r"<spirit:name>([^<]+)", t),
                     re.search(r"<spirit:version>([^<]+)", t))
                if all(v):
                    inv["ip"].append({"file": rel, "vlnv": ":".join(m.group(1) for m in v)})
                else:
                    jm = re.search(r'"ip_name"\s*:\s*"([^"]+)".*?"(?:core_version|version)"\s*:\s*"([^"]+)"', t, re.S)
                    inv["ip"].append({"file": rel, "vlnv": f"{jm.group(1)}:{jm.group(2)}"} if jm else {"file": rel, "vlnv": None})
                    if not jm:
                        inv["unreadable"].append({"file": rel, "why": ".xci layout not recognised"})
            elif ext == ".bd":
                inv["unreadable"].append({"file": rel, "why": "block design: kept and frozen as a whole, cells and connections not parsed (the IP versions inside are not inventoried)"})
            elif ext == ".xpr":
                t = p.read_text(errors="replace")
                part = re.search(r'Option Name="Part" Val="([^"]+)"', t)
                inv["project"] = {"file": rel, "part": part.group(1) if part else None,
                                  "sources_listed": len(re.findall(r"<File Path=", t))}
                inv["unreadable"].append({"file": rel, "why": "project-mode project: the flow is non-project; settings (strategies, synth options) are not translated, sources are listed only"})
            elif ext in (".rpt",):
                t = p.read_text(errors="replace")
                ts = parse_timing_summary(t)
                if ts:
                    inv["timing"] = {"file": rel, **ts}
                ut = parse_utilization(t)
                if ut and "timing" not in inv.get("timing", {}):
                    inv.setdefault("utilization", {"file": rel, **ut}) if len(ut) >= 2 else None
            elif ext in (".dcp", ".bit"):
                inv.setdefault("checkpoints", []).append(rel)
        except (OSError, ValueError) as e:
            inv["unreadable"].append({"file": rel, "why": f"read error {e}"})
    for mdef in all_mods.values():
        mdef["instances"] = [i for i in mdef["instances"] if i["module"] in all_mods]
    inv["modules"] = all_mods
    instantiated = {i["module"] for m in all_mods.values() for i in m["instances"]}
    tops = sorted(set(all_mods) - instantiated)
    inv["top"] = tops[0] if len(tops) == 1 else None
    inv["top_candidates"] = tops
    if inv["top"] is None and tops:
        inv["unreadable"].append({"file": "(hierarchy)", "why": f"no single top: candidates {tops}"})
    top = all_mods.get(inv["top"] or "", {"ports": []})
    inv["resets"] = [p["name"] for p in top["ports"] if re.search(r"(?i)rst|reset", p["name"]) and p["dir"] == "input"]
    inv["clock_ports"] = [p["name"] for p in top["ports"] if re.search(r"(?i)(^|_)clk|clock", p["name"]) and p["dir"] == "input"]
    if not any("sv" in f or f.endswith((".v", ".vhd")) for f in inv["files"]):
        inv["unreadable"].append({"file": "(rtl)", "why": "no HDL source found: a netlist-only or block-design-only design cannot be edited by module"})
    return inv


def write_existing(pkg: Path) -> dict[str, Any]:
    """existing_inventory.yaml and the design.yaml marks: every file under existing/ is `owned` (frozen) except the ones that hold a module
    named in package.yaml existing.change (and any file glob in existing.change_files)."""
    m = load_manifest(pkg)
    ex = pkg / "existing"
    inv = inventory(ex)
    ch = (m.get("existing") or {}).get("change") or []
    editable = {inv["modules"][c]["file"] for c in ch if c in inv["modules"]} | set((m.get("existing") or {}).get("change_files") or [])
    for c in ch:
        if c not in inv["modules"]:
            inv["unreadable"].append({"file": "(change list)", "why": f"module {c} named for change is not in the inventory"})
    owned = sorted(f"existing/{f}" for f in inv["files"] if f not in editable)
    inv["editable_files"] = sorted(editable)
    inv["frozen_interfaces"] = {n: md["ports"] for n, md in inv["modules"].items() if md["file"] not in editable}
    inv["generated"] = today()
    (pkg / "existing_inventory.yaml").write_text(
        "# Generated by `python -m flow.package existing`: the inventory of existing/ and the baseline for `frozen-check`.\n" + yaml.dump(inv, Dumper=_NoAlias, sort_keys=False, width=160))
    dy = pkg / "design.yaml"
    d = yaml.safe_load(dy.read_text()) if dy.exists() else {}
    d["owned"] = owned
    d["note"] = "owned: frozen by the package (brief 174): the agent may edit only the files not listed; see existing_inventory.yaml"
    dy.write_text(yaml.dump(d, Dumper=_NoAlias, sort_keys=False, width=160))
    return inv


def frozen_check(pkg: Path, work: Path, timing_before: Path | None = None, timing_after: Path | None = None, tol_ns: float = 0.0) -> list[str]:
    """Violations of the rules, empty when none. `work` is an edited copy of existing/ (same layout)."""
    base = yaml.safe_load((pkg / "existing_inventory.yaml").read_text())
    own = yaml.safe_load((pkg / "design.yaml").read_text()).get("owned") or []
    frozen = {o[len("existing/"):] for o in own}
    bad = []
    for f in sorted(frozen):
        w = work / f
        if not w.exists():
            bad.append(f"frozen file removed: {f}")
        elif sha256(w) != base["files"][f]:
            bad.append(f"frozen file changed: {f}")
    now = inventory(work)
    for n, ports in base["frozen_interfaces"].items():
        got = now["modules"].get(n)
        if got is None:
            bad.append(f"frozen module {n} no longer defined")
        elif got["ports"] != ports:
            bad.append(f"frozen module {n}: interface changed")
    bx = {c["file"]: c for c in base["constraints"]}
    for c in now["constraints"]:
        if c["file"] in bx and c["file"] in frozen:
            continue
        b = bx.get(c["file"])
        if b is None:
            bad.append(f"new constraint file {c['file']} (a new constraint can change a frozen path: review it)")
        elif (b["ports_with_pins"], b["clocks"]) != (c["ports_with_pins"], c["clocks"]):
            bad.append(f"constraint file {c['file']} is editable but its pin count or clocks changed")
    if timing_before and timing_after:
        tb, ta = parse_timing_summary(timing_before.read_text()), parse_timing_summary(timing_after.read_text())
        if not tb or not ta:
            bad.append("timing report not readable (no 'Design Timing Summary' table)")
        else:
            for k in ("wns", "whs"):
                if ta[k] < tb[k] - tol_ns:
                    bad.append(f"timing worse: {k.upper()} {tb[k]} -> {ta[k]} ns")
    return bad


# ---------------------------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m flow.package")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("init", "verify", "gitignore", "ingest", "allegro-script", "existing", "offchip"):
        sub.add_parser(c).add_argument("dir", type=Path)
    pc = sub.add_parser("check")
    pc.add_argument("dir", type=Path)
    pc.add_argument("--board")
    pf = sub.add_parser("frozen-check")
    pf.add_argument("dir", type=Path)
    pf.add_argument("work", type=Path)
    pf.add_argument("--timing-before", type=Path)
    pf.add_argument("--timing-after", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "init":
        m = init(a.dir)
        print(f"{len(m['files'])} files listed in {a.dir}/package.yaml")
    elif a.cmd == "verify":
        bad = verify(a.dir)
        print("\n".join(bad) or "ok")
        return 1 if bad else 0
    elif a.cmd == "gitignore":
        print(f"{len(gitignore(a.dir))} private files git-ignored")
    elif a.cmd == "ingest":
        o = ingest(a.dir)
        print(f"{len(o['facts'])} facts, {len(o['conflicts'])} conflicts, {len(o['not_read'])} not read -> {a.dir}/board_facts.yaml")
    elif a.cmd == "allegro-script":
        s = allegro_script(a.dir)
        print(s or "no .brd file in the manifest")
    elif a.cmd == "existing":
        inv = write_existing(a.dir)
        print(f"top {inv['top']}, {len(inv['modules'])} modules, {len(inv['unreadable'])} unreadable items -> {a.dir}/existing_inventory.yaml, design.yaml")
    elif a.cmd == "offchip":
        print(yaml.dump(offchip_hints(yaml.safe_load((a.dir / "board_facts.yaml").read_text())), Dumper=_NoAlias, sort_keys=False, width=140))
    elif a.cmd == "check":
        m = load_manifest(a.dir)
        name = a.board or m.get("board")
        root = Path(__file__).resolve().parent.parent
        bd = root / "boards" / name
        r = check_board(yaml.safe_load((a.dir / "board_facts.yaml").read_text()), yaml.safe_load((bd / "board.yaml").read_text()), bd,
                        (bd / "board.yaml").read_text())
        print(yaml.dump(r, Dumper=_NoAlias, sort_keys=False, width=140))
        return 1 if r["conflicts"] else 0
    elif a.cmd == "frozen-check":
        bad = frozen_check(a.dir, a.work, a.timing_before, a.timing_after)
        print("\n".join(bad) or "frozen gates: ok")
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
