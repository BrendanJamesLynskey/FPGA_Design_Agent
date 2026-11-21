"""Agent tool for brief 114: ``doc_crossread``, the blind document cross-read as an optional, read-only check.

A reader model that sees only a vendor-document excerpt writes the facts the code depends on, code reads the numbers out of the design's own code
files, and code compares them (flow/doc_crossread.py). The tool reads files and may make one model call (purpose ``doc_crossread``); it never writes
a design file, builds, simulates or touches a board. With ``facts_file`` it compares a stored reader reply and makes no model call."""
from __future__ import annotations

import json
import os
from pathlib import Path

from agent.core.registry import tool
from agent.core.session import Session


def _inside(p: Path, roots: list[Path]) -> bool:
    return any(p == r or r in p.parents for r in roots)


@tool("doc_crossread", "Optional check, read-only: compare code against a vendor document without letting one reader see both. A reader model sees only the "
      "document excerpt (never your code) and writes the facts the topic depends on (addresses, bit fields, widths, word counts, reset values, conditions) with a "
      "page and a quotation; code checks each quotation against the excerpt, reads the numbers out of your code files, and reports agree / disagree / not in "
      "code for each fact. A disagreement shows both sides' evidence; read it against the document before acting. It finds what a test written from the same "
      "misreading cannot. It does not read function bodies or compare prose, and a name the code spells differently may show as not in code. The document is a text file "
      "(pages separated by form feeds) inside the design, or under the folder in FDA_DOCS_DIR, or a PDF there with `pages`; one model call is made unless `facts_file` is given.",
      {"doc": {"type": "string", "description": "path to the document excerpt (.txt) or PDF, inside the design or under FDA_DOCS_DIR"},
       "pages": {"type": "string", "description": "page numbers or ranges, e.g. 226-234,462-464 (required for a PDF)"},
       "code": {"type": "array", "items": {"type": "string"}, "description": "code files in the design (.py, .sv, .h)"},
       "topic": {"type": "string", "description": "what the code is about, in your own words, without values; the reader is told only this and the excerpt"},
       "target": {"type": "string", "description": "the device family or configuration, as the document names it"},
       "facts_file": {"type": "string", "description": "a stored reader reply (JSON in the design): compare it and make no model call"}},
      ["doc", "code"])
def doc_crossread(s: Session, doc: str, code: list[str], pages: str = "", topic: str = "", target: str = "the device or configuration the design is for",
                  facts_file: str = "") -> dict:
    from flow import doc_crossread as D
    docs_root = os.environ.get("FDA_DOCS_DIR")
    roots = [s.design] + ([Path(docs_root).resolve()] if docs_root else [])

    def resolve(x: str, allowed: list[Path]) -> Path:
        p = (s.design / x) if not Path(x).is_absolute() else Path(x)
        p = p.resolve()
        if not _inside(p, allowed):
            raise ValueError(f"{x}: outside the design (and FDA_DOCS_DIR); the tool reads only those")
        if not p.is_file():
            raise ValueError(f"{x}: not a file")
        return p
    try:
        dp = resolve(doc, roots)
        cps = [resolve(c, [s.design]) for c in code]
        fp = resolve(facts_file, [s.design]) if facts_file else None
        document = D.load_document(doc=None if dp.suffix.lower() == ".pdf" else dp, pdf=dp if dp.suffix.lower() == ".pdf" else None, pages=pages or None)
        meter = None
        if fp is None:
            meter = D.UsageMeter(D.make_resolver(run_dir=s.design / "build" / "crossread"))
        rec, read = D.crossread(document, cps, topic, target, llm=meter, facts=fp, model_info=meter.model_info() if meter else None)
    except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as e:
        return {"ok": False, "output": f"doc_crossread: {e}"}
    except Exception as e:                                      # a missing prompt, an unconfigured model, a failed call: say which, never the prompt
        return {"ok": False, "output": f"doc_crossread: {type(e).__name__}: {str(e)[:200]}"}
    if meter:
        rec["usage"] = meter.totals()
    out = s.design / "build" / "crossread"
    out.mkdir(parents=True, exist_ok=True)
    (out / "record.json").write_text(json.dumps(rec, indent=1, default=str) + "\n")
    return {"ok": True, "output": D.render(rec), "summary": rec["summary"], "record": "build/crossread/record.json"}
