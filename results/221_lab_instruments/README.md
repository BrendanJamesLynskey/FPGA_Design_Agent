# Brief 221: the lab, re-planning the 209 pilot's clock meter with a counter

This folder shows what a lab file changes in a bring-up: the KR260 pilot's P1 design (a frequency meter for the 25 MHz clock on pin C3) planned
with a lab file that holds one mock frequency counter, and the same plan with the owner's seeded bench, where nothing that is onboarded can measure it. The design
and the code are described in [docs/agent.md](../../docs/agent.md#the-lab-instruments-the-agent-can-use-hillabpy-brief-221); nothing here touched an instrument or a board, and the
counter is a mock, so no reading in this folder is evidence about a real clock.

## Records

- [lab_profile_mock.yaml](lab_profile_mock.yaml) and [design_lab.yaml](design_lab.yaml): the lab file of the example (a mock counter, marked `mock: true`) and the design's wiring
  (`counter` channel A on pin C3), which the interview's answer `counter: A -> pin C3` writes.
- [plan.json](plan.json): the method chosen for the one requirement of P1 that an instrument can check, REQ-13 ("COUNT x 156.25 MHz / GATE_ACTUAL measures the C3 clock within
  100 ppm of 25 MHz"): the scripted counter as an independent check, the design's own count against its reference kept beside it.
- [lab_steps.yaml](lab_steps.yaml) and [BRINGUP_lab_block.md](BRINGUP_lab_block.md): the two steps (confirm the wiring, read the frequency; pass within 100 ppm of 25 MHz) and the
  `Lab instruments` section added to BRINGUP.md. P1's run 3 wrote no BRINGUP.md, so the text of run 1's is the base the block is added to.
- [dry_run_results.json](dry_run_results.json): the steps run against the mock counter: both rows are `dry_run`, `evidence` is false, and the reading is the expected value by
  construction (it shows that the plumbing works, not that a clock is right).
- [before_row.md](before_row.md) and [after_row.md](after_row.md): the requirements-report row for REQ-13 before the plan and after it. After, the method cell reads
  `hardware: pending` and, beside it, `instrument (counter A on pin C3, scripted): dry run against a mock, not evidence; to be run by the owner`. The result stays `pending`:
  the on-chip count has not run on the board, and an instrument reading alone does not pass a requirement.
- [plan_owner_bench.json](plan_owner_bench.json): the same requirement planned against [hil/lab.example.yaml](../../hil/lab.example.yaml), the owner's bench as recorded on
  2026-11-04 to 2026-11-09. The ADALM2000 and the Red Pitaya could check it (the M2K by counting edges on a digital input, within its 25 MHz limit; the Red Pitaya from the waveform), but
  neither is onboarded, so the method stays on-chip and both are listed as "available after onboarding". There is no standalone counter on the bench.
- [make_example.py](make_example.py): the generator.

## Reproduce

```
python3 results/221_lab_instruments/make_example.py        # rewrites every file above
python -m pytest -q hil/tests/test_221_lab.py agent/tests/test_221_lab_interview.py flow/tests/test_221_bringup_lab.py
python -m hil.lab_bringup plan  <design>                   # the plan as text, from the lab the design would see
python -m hil.lab_bringup dry-run <design>                 # every step against mock instruments
```

The owner's real run is `python -m hil.lab_bringup run <design>` (or `flow/bringup.py`, which runs the same steps): it asks for the wiring to be confirmed and
for every manual reading, and it is not run by the agent.

## Known gaps and limits

- No real instrument was contacted: no M2K, Red Pitaya, Pluto or RTL-SDR was connected on 2026-11-25 or 2026-11-26 (the PC's USB list shows the capture device, the audio interface and two
  FTDI board cables), and the Red Pitaya's address is still to be given. The Red Pitaya and M2K adapters are tested against fakes only, like the brief 30 drivers they wrap.
- The counter is a mock with an `accuracy_ppm` of 1 that nobody measured. A real instrument without a recorded accuracy gets the step caveat "a pass is a coarse independent check".
- The method choice is by rules on the requirement's words (a frequency with a unit, a voltage level). It found one need in P1's 29 requirements; the LED rates (REQ-16, REQ-17) are stated in
  cycles, not in hertz, so they get no instrument step.
- `libm2k`, `pyadi-iio` and `pyvisa` are not installed in the repository's virtual environment and the tests do not need them; the M2K adapter imports `libm2k` only when a real context is opened.
- Stage 9's hook runs the plan after the model has written BRINGUP.md; a run of the full agent with a lab file was not made here (it needs the access key and live model calls), so that path is covered by the
  unit tests of `apply_to_design` and the interview, not by a recorded live run.
