# freq_duty_counter 0.1.0

Frequency and duty counter: edges and high clocks of an asynchronous input over a fixed gate; two-flop synchroniser inside. frequency = edges / gate time, duty = high clocks / gate clocks.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated and measured on the Nexys A7-100T inside b30_hil_audio (1000.0 Hz read for the 1 kHz tone).

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `GATE_CLKS` | 100000 | 4..1073741824 | gate length in clocks |
| `CNT_W` | 24 | 3..32 | counter width; must hold a gate (GATE_CLKS < 2**CNT_W) |

Out-of-space values fail at elaboration with `$error` (tested: `GATE_CLKS=2`, `CNT_W=40`).

## Interfaces

- `measure`: native; sig (asynchronous) -> valid pulse, edges, high_clks, gates

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- result: one gate (GATE_CLKS clocks) after reset, then every gate
- input_to_count: 3 clocks (two synchroniser flops and an edge register)
- throughput: one input sample per clock; at most one counted edge per two clocks

## Evidence

Bit-exact against the Python models in `hil/instruments/models.py` (plain Python written from the definitions, not from the RTL); cocotb with Icarus Verilog 12. Tests: `hil/tests/test_30_ip_rtl.py`, `designs/b30_hil_audio/tests/test_hil_audio_rtl.py`.

Try it: `python3 -m pytest hil/tests/test_30_ip_rtl.py designs/b30_hil_audio/tests/test_hil_audio_rtl.py`.

Parameter points simulated: `GATE_CLKS=2000, CNT_W=16`; `GATE_CLKS=777, CNT_W=12`.

Seeded faults (`faults.yaml`, run by `hil/ip_faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `counts_both_edges` | falling edges counted too, so the frequency reads double | caught |
| `duty_counts_low` | the duty counter counts the low clocks | caught |
| `gate_half_length` | the gate is half as long as declared, so the duty and frequency scale are wrong | caught |

## Boundary and reuse

- Registered outputs: yes.
- Clock crossings: one: sig through a two-flop ASYNC_REG synchroniser.
- Part, board or pin: none.
- Depends on: nothing.
- Limits: frequency resolution is f_clk / GATE_CLKS; input edges closer than two clocks are missed; no hysteresis or glitch filter.

## Cost table

in-context cost (not an OOC sweep): 12 LUT, 165 FF at GATE_CLKS 50 000 000, CNT_W 26 inside b30_hil_audio (Vivado 2026.1, xc7a100t -1; results/vivado_2026_1_remeasure/b30_hil_audio.json); the OOC sweep is still to do.

Licence: MIT (this repository).
