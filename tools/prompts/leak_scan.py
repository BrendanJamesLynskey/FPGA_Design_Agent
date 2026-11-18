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
import bz2
import gzip
import io
import lzma
import re
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent.core import prompts as P  # noqa: E402

WORD = re.compile(r"\S+")
MAX_BYTES = 8_000_000
#: archives (.tar.gz, .tgz, .tar, .gz, .zip, .bz2, .xz) are opened and every text member is scanned; a hit is reported as
#: ``archive!member``. The allow-list never covers an archive: an archive that carries prompt text is always a failure, and the
#: remedy is to move it to the private repository (brief 99 step 2). A member over MAX_BYTES is not read, a nest deeper than
#: MAX_DEPTH is not opened, and an archive that cannot be opened or is over MAX_ARCHIVE_BYTES is listed by
#: ``unreadable_archives``, which the test fails on, so nothing passes by being unread.
MAX_ARCHIVE_BYTES = 400_000_000
MAX_DEPTH = 3
TAR_SUFFIXES = (".tar.gz", ".tgz", ".tar", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")
ARCHIVE_SUFFIXES = TAR_SUFFIXES + (".gz", ".zip", ".bz2", ".xz")
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


def is_archive(name: str) -> bool:
    return name.lower().endswith(ARCHIVE_SUFFIXES)


def _members(name: str, raw: bytes, depth: int = 0, errs: list | None = None):
    """Yield ``(label, bytes)`` for every member of the archive ``raw`` (a single compressed file is one member); nested archives
    are opened up to MAX_DEPTH. Anything that cannot be read (corrupt or encrypted archive, member over MAX_BYTES, nest deeper than
    MAX_DEPTH) is appended to ``errs`` as a label, which ``unreadable_archives`` turns into a failure."""
    errs = errs if errs is not None else []
    low = name.lower()
    try:
        if low.endswith(TAR_SUFFIXES):
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as tf:
                for m in tf:
                    if not m.isfile():
                        continue
                    if m.size > MAX_BYTES:
                        errs.append(f"{name}!{m.name}")
                    elif (fh := tf.extractfile(m)) is not None:
                        yield from _member(f"{name}!{m.name}", fh.read(), depth, errs)
        elif low.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                for zi in zf.infolist():
                    if zi.is_dir():
                        continue
                    if zi.file_size > MAX_BYTES:
                        errs.append(f"{name}!{zi.filename}")
                    else:
                        yield from _member(f"{name}!{zi.filename}", zf.read(zi), depth, errs)
        else:
            op = {".gz": gzip.decompress, ".bz2": bz2.decompress}.get(low[low.rfind("."):], lzma.decompress)
            data = op(raw)
            if len(data) > MAX_BYTES:
                errs.append(name)
            else:
                yield from _member(f"{name}!{low.rsplit('/', 1)[-1].rsplit('.', 1)[0]}", data, depth, errs)
    except (tarfile.TarError, zipfile.BadZipFile, OSError, EOFError, lzma.LZMAError, ValueError, NotImplementedError, RuntimeError):
        errs.append(name)


def _member(label: str, data: bytes, depth: int, errs: list):
    if is_archive(label):
        if depth < MAX_DEPTH:
            yield from _members(label, data, depth + 1, errs)
        else:
            errs.append(label)
    yield label, data


def unreadable_archives(files: list[Path]) -> list[str]:
    """Tracked archives (or members of them) the scan cannot read in full: corrupt, encrypted, too deep, or over a size cap. Paths only."""
    bad: list[str] = []
    for f in files:
        if not is_archive(f.name) or not f.is_file():
            continue
        try:
            if f.stat().st_size > MAX_ARCHIVE_BYTES:
                bad.append(_rel(f))
                continue
            for _ in _members(_rel(f), f.read_bytes(), 0, bad):
                pass
        except OSError:
            bad.append(_rel(f))
    return bad


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


def _texts(files: list[Path]):
    """``(label, text)`` of every readable text file, and of every text member of every archive among ``files``."""
    for f in files:
        try:
            if not f.is_file():
                continue
            if is_archive(f.name):
                if f.stat().st_size <= MAX_ARCHIVE_BYTES:
                    for label, data in _members(_rel(f), f.read_bytes()):
                        if b"\0" not in data[:4096]:
                            yield label, data.decode("utf-8", "ignore")
                continue
            if f.stat().st_size > MAX_BYTES:
                continue
            raw = f.read_bytes()
        except OSError:
            continue
        if b"\0" not in raw[:4096]:
            yield _rel(f), raw.decode("utf-8", "ignore")


def scan(root: Path | None, n: int = DEFAULT_WORDS, files: list[Path] | None = None, allow: list[str] | None = None,
         texts: dict[str, str] | None = None) -> list[tuple[str, int, str]]:
    """Hits as ``(path, line, prompt name)``. The prompts come from ``texts`` (name -> text) when given, else from the prompts
    directory ``root``."""
    fp = fingerprints_of(texts, n) if texts is not None else fingerprints(root, n)
    if files is None:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
        files = [ROOT / p for p in out.decode().split("\0") if p]
    allow = allow or []
    files = [f for f in files if is_archive(f.name)
             or not any(_rel(f) == a or (a.endswith("/") and _rel(f).startswith(a)) for a in allow)]
    hits: list[tuple[str, int, str]] = []
    for label, text in _texts(files):
        toks = [(m.group().casefold(), m.start()) for m in WORD.finditer(text)]
        words = [t[0] for t in toks]
        for i in range(max(1, len(words) - n + 1)):
            key = tuple(words[i:i + n])
            if key in fp:
                hits.append((label, text.count("\n", 0, toks[i][1]) + 1, fp[key]))
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
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    bad = unreadable_archives([ROOT / p for p in out.decode().split("\0") if p])
    for path in bad:
        print(f"{path}: archive could not be read or is too large to scan")
    arch = sorted({h[0].split("!")[0] for h in hits if "!" in h[0]})
    print(f"{len(hits)} file(s) with prompt text ({len(arch)} archive(s)); {len(bad)} unreadable archive(s)")
    return 1 if hits or bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
