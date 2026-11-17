#!/usr/bin/env python3
"""Scan the tracked files of this repository for prompt text that has moved to the private repository (brief 99).

    python3 tools/prompts/leak_scan.py [--prompts-dir DIR] [--words 12] [--allow FILE]

Every run of ``--words`` (default 12) consecutive words (case-folded, whitespace-normalised) of every prompt in the manifest is a
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
#: 12 words: the harness's own questions and gate messages are recorded in run records by design, and a model's replies reuse
#: the prompts' vocabulary; at 8 words that shared wording matched in ~100 files, at 12 only verbatim dumps and the code that
#: is the source of a prompt fragment match. A dump of any prompt longer than 12 words is always caught.
DEFAULT_WORDS = 12


def fingerprints_of(texts: dict[str, str], n: int) -> dict[tuple[str, ...], str]:
    """``{window: name}`` for named texts (the prompts), ``n`` words per window."""
    fp: dict[tuple[str, ...], str] = {}
    for name, text in texts.items():
        words = [w.casefold() for w in WORD.findall(text)]
        if len(words) < 4:
            continue                                       # too short to say anything about
        for i in range(max(1, len(words) - n + 1)):
            fp.setdefault(tuple(words[i:i + n]), name)
    return fp


def fingerprints(root: Path, n: int) -> dict[tuple[str, ...], str]:
    return fingerprints_of({name: P.load(name, root=root) for name in P.names(root=root)}, n)


def _rel(f: Path) -> str:
    return str(f.relative_to(ROOT)) if ROOT in f.parents else str(f)


def read_allow(path: Path | None) -> list[str]:
    """``tools/prompts/leak_allow.txt``: one tracked path (or a prefix ending in ``/``) per line, then ``#`` and the reason; a line
    without a reason is an error, so every deliberate residual says why it stays."""
    out = []
    if path is None or not path.is_file():
        return out
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        p, _, why = line.partition("#")
        if not why.strip():
            raise SystemExit(f"{path}:{n}: an allow-list entry needs a reason after '#'")
        out.append(p.strip())
    return out


def scan(root: Path | None, n: int = DEFAULT_WORDS, files: list[Path] | None = None, allow: list[str] | None = None,
         texts: dict[str, str] | None = None) -> list[tuple[str, int, str]]:
    """Hits as ``(path, line, prompt name)``. The prompts come from ``texts`` (name -> text) when given, else from the prompts
    directory ``root``."""
    fp = fingerprints_of(texts, n) if texts is not None else fingerprints(root, n)
    if files is None:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
        files = [ROOT / p for p in out.decode().split("\0") if p]
    allow = allow or []
    files = [f for f in files if not any(_rel(f) == a or (a.endswith("/") and _rel(f).startswith(a)) for a in allow)]
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
                hits.append((_rel(f), text.count("\n", 0, toks[i][1]) + 1, fp[key]))
                break                                      # one hit per file is enough to fail; the first is reported
    return hits


def main(argv=None) -> int:
    from agent.access import require_or_exit            # it reads the private prompts: same gate as the agent's entry points
    require_or_exit("leak_scan")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--prompts-dir", type=Path, default=None)
    ap.add_argument("--allow", type=Path, default=ROOT / "tools" / "prompts" / "leak_allow.txt")
    ap.add_argument("--words", type=int, default=DEFAULT_WORDS)
    a = ap.parse_args(argv)
    hits = scan(a.prompts_dir or P.prompts_dir(), a.words, allow=read_allow(a.allow))
    for path, line, name in hits:
        print(f"{path}:{line}: contains text of private prompt {name}")
    print(f"{len(hits)} file(s) with prompt text")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
