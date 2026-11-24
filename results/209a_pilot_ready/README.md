# Brief 209a: the agent made ready for the KR260 pilot

Two specs for the live checks of brief 209a: a toy design for a board with no UART (two registers and an LED blink on the KR260, reached over the JTAG register
bus) and a design that is deliberately too deep for its clock (the report gates of brief 204a send it back to the Designer). The runs were made with the subscription
harness (`--harness claude_code`, Sonnet 5.5); no OpenRouter or Anthropic API call was made.

## Records

- `toy_jtag_leds/spec.md` and `toy_jtag_leds/data/jtag_bus.sv`: the request of the JTAG-route toy run (the bus is `designs/b58a_trigger/rtl/jtag_bus.sv`, unchanged).
- `deep_for_clock/spec.md`: the request of the report-gate run (24 dependent multiplies in one 40 ns clock).
- The results of the runs are in the brief's report; this folder holds the requests.

## Reproduce

`python -m agent run results/209a_pilot_ready/toy_jtag_leds/spec.md --board kr260 --harness claude_code --cc-model claude-sonnet-5-5 --review off --interview off`
and the same for `deep_for_clock` with `--stop-after 4`. Both need the pinned private prompts and Vivado 2025.2 (a heavy-job slot on the shared PC).

## Known gaps and limits

The runs depend on the model and are not repeatable to the byte; they are single runs, not a measurement of the agent's rate.
