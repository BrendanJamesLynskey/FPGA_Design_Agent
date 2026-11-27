"""The `dma_coherency` check (brief 241, advisory): a design that moves Processing System memory through a non-coherent port needs a software
cache contract, and the spec has to say what it is.

On Zynq, the PL reaches the processors' DDR through the PS slave ports. The high-performance ports (Zynq-7000 S_AXI_HP0-3, Zynq UltraScale+
S_AXI_HP0-3_FPD) do not snoop the processors' caches: software must clean (flush) a buffer the PL will read and invalidate a buffer the PL has
written, or the PL reads stale data and the processor reads stale data (UG585 and UG1085, the PS-PL interface chapters; the KB skills
`zynq-cache-coherency-for-dma` and `zynq7000-hp-and-acp-port-behaviour`). The coherent ports (S_AXI_ACP, UltraScale+ S_AXI_HPC0/1_FPD) snoop only
when the transfers are marked coherent (AxCACHE and AxUSER on the Zynq-7000, AxCACHE and the CCI snoop enable on the UltraScale+), so a design
that names one still needs to say that its master does so.

The check reads two things: the design's spec.yaml section

    dma:
      ps_memory_port: S_AXI_HP0            # or a list; the PS port the PL master reaches PS memory through
      cache_contract: software_flush_invalidate   # software_flush_invalidate | hardware_coherent | none_needed (with a reason: text after a colon)

and, in the design's sources (every language, text only), the port names. Findings (advisory, never blocking):

- DMA-COH-01: a non-coherent port is named and the spec has no `dma.cache_contract` (top-level `cache_contract` is read too);
- DMA-COH-02: the contract is `hardware_coherent` but every PS port named is non-coherent.

What it does not do: it cannot tell what the processors do with the buffers, whether the driver really flushes and invalidates, or whether a
master drives AxCACHE and AxUSER for the coherent ports; the contract is a statement to be reviewed, not a proof."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

CODES = ("DMA-COH-01", "DMA-COH-02")
NONCOH = re.compile(r"\b(?:S_AXI_HP[0-3](?:_FPD)?|saxihp[0-3]|SAXIHP[0-3])\w*", re.I)
COH = re.compile(r"\b(?:S_AXI_ACP(?:_FPD)?|S_AXI_HPC[01](?:_FPD)?|saxiacp|saxihpc[01])\w*", re.I)
CONTRACTS = ("software_flush_invalidate", "hardware_coherent", "none_needed")
FIX = {
    "DMA-COH-01": "add `dma: {ps_memory_port: <port>, cache_contract: software_flush_invalidate}` to spec.yaml and make the driver clean a buffer before the PL reads it and "
                  "invalidate it after the PL writes it (or use a coherent port, ACP or HPC, with the master marking its transfers coherent, and say hardware_coherent)",
    "DMA-COH-02": "use a coherent port (S_AXI_ACP, or S_AXI_HPC0/1_FPD with snooping enabled) or change the contract to software_flush_invalidate",
}


def _spec(design: Path) -> dict[str, Any]:
    try:
        d = yaml.safe_load((design / "spec.yaml").read_text())
    except (OSError, yaml.YAMLError):
        return {}
    return d if isinstance(d, dict) else {}


def _ports(spec: dict[str, Any]) -> list[str]:
    d = spec.get("dma")
    p = d.get("ps_memory_port") if isinstance(d, dict) else None
    return [str(x) for x in (p if isinstance(p, list) else [p] if p else [])]


def _contract(spec: dict[str, Any]) -> str:
    d = spec.get("dma")
    c = (d.get("cache_contract") if isinstance(d, dict) else None) or spec.get("cache_contract")
    return str(c).strip() if c else ""


def _texts(design: Path, sources: list[Path]) -> dict[str, str]:
    files = {p for p in sources if p.is_file()}
    files |= {p for p in design.glob("*.tcl")} | {p for p in (design / "bd").glob("**/*") if p.is_file()} if (design / "bd").exists() else {p for p in design.glob("*.tcl")}
    out = {}
    for p in sorted(files):
        try:
            out[str(p)] = p.read_text(errors="replace")
        except OSError:
            continue
    return out


def scan(design: Path, sources: list[Path]) -> tuple[set[str], set[str]]:
    """(non-coherent, coherent) PS port names found in the spec and the sources, upper-cased."""
    nc, co = set(), set()
    for name in _ports(_spec(design)):
        (co if COH.search(name) else nc if NONCOH.search(name) else set()).add(name.upper())
    for text in _texts(design, sources).values():
        nc |= {m.group(0).upper() for m in NONCOH.finditer(text)}
        co |= {m.group(0).upper() for m in COH.finditer(text)}
    return nc, co


def run_checks(design: Path, sources: list[Path]) -> list[dict[str, Any]]:
    spec = _spec(design)
    nc, co = scan(design, sources)
    contract = _contract(spec)
    fs: list[dict[str, Any]] = []

    def f(code: str, msg: str, where: str) -> dict[str, Any]:
        return {"tool": "dma_coherency", "code": code, "severity": "advisory", "where": where, "key": f"dma_coherency:{code} {where}",
                "message": msg, "fix": FIX[code], "blocking": False}

    if nc and not contract:
        fs.append(f("DMA-COH-01", f"PS memory is reached through non-coherent port(s) {', '.join(sorted(nc))} and the spec declares no software cache contract: "
                    "the processors' caches are not snooped, so a buffer the PL reads may be stale in DDR and a buffer the PL writes may be hidden behind stale cache lines", "spec.yaml dma"))
    if contract.split(":")[0].strip() == "hardware_coherent" and nc and not co:
        fs.append(f("DMA-COH-02", f"the contract is hardware_coherent but the only PS port(s) named, {', '.join(sorted(nc))}, are not coherent", "spec.yaml dma"))
    return fs


def applies(design: Path, sources: list[Path]) -> str | None:
    nc, co = scan(design, sources)
    if nc or co or isinstance(_spec(design).get("dma"), dict):
        return None
    return "no PS memory port named in the sources and no dma: section in spec.yaml"
