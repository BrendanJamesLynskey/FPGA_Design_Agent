# Blind document cross-read (brief 114)

A check that compares code with a vendor document without letting one reader see both. Code: [flow/doc_crossread.py](../flow/doc_crossread.py).
Agent tool: `doc_crossread` ([agent/core/crossread_tools.py](../agent/core/crossread_tools.py)). Tests: [flow/tests/test_114_doc_crossread.py](../flow/tests/test_114_doc_crossread.py).
Pre-registration, cases and measured results: [results/114_doc_crossread](../results/114_doc_crossread/README.md).

**Why.** In 96D the eye-scan driver, its fake board and its test stand-in were written from one misreading of UG576 (five-word masks on UltraScale+, where the
guide says ten), so every test passed and the board counted nothing. A second misreading (the clock phase of the scan) showed up only on the board. A test written
by the same reader shares the reader's mistake; an independent read of the document does not.

## How it works

1. **The reader** is a model that sees only a document excerpt, a topic you write and a target (device family or configuration). It never sees the code.
   It writes facts as JSON: subject, field, kind (`address`, `word_count`, `width_bits`, `bit_range`, `reset_value`, `value`, `step`, `condition`, `other`), the
   number, the variant it applies to, whether the variant is the target's, and a page, a table label and a short quotation. The prompts are in the private
   knowledge repository (`graph/doc_crossread/*`, brief 99); the model is the `doc_crossread` purpose of the model table (brief 108), built in as Claude Code on
   the subscription, Sonnet 5.5, effort medium (opt-in like `options`: a `default:` does not move it).
2. **Quotation check, by code.** A fact's quotation must be in the excerpt (white space and case ignored) and on the page cited. A fact whose quotation is not
   found stays in the report marked `[unverified citation]`; it is never silently trusted. One repair round is allowed when the reply is not JSON or more than a
   quarter of the quotations are missing.
3. **Code side, by code.** `extract_code` reads the numbers out of the code files:

   | Language | Read | Not read |
   |---|---|---|
   | Python | module-level and class-level assignments (tuple unpacking too), evaluated with integers, strings, lists, tuples, dicts, comprehensions over `range()` and calls to the simple pure functions defined in the given files (docstring, `if ...: raise`, local assignments, `return`) | constants inside function bodies, attributes of objects, anything that calls a library or does I/O |
   | SystemVerilog | `localparam` and `parameter` (with the declared width), `` `define``, enum members with explicit values | array literals, structs, functions, `case` addresses, port widths, generate blocks, numbers inline in `always` blocks |
   | C | `#define NAME <integer expression>` | enums, `const` variables, function-like macros |

   Every assignment that could not be evaluated is listed in the report as "code not parsed", with the reason. Comments and strings are searched only for the
   names a text fact (a step or a condition) mentions. The evaluator runs no code of its own: arithmetic, comprehensions and the file's simple functions, within
   size, step and recursion limits.
4. **Comparison, by code.** Each fact about the target is matched to code names and judged by its kind. Possible results:
   - `agree`: every number the document gives is in the best-matching code facts (`tier: value` means no code name matched and the number was found elsewhere in the code: check it);
   - `disagree`: a code name matches and its numbers differ; the row shows the document's quotation and the code's file, line, name and value;
   - `not_in_code`: no code name matches (the code may spell it differently: use `--alias DOC=CODE`), or a text fact's names appear nowhere in the code;
   - `mentioned`: a text fact's names appear in the code; the sentence itself is not compared, read the evidence;
   - `other_variant`: the fact is for another device family or mode; not compared;
   - and, listed apart, code constants no document fact matched (`not in document`).

   No model compares, judges or scores anything.

## Use

```
python -m flow.doc_crossread --pdf UG576.pdf --pages 226-234,462-464 --code hw.py --code eyescan.py \
    --topic "driver for the GTH on-chip eye scan: attributes, DRP addresses and sizes" --target "UltraScale+ GTHE4"
python -m flow.doc_crossread --doc excerpt.txt --code regs.h --facts replies/run1.json    # compare a stored reader reply; no model call
python -m flow.doc_crossread --code-only --code tb.sv                                     # what the code side reads
```

`--doc` takes a text excerpt (form-feed separated pages); `--pdf` takes a local PDF and `--pages`. **Vendor PDFs are never committed**; the record keeps the
excerpt's SHA-256 and page numbers. `--record DIR` writes `record.json`. Exit code 2 when there is at least one `disagree`, else 0. The agent tool takes the same
inputs (paths inside the design, or under `FDA_DOCS_DIR`) and writes `build/crossread/record.json`; it is registered (schema 1.19.0) but no stage or role is offered it.

## What you could guess wrong

- **Silence is not agreement.** `not_in_code` often means "the code calls it something else". A document fact the reader missed produces no row at all.
- **The reader's topic is all it knows besides the excerpt.** Do not put values or code in the topic. Name the target family exactly as the document does: the
  reader sets `for_target` from it, and a variant it marks as another family's is not compared.
- **Names are matched by tokens**, not by meaning. Digits are significant first (`ES_QUALIFIER5` against `A_ES_QUALIFIER5`) and then ignored (`..QUALIFIER0`); a
  trailing `OFFSET`, `RESET`, `WIDTH`, `SHIFT` or `ADDR` in a code name says which number it is; a prefix shared by most names in a file (`ZB_ACCEL_`) is ignored.
  Abbreviations are matched only in one form (`RX_FIFO` to `RXF`). Where several code names match, the best match decides, so two registers with the same stem
  (`TCSR0`, `TCSR1`) can both satisfy a fact about one of them.
- **An address found only by value** (`tier: value`) says a number exists in the code, not that the right item uses it.
- **Constants inside function bodies are not read**; a register map written as `if addr == 0x0C:` is invisible to this check.
- **A disagreement can be the document's or the reader's mistake.** Read the quotation and the page before changing code; a `[unverified citation]` mark means the
  quotation is not in the excerpt.
- **The reader is a model and varies from run to run.** One run is a sample: repeat it before relying on silence (results/114_doc_crossread measures this).
- **Cost.** One reader call per check: input is the excerpt (about 1 000 tokens a page), output a few thousand tokens. It runs on the Max plan through Claude Code; no
  dollars are reported. Measured figures per case are in the results README.
