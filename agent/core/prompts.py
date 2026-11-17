"""Prompt text as private data (brief 99): ``load(name)`` reads a prompt from the ``prompts/`` directory of the private
knowledge repository ``FPGA_Design_Agent_Knowledge``; the public repository keeps no prompt text.

Layout in the private repository::

    prompts/MANIFEST.json   {"version": 1, "prompts": {"<name>": {"file": "<name>.txt", "sha256": "<hex>", "bytes": N}}}
    prompts/<name>.txt      the prompt, UTF-8, returned byte for byte (no newline or whitespace changes)

Names are ``/``-separated lowercase words (``graph/interview/clarifier``); a name maps to ``<name>.txt``.

Pinning (like the knowledge packs, ``knowledge/PACKS.md``): ``agent/core/prompts_pin.json`` in this repository holds the
private repository's commit and the SHA-256 of ``MANIFEST.json`` **only**, never prompt text. ``load`` refuses a
manifest whose hash is not the pinned one and a file whose hash is not the manifest's, so a scored run reads exactly the
prompts it was pinned to. While nothing is pinned (``manifest_sha256`` null: stage 0, nothing moved yet) the manifest
hash is not compared; each file is still checked against the manifest. ``FDA_PROMPTS_UNPINNED=1`` skips the pin
comparison for development on a prompt change (the file-to-manifest check stays); ``provenance()`` says which was used.

Where the directory is: ``$FDA_PROMPTS_DIR``, else ``<knowledge checkout>/prompts`` (the checkout the knowledge packs
use, ``$FDA_KNOWLEDGE`` or the sibling ``FPGA_Design_Agent_Knowledge``). CI fetches it with a read-only token
(``docs/private_parts_plan.md``).

There is no committed fallback text: a prompt that cannot be read is :class:`PromptUnavailable` (the run refuses, it
does not carry on with different text), so behaviour never changes silently. Callers format the returned text themselves.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path

from agent.core.bank import DEFAULT_BANK

PIN_FILE = Path(__file__).resolve().parent / "prompts_pin.json"
NAME_RE = re.compile(r"^[a-z0-9_]+(/[a-z0-9_]+)*$")
ENV_DIR = "FDA_PROMPTS_DIR"
ENV_UNPINNED = "FDA_PROMPTS_UNPINNED"


class PromptUnavailable(Exception):
    """The prompt cannot be read, or fails its hash. The message names the prompt and the reason, never prompt text."""


def prompts_dir() -> Path:
    return Path(os.environ[ENV_DIR]) if os.environ.get(ENV_DIR) else Path(DEFAULT_BANK) / "prompts"


def read_pin(path: Path | None = None) -> dict:
    return json.loads((path or PIN_FILE).read_text())


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _manifest(root: Path, pin: dict) -> dict:
    mf = root / "MANIFEST.json"
    try:
        raw = mf.read_bytes()
    except OSError:
        raise PromptUnavailable(f"prompt manifest not found at {mf}: set {ENV_DIR} or check out the private knowledge "
                                f"repository at the pinned commit") from None
    want = pin.get("manifest_sha256")
    if (pin.get("kb_commit") or pin.get("names")) and not (isinstance(want, str) and re.fullmatch(r"[0-9a-f]{64}", want)):
        raise PromptUnavailable("the pin names a private commit or prompts but has no valid manifest_sha256: pin is incomplete")
    if want and os.environ.get(ENV_UNPINNED) != "1" and _sha(raw) != want:
        raise PromptUnavailable(f"prompt manifest hash {_sha(raw)[:12]} is not the pinned {want[:12]} "
                                f"(private repository commit {str(pin.get('kb_commit'))[:12]}); re-pin or check out the pin")
    try:
        data = json.loads(raw)
        return dict(data["prompts"])
    except (ValueError, KeyError, TypeError):
        raise PromptUnavailable("prompt manifest is not valid") from None


def load(name: str, *, root: Path | None = None, pin: dict | None = None) -> str:
    """The prompt called ``name``, exactly as stored. Raises :class:`PromptUnavailable`; never returns other text."""
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise PromptUnavailable(f"bad prompt name {name!r}: lowercase words separated by '/'")
    root = Path(root) if root else prompts_dir()
    entries = _manifest(root, pin if pin is not None else read_pin())
    ent = entries.get(name)
    if ent is None:
        raise PromptUnavailable(f"prompt {name!r} is not in the manifest")
    if not (isinstance(ent, dict) and isinstance(ent.get("file"), str) and isinstance(ent.get("sha256"), str)):
        raise PromptUnavailable(f"prompt {name!r}: manifest entry is not valid")
    f = root / ent["file"]
    try:
        f.resolve().relative_to(root.resolve())
    except ValueError:
        raise PromptUnavailable(f"prompt {name!r}: file path leaves the prompts directory") from None
    try:
        raw = f.read_bytes()
    except OSError:
        raise PromptUnavailable(f"prompt {name!r}: file {ent['file']} is missing") from None
    if _sha(raw) != ent["sha256"]:
        raise PromptUnavailable(f"prompt {name!r}: file hash {_sha(raw)[:12]} is not the manifest's {ent['sha256'][:12]}")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise PromptUnavailable(f"prompt {name!r}: file is not valid UTF-8") from None


def names(*, root: Path | None = None, pin: dict | None = None) -> list[str]:
    return sorted(_manifest(Path(root) if root else prompts_dir(), pin if pin is not None else read_pin()))


def verify_all(*, root: Path | None = None, pin: dict | None = None) -> int:
    """Load every manifest entry (hash-checked); returns how many. Raises on the first failure."""
    for n in names(root=root, pin=pin):
        load(n, root=root, pin=pin)
    return len(names(root=root, pin=pin))


def provenance(*, root: Path | None = None, pin: dict | None = None) -> dict:
    """What a run record may carry: the pin and whether it was enforced. Hashes and a commit, no prompt text."""
    pin = pin if pin is not None else read_pin()
    root = Path(root) if root else prompts_dir()
    try:
        mh = _sha((root / "MANIFEST.json").read_bytes())
    except OSError:
        mh = None
    return {"kb_commit": pin.get("kb_commit"), "pinned_manifest_sha256": pin.get("manifest_sha256"),
            "manifest_sha256": mh, "enforced": bool(pin.get("manifest_sha256")) and os.environ.get(ENV_UNPINNED) != "1"}


class LazyDict(Mapping):
    """A read-only dict of prompts, each loaded on first access (``prefix + "_" + key``). Keeps ``PROMPTS["rtl"]`` working
    without reading the private repository at import time, so importing the agent never needs it."""

    def __init__(self, prefix: str, keys: tuple[str, ...]):
        self._prefix, self._keys = prefix, tuple(keys)

    def __getitem__(self, key: str) -> str:
        if key not in self._keys:
            raise KeyError(key)
        return load(f"{self._prefix}_{key}")

    def __iter__(self):
        return iter(self._keys)

    def __len__(self) -> int:
        return len(self._keys)


def module_getattr(module: str, constants: dict[str, str]):
    """For a module's ``__getattr__`` (PEP 562): ``X = module_getattr(__name__, {"CONVENTIONS": "graph/run/conventions"})``
    makes ``module.CONVENTIONS`` (and ``from module import CONVENTIONS``) load the prompt on first use."""
    def __getattr__(attr: str):
        if attr in constants:
            return load(constants[attr])
        raise AttributeError(f"module {module!r} has no attribute {attr!r}")
    return __getattr__


class Lazy:
    """A class attribute that loads a prompt when read (``SYSTEM = Lazy("graph/interview/oracle_system")``)."""

    def __init__(self, name: str):
        self.name = name

    def __get__(self, obj, owner=None) -> str:
        return load(self.name)
