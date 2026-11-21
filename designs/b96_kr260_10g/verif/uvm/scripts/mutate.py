#!/usr/bin/env python3
"""Make a mutated copy of the b96 PCS/MAC RTL for the UVM bench's mutation run (brief 112).

    mutate.py list                         ids and descriptions
    mutate.py make <id> <rtl dir> <dest>   copy <rtl dir> to <dest> and apply the edits of mutant <id>

Each edit's old text must occur exactly once in its file, so a change to the RTL that moves the target breaks the mutant loudly instead of
silently producing an unmutated copy. The mutants live in mutants/mutants.tsv; nothing in the design's rtl/ is touched."""
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def rows():
    out = []
    for line in (HERE / "mutants" / "mutants.tsv").read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        mid, fn, old, new, what = line.split("\t")
        out.append((mid, fn, old.replace("\\n", "\n"), new.replace("\\n", "\n"), what))
    return out


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "list":
        seen = {}
        for mid, fn, _o, _n, what in rows():
            seen.setdefault(mid, (fn, what))
        for mid, (fn, what) in seen.items():
            print(f"{mid}\t{fn}\t{what}")
        return 0
    if len(argv) == 5 and argv[1] == "make":
        mid, src, dst = argv[2], Path(argv[3]), Path(argv[4])
        edits = [r for r in rows() if r[0] == mid]
        if not edits:
            print(f"no mutant {mid}")
            return 2
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        for _mid, fn, old, new, _what in edits:
            p = dst / fn
            text = p.read_text()
            if text.count(old) != 1:
                print(f"mutant {mid}: old text occurs {text.count(old)} times in {fn} (need exactly 1): {old!r}")
                return 3
            p.write_text(text.replace(old, new))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
