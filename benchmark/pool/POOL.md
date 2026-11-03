# Training-spec pool for P1 (40 specs)

Specs for the rejection-sampling fine-tune of the FPGA Design Agent. Each directory has the same layout as a benchmark
task minus everything that needs RTL: `spec.md` (what the agent is given), `hidden/spec.yaml` (the full answer, schema
`fpga-design-agent/spec/v0`, validated by `agent.graph.spec_schema.validate`), `hidden/model.py` (golden model from
the spec alone), `hidden/acceptance.py` (cocotb tests through the board pins and the shell, every check against the
model, at least one seeded random test), `hidden/bench.yaml` (top, shrunk parameters, optional wrapper, 3 distinctive
phrases) and `hidden/test_model.py` (plain pytest unit tests of the model). There is **no reference RTL, no mutants,
no selfcheck**: a design the agent writes is kept only if it passes these independent tests.

Shared helper: [`poollib.py`](poollib.py) (signal monitor, run-length helpers, model/RTL alignment for clock-level
models, hex glyph table). Nothing in it knows a spec's behaviour.

Mix: 22 T1-level blocks and 18 T2-level peripherals/protocols. Text similarity of the 40 `spec.md` against the 22
benchmark specs (`benchmark/tools/similarity.py specs`): max cosine 0.18 (threshold 0.45).

Check each model's unit tests with `.venv/bin/python -m pytest -q benchmark/pool/<id>/hidden/test_model.py` (one id at
a time: every directory has a `model.py`/`test_model.py` of the same name). Total: 206 cocotb tests, 128 model
unit tests.

| id | tier | what | tests (cocotb + model) | model lines |
|---|---|---|---|---|
| `p_adler32` | T1 | Adler-32 checksum engine with word writes | 5 + 3 | 41 |
| `p_adt7420_oneshot` | T2 | ADT7420 one-shot temperature readings (wrapper) | 6 + 3 | 83 |
| `p_adxl362_activity` | T2 | ADXL362 activity interrupt monitor | 4 + 3 | 39 |
| `p_bin2bcd` | T1 | Signed binary to BCD converter with display | 5 + 3 | 62 |
| `p_crc8_engine` | T1 | Bit-serial CRC-8 engine | 5 + 4 | 63 |
| `p_digital_clock` | T1 | Time-of-day clock with 12/24 hour display | 6 + 4 | 66 |
| `p_hamming84` | T1 | Hamming (8,4) encoder and decoder | 5 + 4 | 58 |
| `p_handshake_fsm` | T1 | Four-phase request/acknowledge responder | 5 + 4 | 55 |
| `p_hcsr04` | T2 | Ultrasonic ranger with median-of-three filtering | 5 + 3 | 46 |
| `p_hdlc_tx` | T2 | HDLC-style framer with bit stuffing and FCS | 5 + 4 | 74 |
| `p_i2c_slave_mem` | T2 | I2C slave memory at address 0x2A (wrapper) | 5 + 3 | 85 |
| `p_manchester_rx` | T2 | Manchester frame receiver with error classes | 5 + 3 | 71 |
| `p_manchester_tx` | T2 | Manchester-coded byte transmitter on a Pmod pin | 5 + 3 | 49 |
| `p_morse_beacon` | T1 | Morse code beacon with message buffer | 5 + 3 | 60 |
| `p_moving_avg` | T1 | Six-sample moving average with clipping | 5 + 3 | 41 |
| `p_nec_rx` | T2 | Infrared remote receiver (NEC style) with tolerant timing | 5 + 3 | 80 |
| `p_nec_tx` | T2 | Infrared remote transmitter (NEC style) with repeat codes | 5 + 4 | 66 |
| `p_onewire_id` | T2 | One-wire style master reading a 16-bit ID with CRC (wrapper) | 5 + 3 | 48 |
| `p_peak_bar` | T1 | LED bar graph with decaying peak marker | 6 + 4 | 52 |
| `p_period_meter` | T1 | Edge period meter with stall detection | 5 + 3 | 48 |
| `p_phase_pwm3` | T1 | Three-phase staggered PWM | 5 + 3 | 37 |
| `p_pulse_stretch` | T1 | Retriggerable pulse stretcher | 5 + 3 | 41 |
| `p_quad_decoder` | T1 | Quadrature decoder fed from switches | 5 + 3 | 43 |
| `p_rate_mult` | T1 | Rate multiplier (N ticks in every M clocks) | 5 + 3 | 51 |
| `p_rr_arbiter` | T1 | Four-way round-robin arbiter with a hold limit | 5 + 4 | 53 |
| `p_sat_accum` | T1 | Saturating accumulator on the switches | 6 + 4 | 54 |
| `p_sd_spi_init` | T2 | SD card initialisation in SPI mode | 7 + 3 | 51 |
| `p_seq_detect` | T1 | Programmable serial pattern detector | 5 + 3 | 44 |
| `p_serial_divider` | T1 | Sequential 16-bit divider with cycle count | 5 + 3 | 49 |
| `p_servo_pwm` | T1 | Hobby-servo pulse generator | 5 + 2 | 32 |
| `p_servo_rx` | T2 | Radio-control pulse reader with failsafe | 5 + 3 | 52 |
| `p_sigma_delta_dac` | T2 | First-order sigma-delta DAC on the audio output | 5 + 3 | 39 |
| `p_spi_slave_regs` | T2 | SPI slave with a small register file | 5 + 3 | 76 |
| `p_stepper_ramp` | T2 | Step and direction generator with trapezoidal speed ramp | 5 + 3 | 65 |
| `p_tennis_score` | T1 | Tennis game scoreboard | 6 + 3 | 79 |
| `p_timer_compare` | T1 | Prescaled 32-bit timer with two output-compare channels | 5 + 3 | 71 |
| `p_tone_gen` | T2 | Eight-note square-wave tone generator on the audio output | 5 + 2 | 47 |
| `p_vga_disc` | T2 | VGA 640x480 disc on a bordered screen | 5 + 3 | 48 |
| `p_window_wdt` | T1 | Window watchdog with fault pulse | 5 + 3 | 57 |
| `p_ws2812_gen` | T2 | Addressable LED strip frame generator | 5 + 4 | 58 |

## Status and caveats

- No simulator was run. The acceptance benches were checked by `py_compile`, by importing every `acceptance.py` (all
  names from `model.py` and `poollib.py` resolve) and by an undefined-name scan; the models by their unit tests. The
  first run against a real design may expose test bugs: fix the test, never weaken a check to make a design pass.
- Several benches compare the RTL clock by clock with a cycle model (`rr_arbiter`, `handshake_fsm`): they allow the RTL
  to lag the model by 0..4 clocks (`poollib.align`). Others use exact run lengths, exact waveforms or exact edge spacings
  that the spec states in clocks (`pulse_stretch`, `servo_pwm`, `tone_gen`, `manchester_tx`, `ws2812_gen`, `hdlc_tx`,
  `nec_tx`, `stepper_ramp`, `vga_disc`, `onewire_id`).
- Specs with a bidirectional pin or bus have a hidden SystemVerilog wrapper (`tb_<id>.sv`: `tri1` nets with a
  testbench pull-down): `onewire_id`, `i2c_slave_mem`, `adt7420_oneshot`. The design's pin is `inout` and is only ever
  driven low or released.
- Time-sensitive register reads: a shell read takes about 1200 clocks at `CLKS_PER_BIT` = 8 (the effect lands about 640
  clocks after the request starts). Benches that depend on that (`window_wdt`, `servo_rx`, `period_meter`, the
  busy/drop tests) use thresholds with margins of 400 clocks or more and say so in comments; if a bench shows a
  timing-dependent failure, check the margins first.
- Spec details that the user text leaves open on purpose (so the interview has work): polynomials/initial values,
  glyph and polarity choices, thresholds, reset values, error priorities, what a write while busy does. They are all
  answered in `hidden/spec.yaml`.
