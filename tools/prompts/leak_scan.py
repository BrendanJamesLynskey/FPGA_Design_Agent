#!/usr/bin/env python3
"""Scan the tracked files of this repository for prompt text that has moved to the private repository (brief 99).

    python3 tools/prompts/leak_scan.py [--prompts-dir DIR] [--words 8]

Every run of ``--words`` consecutive words (case-folded, whitespace-normalised) of every prompt in the manifest is a
fingerprint; a tracked text file that contains one is reported with its path and line number, **never the text**. Exit 1
if anything is found. Prompts shorter than the window are fingerprinted whole. Used by the test
``agent/tests/test_99_prompts.py::test_no_prompt_text_in_the_public_repo`` (skipped where the private prompts are absent).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent.core import prompts as P  # noqa: E402

WORD = re.compile(r"\S+")
MAX_BYTES = 8_000_000


def fingerprints(root: Path, n: int) -> dict[tuple[str, ...], str]:
    fp: dict[tuple[str, ...], str] = {}
    for name in P.names(root=root):
        words = [w.casefold() for w in WORD.findall(P.load(name, root=root))]
        if len(words) < 4:
            continue                                       # too short to say anything about
        for i in range(max(1, len(words) - n + 1)):
            fp.setdefault(tuple(words[i:i + n]), name)
    return fp


def scan(root: Path, n: int = 8, files: list[Path] | None = None) -> list[tuple[str, int, str]]:
    fp = fingerprints(root, n)
    if files is None:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
        files = [ROOT / p for p in out.decode().split("\0") if p]
    hits: list[tuple[str, int, str]] = []
    for f in files:
        try:
            if not f.is_file() or f.stat().st_size > MAX_BYTES:
                continue
            raw = f.read_bytes()
            if b"\0" in raw[:4096]:
                continue
            text = raw.decode("utf-8", "ignore")
        except OSError:
            continue
        toks = [(m.group().casefold(), m.start()) for m in WORD.finditer(text)]
        words = [t[0] for t in toks]
        for i in range(max(1, len(words) - n + 1)):
            key = tuple(words[i:i + n])
            if key in fp:
                hits.append((str(f.relative_to(ROOT)), text.count("\n", 0, toks[i][1]) + 1, fp[key]))
                break                                      # one hit per file is enough to fail; the first is reported
    return hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--prompts-dir", type=Path, default=None)
    ap.add_argument("--words", type=int, default=8)
    a = ap.parse_args(argv)
    hits = scan(a.prompts_dir or P.prompts_dir(), a.words)
    for path, line, name in hits:
        print(f"{path}:{line}: contains text of private prompt {name}")
    print(f"{len(hits)} file(s) with prompt text")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
