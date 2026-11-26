<!-- lab:begin (written by the harness; regenerated each run) -->

## Lab instruments

The lab file (`hil/lab.example.yaml` is the template) lists the instruments; this section is generated from it. You run every instrument step yourself, one at a time: `python -m hil.lab_bringup run <design>`. The agent has only dry-run it against mock instruments. A step marked DRIVES puts a signal into the board and asks you to type `yes` first.

| Requirement | Quantity | Method | Instrument and probe | Not used, and why |
|---|---|---|---|---|
| REQ-13 | frequency of the C3 signal | scripted | counter A on pin C3 | none |

1. **Wiring.** Confirm counter channel A is connected to pin C3 (board powered off while wiring; logic levels match the board's VCCO). Type yes to go on.
2. **Measure** (REQ-13): counter A reads the frequency of the C3 signal; pass within 100 ppm of 25 MHz.

A wrong probe pin shows up as a reading nowhere near the expected value, or as 'not enough edges': check the pin before the cable. A manual reading typed without its unit, or in the wrong one (kHz for MHz), is refused or flagged.

<!-- lab:end -->
