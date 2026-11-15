# Interface profiles: results (brief 73)

In plain words:
- The same register map (`hwsw/examples/demo_accel.yaml`, 13 registers of its own and an interrupt, 4 KB window) built
  out of context under each interface profile costs, in Vivado 2026.1 on an xc7a100t at 10 ns, one run each:

| Profile | LUTs | Flip-flops | WNS at 10 ns | Against `house` |
|---|---|---|---|---|
| `house` | 248 | 262 | 5.147 ns | |
| `amd_compatible` | 180 | 241 | 5.634 ns | 68 fewer LUTs, 21 fewer flip-flops (no error-capture registers) |
| `strict` | 286 | 266 | 2.567 ns | 38 more LUTs, 4 more flip-flops, 2.6 ns less slack |

- `amd_compatible` is cheaper than `house` because it leaves the error-capture registers out; its 180 LUTs and 241
  flip-flops are the figures brief 64A3 measured for the `okay` setting without the capture (a reproduction, one run each).
- `house` reproduces brief 64A3's `split` with the capture (248 LUTs, 262 flip-flops).
- `strict` adds the rejections (the strobe, alignment and reserved-bit tests in the write decode, the SLVERR path on both
  channels, the capture of every rejected access) and the capture's interrupt: 38 LUTs and 4 flip-flops over `house`.
  Its slack is smaller; the cause is read from the committed timing reports below (brief 80). At 10 ns it still closes with
  2.6 ns to spare. One run each: the differences are single builds, not a distribution.
- **Why `strict` has 2.6 ns less slack (brief 80, from `raw/<profile>/timing_summary.rpt`, no rebuild).** The worst setup
  path is a different path in each build:

  | Profile | Worst path | Logic levels | Data path | of which routing | CE setup | Slack |
  |---|---|---|---|---|---|---|
  | `house` | `aw_got_reg` to `job_cycles_lo_value_shadow_reg[17]/CE` | 4 | 4.600 ns | 3.317 ns | 0.169 ns | 5.147 ns |
  | `amd_compatible` | `aw_word_reg[9]` to `job_cycles_hi_value_shadow_reg[11]/CE` | 3 | 4.113 ns | 2.919 ns | 0.169 ns | 5.634 ns |
  | `strict` | `w_strb_reg[3]` to `ecap_addr_reg[2]/CE` | 7 | 6.977 ns | 5.391 ns | 0.372 ns | 2.567 ns |

  The 2.58 ns between `house` and `strict` is 2.377 ns more data path (three more LUT levels and 2.07 ns more routing) plus
  0.203 ns more setup time, because the end point is a clock-enable pin of a 12-bit register with a fan-out of 11. The extra
  levels are the rejection test: in the generated block (`results/73_profiles/generated/strict/demo_accel_regs.sv`) a write
  that the profile rejects raises `wr_rej` (the per-register strobe and reserved-bit tests in the write decode, lines
  165-253), `wr_rej` feeds `ecap_bad_wr` (line 490) and so the clock enable of the error-capture registers (line 501), and
  also the response `s_axil_bresp` (line 146). In `house` and `amd_compatible` no write is rejected (`wr_rej` does not exist
  in the generated file), so that cone is absent. Routing is 77 % of the strict path against 72 % in `house`. A way to cut
  the path, not tried: register `wr_rej` and capture one clock after the response. It would delay the capture by a clock, so
  it is a design decision (the datasheet's capture timing would change), not a free fix.
- Simulation: the same bench, with the 59A protocol checker and brief 71's missing-response monitor on the wires, passes on
  the map under each profile; eleven seeded faults in the strict RTL are each caught (`hwsw/tests/test_64a_regmap_rtl.py`).

Out-of-context builds only; nothing here has run on a board. How the profiles work: [docs/hwsw.md](../../docs/hwsw.md#interface-profiles-brief-73).

## Records

| File | What | Made by |
|---|---|---|
| `regmap_ooc_profiles.json` | LUTs, flip-flops, WNS, the resolved settings and the model hash for each profile, and the differences against `house` | `python3 hwsw/regmap_ooc.py --series 73` (Vivado 2026.1 build 6511674, xc7a100tcsg324-1, out of context, clock read first, one thread, one run per profile; `hwsw/regmap_ooc.tcl`) |
| `raw/<profile>/` | the raw reports each entry is read from: `utilization.rpt`, `timing_summary.rpt`, `summary.txt`, `clock.xdc` | the same run |
| `generated/<profile>/demo_accel_regs.{sv,md}` | the block and its datasheet for each profile, so the differences can be read side by side (the C header and Python driver are generated too, and not kept here) | `python3 -m hwsw.regmap gen <map without its unmapped: line> --spec hwsw/examples/profiles/spec_<profile>.yaml --out DIR` |

## Reproduce

Vivado runs take a heavy slot (`_handoff/take_heavy_slot.sh`) and run under `systemd-run --user --scope -p MemoryMax=...`
(the script itself starts each run in a 4 GB scope).

```
# the three builds (about 4 minutes each on the build PC); writes regmap_ooc_profiles.json and raw/<profile>/
python3 hwsw/regmap_ooc.py --series 73
# the generated blocks and datasheets, side by side
grep -v '^unmapped:' hwsw/examples/demo_accel.yaml > /tmp/demo_accel.yaml
python3 -m hwsw.regmap gen /tmp/demo_accel.yaml --spec hwsw/examples/profiles/spec_strict.yaml --out /tmp/strict
# simulation (Icarus, cocotb): the demo map under each profile, and the eleven strict-RTL faults
python3 -m pytest -q hwsw/tests/test_64a_regmap_rtl.py -k "profile or strict_rtl_mutant"
# the profile rules and the axi_profile check (no simulator)
python3 -m pytest -q hwsw/tests/test_73_profiles.py flow/tests/test_73_axi_profile.py
```

## Known gaps and limits

- One configuration (one map, one part, one clock), one run per profile; a larger map or a tighter clock may move the
  strict cost differently.
- The Arm behaviour of SLVERR on a load and on a posted write is still expected, not measured (brief 64B item 5).
- Formal (SymbiYosys): brief 80 added properties for the strict rejections (`hwsw/tests/regmap_formal.py` `conformance`,
  `hwsw/tests/test_80_strict_formal_rtl.py`, record in `results/80_cleanup/README.md`): the block must answer SLVERR for an
  unaligned address, an unmapped one, a strobe pattern covering part of a multi-byte field and a 1 in a reserved bit, OKAY
  otherwise, change no software-writable output on a rejected write, and return 0 for an unaligned or unmapped read; nine
  seeded faults are each found. A bounded proof (depth 20), not an unbounded one.
- The error capture does not say which cause (hole, unaligned, partial write, reserved bit) made an access bad.
