# Brief 153 (review item F9): pre-registration

Written 2026-11-21 22:54 GMT (`date`), before any change to the flow code on branch `b153-vhdl-parity`. Source: brief 147's review
(`reports/147_flow_improvement_review.md`, section 5.1 and 5.4 item 1, programme row F9).

## The question

How many readers of a design's RTL silently skip a VHDL design (return a pass, an empty list or no finding, and say nothing), and does
the number go to 0 after the change, with each reader either reading VHDL or saying it does not?

## The labelled set (frozen at the commit that adds this file)

`tools/vhdl_parity_probe.py`, `READERS`: 17 readers, each with a planted defect (or, for a file-list reader, an edit) and a rule for
what "caught" means. The design is one task, `t1_gray_stepper`: its SystemVerilog reference and the brief 55 VHDL translation (arm B,
`results/55_vhdl/translations/B`), staged with the spec, XDC and `build.yaml` a board design has. Each reader runs on the clean-or-planted
SystemVerilog design (a control: it must catch the plant) and on the planted VHDL design. Outcomes: `caught`, `no_reader` (the reader
says it did not read VHDL: the fail-closed status), `silent` (returns pass/empty and says nothing), `wrong` (reads the VHDL as
SystemVerilog and fails with an error naming the wrong problem), `control` (a reader with nothing to catch by construction).
The count F9 is judged on: **silent**, on the VHDL design.

A second record runs every registered, source-reading check of `flow.checks` on the five brief 55 translations and their SystemVerilog
references (`checks_before.json`, `checks_after.json`): status per check.

The probe was written and debugged against the unchanged code, so its first runs (to make the plants work: one plant had to drive an
output because GHDL removes an unused signal) saw the before picture before this file was committed. The labelled set was not changed
after seeing the numbers except where a plant did not do what it said (listed in the report). The before result is committed in
`before.json`.

## Null result, stated before the after run

- **Null A:** after the change the number of `silent` readers on the VHDL design is still above 0 (a reader was missed, or one was
  ported with a text scan that does not catch its plant).
- **Null B:** the planted wrong constant in the VHDL design (the shell's `DESIGN_ID` bound to `x"47524158"` where the spec says "GRAY" =
  `x"47524159"`) is not caught by the derived-constants check (`CONST-ID-01`).
- **Null C:** a port changes the SystemVerilog result of a reader (a regression): the SystemVerilog controls must still be `caught`.

## What counts as done

- `silent` = 0 on the VHDL design, with every reader `caught` or `no_reader` (no `wrong`).
- Null B false: `CONST-ID-01` raised on the planted VHDL design, and not raised on the clean one.
- Every port covered by a test on a VHDL fixture (`flow/tests/test_153_vhdl_parity.py`).
- Not claimed: that VHDL reaches parity of capability (NVC, code coverage, mixed simulation, library blocks in VHDL are F10 and F11),
  or that the 17 readers are every reader there is: they are the ones the review's section 5.1 names plus those a grep for suffix
  globs found (`inventory.md`).
