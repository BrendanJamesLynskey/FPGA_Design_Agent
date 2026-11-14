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
  Its slack is smaller (probably the rejection tests in front of the register write strobes; not investigated); at 10 ns it
  still closes with 2.6 ns to spare. One run each: the differences are single builds, not a distribution.
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
- Formal (SymbiYosys) properties were not added for the strict rejections; the local machine has no SymbiYosys. The
  rejections are checked in simulation with seeded faults.
- The error capture does not say which cause (hole, unaligned, partial write, reserved bit) made an access bad.
