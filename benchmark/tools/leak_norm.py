#!/usr/bin/env python3
"""Comment-insensitive, identifier-insensitive normalisation for the leak guard (brief 83).

A guard that compares lines or fixed windows of text is beaten by cosmetic changes: a trailing comment on every line,
a renamed signal, different indentation. This module removes what such changes touch, so the guard compares what the
code does and how it is built:

    strip_text(text, suffix)   comments and string literals removed, whitespace collapsed (for window matching)
    code_tokens(text, suffix)  token stream with comments and strings dropped, identifiers -> I, numbers -> N,
                               keywords and operators kept (for winnowing)
    prose_tokens(text)         lower-cased words (specs, YAML values)
    fingerprints(tokens, k, w) Schleimer et al. winnowing, as `similarity.py code`

Languages: SystemVerilog and Verilog (.sv .svh .v .vh), VHDL (.vhd .vhdl; case-insensitive), Python (.py; real
tokenizer, so docstrings are strings), and `#` comment styles for YAML, Tcl, XDC and shell. Anything else is text:
words only. No language model anywhere; no matched text is ever printed by the callers.

Normalised away, on purpose: comments; string literals; identifier names; number values and radix; whitespace and
indentation; case (VHDL). Not normalised: operator and keyword order, the shape of the expression tree, the order of
statements (a reordered copy still shares most k-grams).
"""

from __future__ import annotations

import hashlib
import io
import keyword
import re
import tokenize
from pathlib import Path

LONG_STR = 40                                  # a string this long is text that can carry code or a spec
SV = {".sv", ".svh", ".v", ".vh", ".svp", ".sva", ".vp"}
VHDL = {".vhd", ".vhdl"}
PY = {".py"}
HASH = {".yaml", ".yml", ".tcl", ".xdc", ".sh", ".toml", ".cfg", ".ini", ".txt"}
CODE = SV | VHDL | PY
SCANNED = CODE | HASH | {".md", ".json", ".jsonl", ".csv", ".mem", ".hex", ".cpp", ".h", ".c", ".js"}

SV_KEYWORDS = set("""module endmodule input output inout logic wire reg always always_ff always_comb always_latch
assign begin end if else case casez casex endcase default for while posedge negedge or and not parameter localparam
int integer genvar generate endgenerate function endfunction task endtask return typedef enum struct packed
signed unsigned initial forever repeat unique priority import package endpackage bit byte interface endinterface
modport assert property cover assume sequence endsequence disable iff generate foreach break continue do automatic
static const void string shortint longint time real""".split())
VHDL_KEYWORDS = set("""library use entity is port generic map end architecture of signal variable constant type subtype
begin process if then elsif else case when others for loop while generate in out inout buffer downto to and or not
xor nand nor xnor rem mod abs function procedure return package body component wait until after null range
rising_edge falling_edge std_logic std_logic_vector unsigned signed integer natural boolean attribute report assert
severity open all with select next exit record array label configuration""".split())
PY_KEYWORDS = set(keyword.kwlist) | {"self", "None", "True", "False"}

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")
_NUMBER = re.compile(r"(?<![A-Za-z0-9_$])(?:\d+\s*'[sS]?[bBoOdDhH]\s*[0-9a-fA-F_xXzZ?]+|'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+|'[01xXzZ]"
                     r"|\d+\.\d+(?:[eE][+-]?\d+)?|0[xX][0-9a-fA-F_]+|\d[\d_]*)")
_VHDL_BASED = re.compile(r"\d+#[0-9a-fA-F_.]+#|[xXbBoO]\"[0-9a-fA-F_xXzZuU-]+\"")
_TOKEN = re.compile(r"\s*(?:(?P<id>[A-Za-z_\\][A-Za-z0-9_$]*)|(?P<num>\d)|(?P<op>>>>=|<<<=|===|!==|<<<|>>>|\|->|\|=>"
                    r"|[<>=!]=|<<|>>|&&|\|\||\*\*|\+:|-:|::|=>|<=|:=|\S))")


BACKUP = {".bak", ".orig", ".old", ".tmp", ".save", ".swp", ".rej", ".txt~", "~"}


def eff_suffix(name: str) -> str:
    """Suffix of a file name with a backup ending (.bak, .orig, ~) looked through: x.sv.bak counts as .sv."""
    p = Path(name)
    suf = p.suffix.lower()
    while suf in BACKUP or name.endswith("~"):
        name = name[:-len(suf)] if suf in BACKUP else name[:-1]
        p = Path(name)
        suf = p.suffix.lower()
    return suf


def _scan(text: str, line: str | None, block: bool, vhdl: bool, hashc: bool) -> list[tuple[str, str]]:
    """Split into ('code'|'str', chunk); comments are dropped.  A small scanner, not a regex, so a quote inside a
    comment or a comment marker inside a string does the right thing."""
    out: list[tuple[str, str]] = []
    i, n = 0, len(text)
    buf: list[str] = []

    def flush() -> None:
        if buf:
            out.append(("code", "".join(buf)))
            buf.clear()

    while i < n:
        c = text[i]
        two = text[i:i + 2]
        if hashc and c == "#" and (i == 0 or text[i - 1] in " \t\n"):
            j = text.find("\n", i)
            j = n if j < 0 else j
            flush()
            out.append(("comment", text[i + 1:j]))
            i = j
            continue
        if line and text.startswith(line, i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            flush()
            out.append(("comment", text[i + len(line):j]))
            i = j
            continue
        if block and two == "/*":
            j = text.find("*/", i + 2)
            j2 = n if j < 0 else j
            flush()
            out.append(("comment", text[i + 2:j2]))
            i = n if j < 0 else j + 2
            continue
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" and not vhdl else 1
                if vhdl and text[j - 1:j + 1] == '""':      # VHDL doubles a quote inside a string
                    j += 1
            flush()
            out.append(("str", text[i:j + 1]))
            i = j + 1
            continue
        if c == "'" and hashc:                          # YAML/Tcl/shell single-quoted string
            j = text.find("'", i + 1)
            j = n - 1 if j < 0 else j
            flush()
            out.append(("str", text[i:j + 1]))
            i = j + 1
            continue
        if vhdl and c == "'" and i + 2 < n and text[i + 2] == "'" and not (i > 0 and (text[i - 1].isalnum() or text[i - 1] in "_)")):
            flush()
            out.append(("str", text[i:i + 3]))          # character literal '0', not an attribute tick
            i += 3
            continue
        buf.append(c)
        i += 1
    flush()
    return out


def _chunks(text: str, suffix: str) -> list[tuple[str, str]]:
    s = suffix.lower()
    if s in SV:
        return _scan(text, "//", True, False, False)
    if s in VHDL:
        return _scan(text, "--", True, True, False)
    if s in HASH:
        return _scan(text, None, False, False, True)
    return [("code", text)]


def _py_hidden(text: str) -> str:
    """Comments and long string literals of Python source, for the hidden-text pass."""
    parts = []
    try:
        for t in tokenize.generate_tokens(io.StringIO(text).readline):
            if t.type == tokenize.COMMENT or (t.type == tokenize.STRING and len(t.string) >= LONG_STR):
                parts.append(t.string)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return "\n".join(parts)


def _py_tokens(text: str) -> list[str] | None:
    out: list[str] = []
    fdepth = 0
    try:
        for t in tokenize.generate_tokens(io.StringIO(text).readline):
            ty, s = t.type, t.string
            if ty in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
                      tokenize.ENDMARKER, tokenize.ENCODING):
                continue
            name = tokenize.tok_name.get(ty, "")
            if name == "FSTRING_START":
                fdepth += 1
                if fdepth == 1:
                    out.append("S")
                continue
            if name == "FSTRING_END":
                fdepth -= 1
                continue
            if fdepth:
                continue
            if ty == tokenize.STRING:
                out.append("S")
            elif ty == tokenize.NUMBER:
                out.append("N")
            elif ty == tokenize.NAME:
                out.append(s if s in PY_KEYWORDS else "I")
            else:
                out.append(s)
        return out
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return None


def strip_text(text: str, suffix: str) -> str:
    """Comments and string literals removed, whitespace collapsed.  VHDL is lower-cased.  Text files unchanged
    apart from whitespace."""
    s = suffix.lower()
    if s in PY:
        toks = _py_tokens(text)
        if toks is not None:
            # keep identifiers: rebuild from the real tokenizer so only comments and strings go
            out = []
            try:
                for t in tokenize.generate_tokens(io.StringIO(text).readline):
                    if t.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
                                  tokenize.ENDMARKER, tokenize.STRING):
                        continue
                    if tokenize.tok_name.get(t.type, "").startswith("FSTRING"):
                        continue
                    out.append(t.string)
            except (tokenize.TokenError, IndentationError, SyntaxError):
                pass
            return " ".join(out)
        text = "\n".join(re.sub(r"(?<![\"'])#.*", " ", ln) for ln in text.splitlines())
        return re.sub(r"\s+", " ", text).strip()
    joined = " ".join(c if k == "code" else ('""' if k == "str" else " ") for k, c in _chunks(text, s))
    joined = re.sub(r"\s+", " ", joined).strip()
    return joined.lower() if s in VHDL else joined


def hidden_text(text: str, suffix: str) -> str:
    """Comment text and long string literals: code or a spec hidden there is still visible to the agent."""
    s = suffix.lower()
    if s in PY:
        return _py_hidden(text)
    return "\n".join(c for k, c in _chunks(text, s) if k == "comment" or (k == "str" and len(c) >= LONG_STR))


def code_tokens(text: str, suffix: str) -> list[str]:
    """Token stream for winnowing: identifiers -> I, numbers -> N, strings dropped, comments dropped."""
    return drop_dead(_code_tokens(text, suffix))


def _code_tokens(text: str, suffix: str) -> list[str]:
    s = suffix.lower()
    if s in PY:
        toks = _py_tokens(text)
        if toks is not None:
            return [t for t in toks if t != "S"]
        s = ".sv"                                       # unparsable Python: fall back to the generic scanner
    kw = VHDL_KEYWORDS if s in VHDL else SV_KEYWORDS | PY_KEYWORDS
    vhdl = s in VHDL
    body = " ".join(c for k, c in _chunks(text, s) if k == "code")
    if vhdl:
        body = _VHDL_BASED.sub(" 0 ", body.lower())
    else:
        body = _NUMBER.sub(lambda m: " 0 ", body)
    out: list[str] = []
    for m in _TOKEN.finditer(body):
        if m.group("id"):
            t = m.group("id")
            t = t.lower() if vhdl else t
            out.append(t if t in kw else "I")
        elif m.group("num"):
            out.append("N")
        else:
            op = m.group("op")
            out.append("N" if op.isdigit() else op)
    # collapse runs the number regex turned into "0": already N through the digit branch
    return out


_DEAD = re.compile(r"I (?:=|<=) N(?: ;)?(?= (?:;|I|N|if|end|begin|else|for|while|return|\Z|[)}]))|\bif \( N \)|\bif N :")


def drop_dead(toks: list[str]) -> list[str]:
    """Remove padding statements such as `x = 0;` and `if (0)`: a dead statement every few tokens breaks every k-gram."""
    s = " " + " ".join(toks) + " "
    for _ in range(2):
        s = _DEAD.sub(" ", s)
    return s.split()


def prose_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def tokens_for(text: str, suffix: str) -> list[tuple[str, list[str]]]:
    """[(mode, tokens)] for one file: 'code' and 'prose' streams.  Comment text and long strings are scored as a
    second stream of the same file (code-shaped and word-shaped); an unknown suffix is read as code and as prose."""
    s = suffix.lower()
    out: list[tuple[str, list[str]]] = []
    if s in CODE:
        out.append(("code", code_tokens(text, s)))
    elif s in HASH:
        out.append(("prose", prose_tokens(" ".join(c for k, c in _chunks(text, s) if k == "code"))))
    else:
        out.append(("prose", prose_tokens(text)))
        if s not in {".md", ".json", ".jsonl", ".csv"}:
            out.append(("code", code_tokens(text, ".sv")))
    h = hidden_text(text, s) if s in CODE | HASH else ""
    if h.strip():
        out.append(("code", code_tokens(h, ".sv")))
        out.append(("prose", prose_tokens(h)))
    return out


def fingerprints(toks: list[str], k: int, w: int) -> set[int]:
    hs = [int.from_bytes(hashlib.blake2b(" ".join(toks[i:i + k]).encode(), digest_size=8).digest(), "big")
          for i in range(max(0, len(toks) - k + 1))]
    fp = set()
    for i in range(max(0, len(hs) - w + 1)):
        fp.add(min(hs[i:i + w]))
    if hs and len(hs) < w:
        fp.add(min(hs))
    return fp
