"""Hybrid skill retrieval over the frozen knowledge bank (brief 36): BM25 plus optional embeddings, fused by rank.

The index answers "which skills are about this?" with **names and one-line descriptions**, so a role can see a ranked
shortlist without the bodies, then load one body (``load_skill(name=...)``) or one section of it
(``skill_excerpt(name, heading)``). Three ways to run it, chosen by :func:`open_index`:

- **in-process BM25** (always available; what CI and a bank without vectors get);
- **in-process hybrid**: BM25 plus cosine similarity against the bank's committed vectors
  (``<bank>/indexes/skill_vectors.npz``), when ``fastembed`` is importable to embed the query;
- **service**: ``FDA_SKILL_INDEX_URL`` names the container in ``infra/skill_index/`` (same code, same vectors), which
  embeds the query there, so the agent's own environment needs no model.

Vectors are computed only on the owner's PC or through an API (owner rule, 2026-11-10: never on a work machine), with
``python -m agent.core.skill_index build``; the manifest records the model and each skill's SHA-256, and a skill whose
text changed since is searched by BM25 alone until the vectors are rebuilt (never against a stale vector).

Skill text is untrusted data: nothing here interprets it, it is only tokenised and embedded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

EMBED_MODEL = "BAAI/bge-small-en-v1.5"          # MIT; 384 dimensions; runs on a CPU in fastembed (Apache-2.0)
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "     # bge's retrieval instruction
VECTORS = "indexes/skill_vectors.npz"
MANIFEST = "indexes/skill_vectors.json"
RRF_K = 60                                       # reciprocal-rank fusion constant (Cormack et al. 2009)
SECTION_VOTE = 0.5                               # a named section counts as half a first-place vote (set before measuring)
K1, B = 1.2, 0.75
_WORD = re.compile(r"[a-z0-9]+")
_COMPOUND = re.compile(r"[a-z0-9]+(?:[-_.][a-z0-9]+)+")
_STOP = frozenset("a an and are as at be by for from has have in is it its of on or that the this to was were will with "
                  "use when used using not no can only one each any".split())
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)


def tokenize(text: str) -> list[str]:
    t = text.lower()
    return [w for w in _WORD.findall(t) if w not in _STOP] + [c.strip("._-") for c in _COMPOUND.findall(t)]


def split_front(text: str) -> tuple[dict, str]:
    """SKILL.md front matter (``---`` YAML ``---``) and the body."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            import yaml
            try:
                meta = yaml.safe_load(text[3:end]) or {}
            except Exception:
                meta = {}
            return (meta if isinstance(meta, dict) else {}), text[end + 4:].lstrip("\n")
    return {}, text


def headings(body: str) -> list[str]:
    return [m.group(2) for m in _HEADING.finditer(body)]


def excerpt(body: str, heading: str) -> str | None:
    """The section of ``body`` under ``heading`` (case-insensitive, exact text or unique prefix), up to the next heading
    of the same or a higher level; None when no heading matches or the prefix is ambiguous."""
    hs = list(_HEADING.finditer(body))
    want = heading.strip().lstrip("#").strip().lower()
    exact = [m for m in hs if m.group(2).lower() == want]
    pick = exact or [m for m in hs if m.group(2).lower().startswith(want)]
    if len(pick) != 1 and not exact:
        return None
    m = pick[0]
    level = len(m.group(1))
    end = len(body)
    for n in hs:
        if n.start() > m.start() and len(n.group(1)) <= level:
            end = n.start()
            break
    return body[m.start():end].rstrip() + "\n"


@dataclass
class Entry:
    name: str
    path: str
    section: str
    description: str
    axis: str = ""
    also: list[str] = field(default_factory=list)
    text: str = ""

    @property
    def body(self) -> str:
        return split_front(self.text)[1]

    def sha(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()

    def doc_text(self) -> str:
        """What is indexed: the name (as words), description, section ids, headings and the body's start."""
        body = self.body
        return "\n".join([self.name.replace("-", " "), self.description, self.section, " ".join(self.also),
                          " | ".join(headings(body)), body[:2500]])

    def card(self) -> dict[str, Any]:
        return {"name": self.name, "section": self.section, "description": self.description, "path": self.path}


def entries_from(items: Iterable[dict]) -> list[Entry]:
    """``LocalBank.skills``/``catalogue`` rows to entries, one per name (the first path wins; names are unique in the bank)."""
    out, seen = [], set()
    for x in items:
        meta = split_front(x.get("text", ""))[0]
        name = x.get("name") or meta.get("name") or Path(x["path"]).parent.name
        if name in seen:
            continue
        seen.add(name)
        out.append(Entry(name=name, path=x["path"], section=x.get("section", ""), axis=x.get("axis", ""),
                         description=str(x.get("description") or meta.get("description") or ""),
                         also=list(meta.get("also") or []), text=x.get("text", "")))
    return out


class BM25:
    def __init__(self, docs: list[str]):
        self.tf = []
        self.dl = []
        df: dict[str, int] = {}
        for d in docs:
            toks = tokenize(d)
            c: dict[str, int] = {}
            for t in toks:
                c[t] = c.get(t, 0) + 1
            self.tf.append(c)
            self.dl.append(len(toks))
            for t in c:
                df[t] = df.get(t, 0) + 1
        self.n = len(docs)
        self.avgdl = (sum(self.dl) / self.n) if self.n else 1.0
        self.idf = {t: math.log(1.0 + (self.n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def scores(self, query: str) -> list[float]:
        out = [0.0] * self.n
        for q in set(tokenize(query)):
            idf = self.idf.get(q)
            if not idf:
                continue
            for i, c in enumerate(self.tf):
                f = c.get(q)
                if f:
                    out[i] += idf * f * (K1 + 1) / (f + K1 * (1 - B + B * self.dl[i] / self.avgdl))
        return out


class Encoder:
    """Query embedding with fastembed (imported lazily). ``None`` from :func:`local_encoder` when it is not installed."""

    def __init__(self, model: str = EMBED_MODEL, cache_dir: str | None = None):
        from fastembed import TextEmbedding
        self.model = model
        self._m = TextEmbedding(model, cache_dir=cache_dir or os.environ.get("FASTEMBED_CACHE_PATH"), threads=2)

    def embed(self, texts: list[str], query: bool = False):
        import numpy as np
        pre = QUERY_PREFIX if query else ""
        v = np.array(list(self._m.embed([pre + t for t in texts])), dtype="float32")
        return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)


def local_encoder(model: str = EMBED_MODEL) -> Encoder | None:
    if os.environ.get("FDA_SKILL_EMBED", "1") == "0":
        return None
    try:
        return Encoder(model)
    except Exception:                          # not installed, or no model cache and no network: BM25 alone
        return None


def load_vectors(bank_root: Path) -> tuple[dict, Any] | None:
    """(manifest, matrix) from the bank, or None when the bank has no vectors."""
    m, v = Path(bank_root) / MANIFEST, Path(bank_root) / VECTORS
    if not (m.is_file() and v.is_file()):
        return None
    import numpy as np
    return json.loads(m.read_text()), np.load(v)["vectors"]


class SkillIndex:
    def __init__(self, entries: list[Entry], vectors: tuple[dict, Any] | None = None, encoder: Encoder | None = None):
        self.entries = entries
        self.by_name = {e.name: e for e in entries}
        self.bm25 = BM25([e.doc_text() for e in entries])
        self.encoder = encoder
        self.vec = None                         # row of the matrix per entry (None: stale or missing)
        self.stale: list[str] = []
        if vectors is not None and encoder is not None:
            man, mat = vectors
            if man.get("model") == encoder.model:
                rows = {p: (i, h) for i, (p, h) in enumerate(zip(man["paths"], man["sha256"]))}
                self.vec = []
                for e in entries:
                    r = rows.get(e.path)
                    ok = r is not None and r[1] == e.sha()
                    self.vec.append(mat[r[0]] if ok else None)
                    if not ok:
                        self.stale.append(e.name)

    @property
    def mode(self) -> str:
        return "hybrid" if self.vec is not None else "bm25"

    def ranked(self, query: str, sections: list[str] | None = None, mode: str | None = None) -> list[tuple[Entry, dict]]:
        """Every entry, best first, with its per-signal ranks. ``mode``: bm25 | vector | hybrid (default: what is loaded)."""
        mode = mode or self.mode
        n = len(self.entries)
        bm = self.bm25.scores(query)
        bm_rank = {i: r for r, i in enumerate(sorted(range(n), key=lambda i: (-bm[i], i)))}
        vec_rank: dict[int, int] = {}
        cos = [0.0] * n
        if mode in ("vector", "hybrid") and self.vec is not None:
            q = self.encoder.embed([query], query=True)[0]
            have = [i for i in range(n) if self.vec[i] is not None]
            for i in have:
                cos[i] = float(q @ self.vec[i])
            vec_rank = {i: r for r, i in enumerate(sorted(have, key=lambda i: (-cos[i], i)))}
        sec = set(sections or ())

        def fused(i: int) -> float:
            s = 0.0
            if mode in ("bm25", "hybrid") or not vec_rank:
                s += 1.0 / (RRF_K + bm_rank[i]) if bm[i] > 0 else 0.0
            if mode in ("vector", "hybrid") and i in vec_rank:
                s += 1.0 / (RRF_K + vec_rank[i])
            if sec and (self.entries[i].section in sec or sec & set(self.entries[i].also)):
                s += SECTION_VOTE / RRF_K       # a section the caller named: half a first-place vote
            return s
        order = sorted(range(n), key=lambda i: (-fused(i), i))
        return [(self.entries[i], {"score": round(fused(i), 6), "bm25": round(bm[i], 3), "bm25_rank": bm_rank[i] + 1,
                                   "vector_rank": (vec_rank[i] + 1) if i in vec_rank else None,
                                   "cosine": round(cos[i], 4) if i in vec_rank else None}) for i in order]

    def search(self, query: str, k: int = 8, sections: list[str] | None = None, mode: str | None = None) -> list[dict]:
        out = []
        for e, sc in self.ranked(query, sections, mode):
            if sc["score"] <= 0:
                break
            out.append({**e.card(), **sc})
            if len(out) >= k:
                break
        return out


# --- the service client (infra/skill_index) -----------------------------------------------------------------------------

class RemoteIndex:
    """The same ``search`` against the container (``FDA_SKILL_INDEX_URL``); bodies still come from the local bank."""

    def __init__(self, url: str, local: SkillIndex):
        self.url = url.rstrip("/")
        self.local = local
        self.by_name = local.by_name
        self.entries = local.entries
        self.mode = "service"

    def search(self, query: str, k: int = 8, sections: list[str] | None = None, mode: str | None = None) -> list[dict]:
        import urllib.request
        body = json.dumps({"query": query, "k": k, "sections": sections or [], "mode": mode,
                           "names": sorted(self.by_name)}).encode()
        req = urllib.request.Request(self.url + "/search", data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                hits = json.loads(r.read())["hits"]
        except Exception:                          # service down: the in-process index answers
            return self.local.search(query, k, sections, mode)
        return [h for h in hits if h.get("name") in self.by_name][:k]


_CACHE: dict[tuple, Any] = {}


def open_index(bank, board: str | None, family: str | None, part: str | None = None, encoder: Encoder | None | str = "auto"):
    """The index of every skill the session's board and part may use (cached per bank/board/part). ``encoder="auto"``:
    fastembed when installed and the bank has vectors; ``None``: BM25 only."""
    key = (str(getattr(bank, "root", id(bank))), board, family, part, encoder if encoder in (None, "auto") else id(encoder))
    if key in _CACHE:
        return _CACHE[key]
    entries = entries_from(bank.catalogue(board, family, part=part))
    vectors = load_vectors(bank.root) if hasattr(bank, "root") else None
    enc = (local_encoder() if vectors is not None else None) if encoder == "auto" else encoder
    idx: Any = SkillIndex(entries, vectors, enc)
    url = os.environ.get("FDA_SKILL_INDEX_URL")
    if url:
        idx = RemoteIndex(url, idx)
    _CACHE[key] = idx
    return idx


# --- building the vectors (owner's PC only) ------------------------------------------------------------------------------

def all_entries(bank_root: Path) -> list[Entry]:
    """Every sectioned skill of the bank (all boards, all families), for the vectors file."""
    from agent.core.bank import LocalBank
    b = LocalBank(bank_root)
    S = b._select.S
    rows = []
    for s in S.all_skills(b.root):
        p = b.root / s.path
        rows.append({"path": s.path, "axis": s.axis, "section": s.section, "name": s.name, "description": s.description,
                     "text": p.read_text(errors="replace")})
    return entries_from(rows)


def build(bank_root: Path, model: str = EMBED_MODEL) -> dict:
    """Embed every skill and write ``indexes/skill_vectors.{npz,json}`` into the bank. Refuses on a host flagged as a
    work machine (``FDA_WORK_MACHINE=1``)."""
    if os.environ.get("FDA_WORK_MACHINE") == "1":
        raise SystemExit("refused: embeddings are never computed on a work machine (owner rule, 2026-11-10)")
    import numpy as np
    ents = all_entries(bank_root)
    enc = Encoder(model)
    mat = enc.embed([e.doc_text() for e in ents])
    out = Path(bank_root) / "indexes"
    out.mkdir(exist_ok=True)
    np.savez_compressed(out / "skill_vectors.npz", vectors=mat.astype("float32"))
    man = {"model": model, "dim": int(mat.shape[1]), "count": len(ents), "doc_text": "agent.core.skill_index.Entry.doc_text",
           "paths": [e.path for e in ents], "sha256": [e.sha() for e in ents]}
    (out / "skill_vectors.json").write_text(json.dumps(man, indent=1) + "\n")
    return {"count": len(ents), "dim": man["dim"], "model": model}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="embed every skill into <bank>/indexes (owner's PC only)")
    b.add_argument("--bank", type=Path, required=True)
    b.add_argument("--model", default=EMBED_MODEL)
    q = sub.add_parser("search", help="rank the skills for a query")
    q.add_argument("query")
    q.add_argument("--bank", type=Path)
    q.add_argument("--board", default="nexys_a7_100t")
    q.add_argument("--part", default="xc7a100tcsg324-1")
    q.add_argument("-k", type=int, default=8)
    q.add_argument("--mode", choices=["bm25", "vector", "hybrid"])
    a = ap.parse_args(argv)
    if a.cmd == "build":
        print(json.dumps(build(a.bank, a.model)))
        return 0
    from agent.core.bank import DEFAULT_BANK, LocalBank
    bank = LocalBank(a.bank or DEFAULT_BANK)
    idx = open_index(bank, a.board, None, a.part)
    for h in idx.search(a.query, a.k, mode=a.mode):
        print(f"{h['score']:.4f}  {h['name']:<44} {h['section']:<22} {h['description'][:70]}")
    print(f"[mode {idx.mode}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
