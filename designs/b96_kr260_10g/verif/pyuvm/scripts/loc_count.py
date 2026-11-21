#!/usr/bin/env python3
"""Lines of code per component, brief 112's SystemVerilog UVM bench against this pyuvm bench (brief 123): `loc_count.py > loc.tsv`.
Columns: component, SV files, SV total lines, SV code lines (not blank, not a comment-only line), Python files, Python total lines, Python code lines.
The Python bench reuses model/pcs.py (333 lines, not counted: 112's SystemVerilog models are a port of it) and the cocotb/pyuvm/cocotb-coverage libraries."""
from __future__ import annotations

from pathlib import Path

VERIF = Path(__file__).resolve().parents[2]
UVM, PY = VERIF / "uvm", VERIF / "pyuvm"

# component -> (SystemVerilog files, Python files)
PAIRS = {
    "hardware top, interfaces, channel": (["tb/tb_uvm_top.sv", "tb/pcs_mac_ifs.sv", "tb/line_channel.sv"], ["tb/tb_pyuvm_top.sv", "pcs_mac_pyuvm/channel.py"]),
    "agents (drivers, monitors, sequencers)": (["env/pcs_mac_agents.sv"], ["pcs_mac_pyuvm/agents.py"]),
    "sequence items": (["env/pcs_mac_items.sv"], ["pcs_mac_pyuvm/items.py"]),
    "reference models": (["ref/pcs_ref_pkg.sv"], ["pcs_mac_pyuvm/refmodels.py"]),
    "scoreboard": (["env/pcs_mac_scoreboard.sv"], ["pcs_mac_pyuvm/scoreboard.py"]),
    "functional coverage": (["env/pcs_mac_cov.sv", "scripts/cov_merge.py"], ["pcs_mac_pyuvm/cov.py"]),
    "sequences (directed + random)": (["env/pcs_mac_seqs.sv"], ["pcs_mac_pyuvm/seqs.py"]),
    "env, tests, package": (["env/pcs_mac_env.sv", "tests/pcs_mac_tests.sv", "pcs_mac_uvm_pkg.sv"], ["pcs_mac_pyuvm/env.py", "pcs_mac_pyuvm/__init__.py", "tests/pcs_mac_pyuvm_cocotb.py"]),
    "assertions / protocol checks": (["sva/pcs_mac_sva.sv"], ["pcs_mac_pyuvm/checker.py"]),
    "build, regression and mutation scripts (mutate.py and mutants.tsv are shared, not counted)": (["scripts/run_regress.sh", "scripts/uvm_build.sh"], ["scripts/run_regress.py", "scripts/pyuvm_run.py"]),
}


def count(path: Path) -> tuple[int, int]:
    lines = path.read_text(errors="replace").splitlines()
    cm = ("//",) if path.suffix in (".sv", ".v") else ("#",)
    code = 0
    in_doc = False
    for l in lines:
        s = l.strip()
        if path.suffix == ".py" and s.count('"""') == 1:
            in_doc = not in_doc
            continue
        if in_doc or not s or s.startswith(cm) or (path.suffix == ".py" and s.startswith('"""') and s.endswith('"""') and len(s) > 5):
            continue
        code += 1
    return len(lines), code


def main() -> None:
    print("component\tsv_files\tsv_lines\tsv_code\tpy_files\tpy_lines\tpy_code")
    tot = [0, 0, 0, 0]
    for comp, (sv, py) in PAIRS.items():
        a = [count(UVM / f) for f in sv]
        b = [count(PY / f) for f in py]
        row = [sum(x[0] for x in a), sum(x[1] for x in a), sum(x[0] for x in b), sum(x[1] for x in b)]
        tot = [t + r for t, r in zip(tot, row)]
        print(f"{comp}\t{len(sv)}\t{row[0]}\t{row[1]}\t{len(py)}\t{row[2]}\t{row[3]}")
    print(f"TOTAL\t\t{tot[0]}\t{tot[1]}\t\t{tot[2]}\t{tot[3]}")
    pcs = VERIF.parent / "model" / "pcs.py"
    n, c = count(pcs)
    print(f"model/pcs.py (reused by the Python bench, not in the total)\t\t\t\t1\t{n}\t{c}")


if __name__ == "__main__":
    main()
