"""Statement integrity: the definitions and theorem statements of a proved Spec.lean must equal the human-approved ones.

The file is split into top-level blocks (def, theorem, lemma, ...). For a theorem the statement is the text up to its
``:= by``; for a def it is the whole block. Every block of the approved file must appear, by name, with the same text in the
proved file. The proved file may add helper ``theorem``/``lemma`` blocks (they cannot change a statement); it may not add
or change a ``def``. Comments are ignored.
"""
import re
import sys

KW = r"(?:private\s+|protected\s+)?(def|abbrev|theorem|lemma|instance|open|namespace|end|import|set_option|noncomputable|macro|macro_rules|syntax|notation|infix|infixl|infixr|prefix|postfix|elab|attribute|local|section|variable|example|universe)\b"
FORBIDDEN = ("instance", "macro_rules", "syntax", "notation", "infix", "infixl", "infixr", "prefix", "postfix", "elab", "attribute", "local")


def blocks(text: str) -> list[tuple[str, str, str]]:
    text = re.sub(r"/-.*?-/", "", text, flags=re.S)
    text = re.sub(r"--[^\n]*", "", text)
    parts, cur = [], []
    for line in text.splitlines():
        if re.match(KW, line) and cur:
            parts.append("\n".join(cur)); cur = []
        cur.append(line)
    parts.append("\n".join(cur))
    out = []
    for p in parts:
        m = re.match(KW + r"\s*([^\s(:\[]*)", p.lstrip())
        if not m:
            continue
        kind, name = m.group(1), m.group(2)
        body = p
        if kind in ("namespace", "end", "open", "import", "set_option", "section", "variable", "universe"):
            body = p.splitlines()[0] if p.strip() else p
        if kind in ("theorem", "lemma"):
            body = p.split(":= by")[0] if ":= by" in p else p.split(":=")[0]
        out.append((kind, name or kind, re.sub(r"\s+", " ", body).strip()))
    return out


def check(approved: str, proved: str) -> list[str]:
    a, b = blocks(approved), blocks(proved)
    bd = {(k, n): t for k, n, t in b}
    errs = []
    for k, n, t in a:
        if k in ("end",):
            continue
        if bd.get((k, n)) != t:
            errs.append(f"{k} {n}: missing or changed")
    for k, n, t in b:
        if k in FORBIDDEN:
            errs.append(f"{k} {n}: not allowed (could change what a statement means)")
        if k == "macro" and not re.match(r'macro\s+"[^"]*"\s*:\s*tactic\b', t):
            errs.append(f"macro {n}: only tactic macros are allowed")
        if k == "def" and not any(k == k2 and n == n2 for k2, n2, _ in a):
            errs.append(f"def {n}: new def not allowed")
    return errs


def main(a: str, b: str) -> int:
    errs = check(open(a).read(), open(b).read())
    for e in errs:
        print("STATEMENT CHECK:", e)
    if not errs:
        print("statements identical (helper lemmas allowed)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
