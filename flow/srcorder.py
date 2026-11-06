"""Source handling shared by simulation, lint, Vivado and the scoring tools (brief 07a2-prep).

- :func:`order_sv`: SystemVerilog sources in dependency order (packages and interfaces before the files that use them),
  not in file-name order. A package ``foo_pkg`` in ``foo_pkg.sv`` used to sort after ``foo_core.sv`` and fail to compile.
  The order is stable: files with no dependency between them keep the order they came in (so the reference ``_``-prefixed
  names, which sort first, still do); a cycle falls back to the input order.
- :func:`no_shell`: a design whose subject is the USB-UART itself (task ``no_shell: true``) is built without the test
  shell, whose ``uart_rx`` / ``uart_tx`` would clash with the design's own. The harness marks such a design with an empty
  file ``.no_shell`` in the design directory; :func:`drop_shell` removes the shell's sources from a list.
- :func:`data_files`: the task's ``data/`` files (copied into ``<design>/data`` at the start of a run).
"""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

ROOT = Path(__file__).resolve().parents[1]
SHELL_DIR = ROOT / "shell" / "rtl"
NO_SHELL_MARKER = ".no_shell"

_DEF = re.compile(r"^\s*(?:package|interface)\s+(?:automatic\s+|static\s+)?([A-Za-z_]\w*)", re.M)
_IMPORT = re.compile(r"\bimport\s+([A-Za-z_]\w*)\s*::")
_SCOPED = re.compile(r"\b([A-Za-z_]\w*)\s*::")
_IFACE_USE = re.compile(r"\b([A-Za-z_]\w*)\s*(?:\.\s*[A-Za-z_]\w*\s+)?[A-Za-z_]\w*\s*(?:\(|,|\)|;)")
_COMMENTS = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
_STRINGS = re.compile(r'"(?:\\.|[^"\\])*"')


def _text(p: Path) -> str:
    try:
        t = p.read_text(errors="replace")
    except OSError:
        return ""
    return _STRINGS.sub('""', _COMMENTS.sub(" ", t))


def order_sv(files: Iterable[Path | str]) -> list[Path]:
    """``files`` ordered so that every package or interface comes before the files that import or use it."""
    paths = [Path(f) for f in files]
    texts = [_text(p) for p in paths]
    defs: dict[str, int] = {}
    for i, t in enumerate(texts):
        for n in _DEF.findall(t):
            defs.setdefault(n, i)
    if not defs:
        return paths
    deps: list[list[int]] = []
    for i, t in enumerate(texts):
        need = set(_IMPORT.findall(t)) | set(_SCOPED.findall(t))
        need |= {n for n in _IFACE_USE.findall(t) if n in defs}
        deps.append(sorted({defs[n] for n in need if n in defs and defs[n] != i}))
    out: list[int] = []
    state: dict[int, int] = {}                          # 1 = in progress, 2 = done

    def visit(i: int) -> None:
        if state.get(i):
            return                                      # done, or a cycle: keep the input order
        state[i] = 1
        for d in deps[i]:
            visit(d)
        state[i] = 2
        out.append(i)

    for i in range(len(paths)):
        visit(i)
    return [paths[i] for i in out]


def no_shell(design: Path | str) -> bool:
    return (Path(design) / NO_SHELL_MARKER).is_file()


def is_shell_source(p: Path | str) -> bool:
    """A file of the test shell's rtl directory (this repo's, or a replay copy of it: any ``shell/rtl`` directory)."""
    try:
        d = Path(p).resolve().parent
    except OSError:
        return False
    return d == SHELL_DIR.resolve() or (d.name == "rtl" and d.parent.name == "shell")


def drop_shell(files: Iterable[Path | str]) -> list[Path]:
    return [Path(f) for f in files if not is_shell_source(f)]


def design_of(test_dir: Path | str) -> Path:
    """A design's tests directory -> the design directory."""
    return Path(test_dir).resolve().parent


def data_files(design: Path | str) -> list[Path]:
    d = Path(design) / "data"
    return sorted(p for p in d.rglob("*") if p.is_file()) if d.is_dir() else []


@contextmanager
def linked_data(data_dir: Path | str, cwd: Path | str) -> Iterator[list[Path]]:
    """The task's data files in the simulator's working directory for the length of a simulation.

    cocotb's runner starts the simulator in its ``test_dir`` (the bench's directory), so ``$readmemh("x.hex")`` opens
    ``<cwd>/x.hex``. Each file of ``data_dir`` is linked as ``<cwd>/data/<name>`` and ``<cwd>/<name>`` (so both spellings
    work); only links that did not exist are made, and exactly those are removed afterwards (also on an error)."""
    root, cwd = Path(data_dir), Path(cwd)
    made: list[Path] = []
    made_dirs: list[Path] = []
    try:
        if root.is_dir():
            for f in sorted(p for p in root.rglob("*") if p.is_file()):
                rel = f.relative_to(root)
                for dst in (cwd / "data" / rel, cwd / rel):
                    if os.path.lexists(dst):
                        continue
                    if not dst.parent.exists():
                        dst.parent.mkdir(parents=True)
                        made_dirs.append(dst.parent)
                    dst.symlink_to(f.resolve())
                    made.append(dst)
        yield made
    finally:
        for dst in made:
            dst.unlink(missing_ok=True)
        for d in reversed(made_dirs):
            try:
                d.rmdir()
            except OSError:
                pass
