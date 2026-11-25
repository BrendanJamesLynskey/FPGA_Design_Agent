# Results: register power-up values, AMD against Altera, measured (brief 206)

The owner's question: "I always thought that the FPGA configuration process enabled free preset of regs. I have done this
with Xilinx. I'm surprised that Altera is different." Brief 204's study said that AMD loads 0 or 1 for free through the
global set/reset (GSR), and that Altera registers power up at 0, so a 1 costs inverters (NOT-gate push-back). This brief
measured what is actually true for each family, what it costs, and when the cost is more than zero. The plan and the
expectations were written before any run: [PLAN_AND_PREREGISTRATION.md](PLAN_AND_PREREGISTRATION.md), with two dated
amendments for follow-up arms.

**Short answer.**
- **AMD, both families measured:** you are right. Every fabric and IOB flip-flop takes an initial value of 0 or 1 for free,
  whatever the sense of its reset.
- **Altera:** the study was right for the core. Every core register powers up 0, and a 1 is made with inverters.
- **The I/O registers are the exception:** on Cyclone IV E, Cyclone V and MAX 10 they power up high natively.
- **The real cost is at the hard blocks, on both vendors.** A 1 on a register next to a multiplier or a RAM keeps that
  register out of the block. On Altera a power-up 1 on a RAM's read register cost the whole RAM: a 256 x 16 RAM was built
  from about 7,100 logic cells instead of one M9K.

Tools: Vivado 2026.1 (synthesis out of context, plus placement for the IOB arm), Quartus Prime Lite 25.1std (full
compile), xsim (AMD), and Icarus Verilog 12 on Quartus's post-fit netlists. One run per arm. Both Vivado and Quartus are
deterministic for a fixed input, but run-to-run noise was not estimated. The X8 and X9 arms ran three times on Vivado and
gave identical counts each time (main batch, follow-up batch, scan re-run).

## What the vendors say (sources)

Tags: **B** body text read; **S** search-result snippet only.

- **AMD**
  - UG949 v2025.2 p.50 and p.71 (B): the GSR loads each register's initial value at the end of configuration. AMD
    recommends initialising every register, SRL and memory instead of adding a reset only for that.
  - UG474 v1.9 p.20 (7 series) and UG574 v1.6 p.18 (UltraScale) (B): INIT is set separately from the SR set/reset value.
  - UG901 v2025.2 p.251 (B): an initial value becomes INIT, independent of any local reset.
  - UG473 v1.14 p.32 (B): the GSR loads the block-RAM output latches and registers from INIT_A/INIT_B.
  - UG573 v1.14 p.90 (B) and UG901 p.122 (B): UltraRAM powers up 0 and has no user INIT.
  - UG573 p.41 (B): block RAMs used for bitstream-authentication keys always start at 0.
  - UG479 and UG579 (B, by absence): no INIT attribute on the DSP48 pipeline registers.
- **Altera**
  - Quartus Prime Standard Edition Design Recommendations UG-20175 18.1 (2018-09-24), section 2.5.1, p.67-69 (B):
    - core registers power up low on all devices, and a high power-up is made by NOT-gate push-back;
    - with aload, a reset of 1 needs no push-back;
    - the Power-Up Level option, and the warning that a high level on a large entity hurts QoR;
    - a VHDL integer with no initial value powers up at the left end of its range;
    - where the architecture lacks a second asynchronous control, a power-up level that conflicts with the reset is
      ignored.
  - Same guide, section 2.4.1.11 p.60 (B): dedicated RAM outputs power up 0 even with a .mif.
  - Cyclone IV Device Handbook vol. 1, CYIV-5V1-2.2 (March 2016) (B):
    - LEs have asynchronous clear only, and a preset is made by push-back (PDF p.35);
    - M9K outputs power up cleared (p.38, p.54);
    - **IOE registers can be programmed to power up high or low** (p.112).
  - Cyclone V Device Handbook vol. 1, CV-5V2 (2017-09-19) (B): ALM register ports, and a LAB-wide preset or asynchronous
    load shared with clock enable 0 (p.1-5). DSP and M10K output registers clear at power-up (Table 2-4, DSP chapter).
  - MAX 10 FPGA Device Architecture, M10-ARCHITECTURE 2017.02.21 (B): the same LE preset rule as Cyclone IV.
  - MAX 10 GPIO User Guide 683751 22.1 (S): the GPIO Lite IP has a "power up high" option for DDR I/O registers.

## Measured: AMD (Vivado 2026.1)

xc7a35tcpg236-1 and xck26-sfvc784-2LV-c gave **the same result in every arm**. The counts below hold for both parts.
Records: `records/amd_<part>.tsv`, `records/amd_<part>_b.tsv`, `records/amd_<part>_scan.tsv`; messages per arm:
`records/amd_logs/`.

| Arm | RTL | Initial value 0 | Initial value 1 |
|---|---|---|---|
| X1 | 8-bit register, no reset | 8 FDRE INIT 0, 0 LUT | 8 FDRE INIT 1, 0 LUT |
| X2 | synchronous reset to 0 | 8 FDRE INIT 0 | 8 FDRE **INIT 1** (reset value 0 kept), 0 LUT |
| X3 | synchronous set to 1 | 8 FDSE **INIT 0** | 8 FDSE INIT 1 |
| X4 | asynchronous clear | 8 FDCE INIT 0 | 8 FDCE **INIT 1** |
| X5 | asynchronous preset | 8 FDPE **INIT 0** | 8 FDPE INIT 1 |
| X6 | 64-bit, 3 stages, no logic | 192 FDRE INIT 0, 0 LUT | 192 FDRE INIT 1, 0 LUT |
| X7 | IOB input and output registers (IOB = TRUE), no reset / sync reset 0 / async clear (placed) | in ILOGICE2.IFF and OLOGICE2.OUTFF (7 series), BITSLICE_COMPONENT_RX_TX (UltraScale+), INIT 0 | **same sites, INIT 1**, all three reset styles; report_drc after placement raised no rule about INIT (7 series: UCIO-1, CFGBVS-1; UltraScale+: UCIO-1, RTSTAT-1, RTSTAT-2 and RTSTAT-8, all from the bench having no pin constraints and no routing) |
| X8 | 18 x 18 multiply, A, B, M, P registers | 1 DSP, AREG = BREG = MREG = PREG = 1, **0 FF** | 1 DSP, **AREG = BREG = MREG = PREG = 0, 108 FDRE in the fabric**, no warning (only the DSP Final Report shows the empty columns) |
| X8b | only P register at 1 | all absorbed | A, B absorbed, M becomes PREG, **P (36 FDRE) in fabric** |
| X8c | only A, B at 1 | all absorbed | M, P absorbed, **A, B (36 FDRE) in fabric** |
| X9 | 1K x 32 block RAM, read register A5A50F0F, output register 3C3CF0F0 | 1 RAMB36, DOB_REG = 1, 0 FF | read register value goes to INIT_B; **DOB_REG = 0, output register as 32 FDRE**; INFO Synth 8-7052 only |
| X9b | read and output registers both 3C3CF0F0 | as X9 | **DOB_REG = 1, INIT_B = 3C3CF0F0, 0 FF** (one value per port fits) |
| X9c | only the output register non-zero | as X9 | **DOB_REG = 0, 32 FDRE** (latch 0 and register non-zero are two values) |
| X10 | 32 x 8 LUT RAM and a 16-deep SRL with contents | INIT all 0 | RAM32X1S INIT AAAAAAAA ... and SRL16E INIT 16'h1F77: honoured |
| X11 | 4K x 72 `ram_style = "ultra"` (xck26) | 1 URAM288 | **WARNING Synth 8-12183: ram_style ultra ignored because of a non-zero INIT; 8 RAMB36E2 + 15 LUTs** |
| X12 / X12b | VHDL `integer range -8 to 7`, no initial value / `:= 0` | X12b: 4 FDRE INIT 0, 4 LUTs | X12: 4 FDRE, top bit INIT 1 (powers up -8), 4 LUTs: no cost, different start |
| X13 | GSR in xsim, post-synthesis netlist of X2 and X4 (xc7a35t) | 00 during and after GSR | **FF during GSR and after it**; X2's synchronous reset gives 00 at the next edge; X4's asynchronous clear gives 00 at once (`records/amd_gsr_sim.txt`) |

## Measured: Altera (Quartus Prime Lite 25.1std)

Parts: EP4CE22F17C6 (Cyclone IV E), 10M50DAF484C7G (MAX 10, the DE10-Lite part) and 5CEBA4F23C7 (Cyclone V). The arms
are compiled together in one top (`altera/rtl/q_top.sv`), each on its own clock, with virtual pins except the I/O arm.
Fitter figures: LEs (Cyclone IV E, MAX 10) and "ALMs needed" (Cyclone V; fractional). Fmax is the slow 85 °C model,
unrestricted, for arms with register-to-register paths. Records: `records/altera/q_<fam>_i<INITV>_pb<ON|OFF>.json`;
gate-level simulation: `records/altera_gate_sim.txt`.

| Arm | Cyclone IV E: 0 / 1 | MAX 10: 0 / 1 | Cyclone V: 0 / 1 |
|---|---|---|---|
| Q1 8-bit register to a port | 8 / 8 LE (inverter in the register's own LE) | 8 / 8 LE | 0 / 4 ALM (+8 ALUT) |
| Q2 synchronous reset 0, power-up 1 | 8 / 8 LE; **powers up FF, reset gives 00** | 8 / 8 LE; same | 2 / 4 ALM |
| Q3 asynchronous clear, power-up 1 | **Critical Warning 18010 "will power up to Low"**; powers up 00 | same | same warning |
| Q4 asynchronous preset, power-up 0 | **Critical Warning 18010 "will power up to High"**; powers up FF | same | same warning |
| Q5 fast input and output registers, power-up 1 | in the IOE, netlist `power_up = "high"`, **no logic added**; powers up F | same | in DDIOIN/DDIOOUT cells, `power_up = "high"`, no logic added |
| Q6a registers around an 18 x 18 multiply | 0 / **89 LE, 72 regs in fabric**; Fmax 290.53 / 213.04 MHz | 0 / 87 LE; 233.1 / 180.28 MHz | 0 / 36 ALM; 339.9 / 146.84 MHz |
| Q6b RAM 256 x 16, registered read, power-up 1 | 1 M9K + 25 LE / **no M9K, 7144 LE, 4137 regs**; 715.82 / 182.82 MHz | 1 M9K / no M9K, 7145 LE; 606.43 / 152.42 MHz | 1 M10K / no M10K, 3626.4 ALM; 585.48 / 172.53 MHz |
| Q7 64-bit, 3 stages, no logic | 192 / 192 LE (64 inverters packed into the registers' LEs) | 192 / 192 LE | 6.5 / **32 ALM (+64 ALUT)** |
| Q8 64-bit with a 4-input function between stages | 192 / 201 LE (+9) | 192 / 198 LE (+6) | 64 / 96 ALM (+64 ALUT) |
| Q9 VHDL integer, no initial value | 5 LE, powers up 8 (-8) | same | 2 ALM |

- Q6b: "RAM logic is uninferred due to asynchronous read logic" (Info 276007). The read register cannot sit in the M9K or
  M10K, whose outputs power up 0, so the read becomes asynchronous and the RAM is built from logic. This is the largest cost
  measured. Quartus reports it only as an Info message.
- `NOT_GATE_PUSH_BACK OFF` changed nothing. Quartus prints Warning 18057 ("the assignment to disallow NOT gate push-back
  ... is ignored") for every register with a power-up level, and the counts equal the ON case. The power-up level wins.
- Push-back also sets DEV_CLRn to set rather than clear such registers (Info 13003). On the LE families every core
  register in the post-fit netlist has `power_up = "low"`. Only the I/O registers carry `"high"`.
- Fmax differences of a few percent on the arms without a hard block (Q7, Q8, Q5) are placement noise from one run.
  Q7's unrestricted Fmax rose with power-up 1 on Cyclone IV E (865.05 to 1118.57 MHz). Only the hard-block arms (Q6a, Q6b) show
  a real drop.

**Gate-level power-up simulation.** Cyclone IV E and MAX 10 ran in Icarus Verilog on the post-fit netlists, using
Quartus's own atom models. For MAX 10, our stand-ins replace four encrypted inner modules (buffers, the user-flash and
ADC blocks), which have no effect on registers (`altera/sim/encrypted_stubs.v`). The output before the first clock is as
the netlist says:
- power-up 1 gives FF on Q1, Q2, Q6, Q7 and Q8, and F on the I/O arm;
- Q3 gives 00, because its power-up level was ignored;
- Q4 gives FF, because the preset wins over a power-up of 0;
- Q9 gives 8.

Cyclone V did not run: its DSP model `cyclonev_mac` is encrypted. Questa FSE, which could run it, has no licence here
(`records/questa_licence_probe.txt`). Cyclone V's netlist power-up parameters are still recorded.

## Pre-registered expectations against results

| # | Expected | Result |
|---|---|---|
| E1, E2 | AMD INIT free, any reset sense | confirmed (X1 to X6, both parts) |
| E3 | IOB keeps INIT | confirmed (X7, both parts, all reset styles; DRC silent) |
| E4 | DSP-adjacent INIT 1 kept out of the DSP | confirmed, with no warning (X8, X8b, X8c) |
| E5 | BRAM output register INIT honoured via INIT_A/B | **partly wrong**: only when the read and output registers share one value (X9b); otherwise the output register stays in the fabric (X9, X9c) |
| E6 | LUTRAM and SRL INIT honoured | confirmed |
| E7 | URAM with contents falls back or errors | confirmed: falls back to block RAM with WARNING Synth 8-12183 |
| E8 | VHDL integer: -8 or 0 (50/50) | -8 on both Vivado and Quartus |
| E9 | GSR loads INIT; the opposite reset then wins | confirmed (X13) |
| E10 | Altera plain register power-up 1 costs 0 LE/ALM | true on Cyclone IV E and MAX 10 (inverter in the register's own LE); **wrong on Cyclone V (+4 ALM for 8 bits)** |
| E11 | sync reset 0 + power-up 1 works | confirmed (gate sim: FF, then 00 after the reset edge) |
| E12 | async clear + power-up 1 ignored, warned | confirmed (Critical Warning 18010) |
| E13 | async preset powers up 1 | confirmed, even when power-up 0 was asked (Critical Warning) |
| E14 | Cyclone IV/MAX 10 I/O registers power up high natively | confirmed; **Cyclone V too** (expected push-back there) |
| E15 | DSP/RAM-input register at 1 not absorbed | confirmed, and far worse for the RAM read register (whole RAM lost) |
| E16 | register-to-register costs LEs and Fmax | **wrong on the LE families** (0 LE; the inverters pack into the registers' own LEs; no real Fmax change); true on Cyclone V (+25.5 ALM) |
| E17 | logic between stages absorbs the inverters (0 extra) | **wrong**: +9 LE (C IV E), +6 LE (MAX 10), +32 ALM (C V) |
| E18 | VHDL integer powers up -8 | confirmed (gate sim shows 8) |
| E19 | gate-level sim confirms | confirmed on Cyclone IV E and MAX 10; Cyclone V not run (encrypted DSP model, no Questa licence) |

## Our inference (what to do)

- On AMD an initial value is free and kept everywhere **except** on a register that should go into a DSP48, a block-RAM
  output register or UltraRAM. There it silently moves the register into the fabric, or for UltraRAM changes the memory
  type.
- On Altera core registers an initial value of 1 is cheap on the LE families (Cyclone IV E, MAX 10) and costs some logic
  on Cyclone V. It is expensive next to a DSP or RAM, worst of all on a RAM's read register. A power-up level that disagrees
  with an asynchronous clear or preset is ignored, with a Critical Warning.
- I/O registers on all three Altera families power up high natively.
- The cost is non-zero in these cases:
  1. a register that should be absorbed by a hard block (both vendors);
  2. Cyclone V ALMs, where a register-only ALM must add an ALUT;
  3. a power-up that conflicts with an asynchronous reset (Altera: the power-up is lost, so the cost is correctness rather
     than area).
- A plain register-to-register chain costs nothing on the LE families: the inverters cancel inside the chain, and the two
  at the ends pack into the registers' own LEs.

The house rule written from these results is in the brief 206 report and the KB skill `power-up-values-amd-and-altera`.

## Records

- `PLAN_AND_PREREGISTRATION.md`: the plan, the 19 expectations (stamped 17:34 GMT before any run) and the dated
  amendments.
- `amd/rtl/pu_arms.sv`, `amd/rtl/x12_vhdl_int.vhd`, `amd/rtl/x12b_vhdl_int0.vhd`: the AMD arms.
- `amd/tcl/arms.tcl`, `amd/tcl/arms_b.tcl` and `amd/tcl/arms_scan.tcl`: the Vivado batch scripts. `amd/run_amd.sh`,
  `amd/run_amd_b.sh` and `amd/run_amd_scan.sh` are the drivers.
- `amd/split_log.py`: splits the log per arm. `amd/sim/tb_gsr.v` and `amd/sim/run_gsr.sh` are the GSR simulation.
- `records/amd_<part>.tsv`, `records/amd_<part>_b.tsv` and `records/amd_<part>_scan.tsv`: one line per arm, value and
  measurement (part, arm, initial value, key, value).
- `records/amd_logs/messages_<part>[_b].tsv`: every WARNING and CRITICAL WARNING per arm, plus INFO lines that mention
  INIT, power or SRVAL. This brief's own "no cells matched" lines (Vivado 12-180) are removed.
- `records/amd_gsr_sim.txt`: the X13 simulation output.
- `records/init_scan/`: the agent's `fda_init_scan` output on each X8, X9, X11 and X12b netlist. Also
  `xck26_x11_1_synth_8_12183.log`, the URAM warning lines. These are the test fixtures of `flow/tests/test_206_init_values.py`.
- `altera/rtl/q_top.sv`, `altera/tcl/q_project.tcl` and `altera/tcl/q.sdc`: the Quartus arms and project.
  `altera/run_altera.sh` is the driver and `altera/parse_quartus.py` reads one case into JSON.
- `records/altera/q_<fam>_i<INITV>_pb<ON|OFF>.json`: per case, the fitter and synthesis entity tables, Fmax, the I/O
  pin register columns, the power-up messages and the netlist `power_up` counts per arm.
- `altera/sim/tb_q.v`, `altera/sim/run_q_sim.sh`, `altera/sim/encrypted_stubs.v` and `altera/sim/glbl_stub.v`: the
  gate-level simulation.
- `records/altera_gate_sim.txt`: its output.
- `records/questa_licence_probe.txt`: why Questa FSE did not run.
- `records/summary.json`: every number in this README, built by `summary.py` from the records above.

## Reproduce

- AMD: take a heavy slot, then run `amd/run_amd.sh <build>`, `amd/run_amd_b.sh <build>` and `amd/run_amd_scan.sh <build>`.
  Each driver runs both parts under `systemd-run --user --scope -p MemoryMax=5G` or `6G`. Vivado reported a peak of 4.7 GB (xck26 run). The xc7a35t pass takes about 15 minutes and the xck26 pass about 20.
- AMD GSR simulation (sim only): `amd/sim/run_gsr.sh <build>/net <work>`.
- Altera: take a heavy slot, then run `altera/run_altera.sh <build>/q`, which compiles nine cases in sequence. A case
  takes 30 s to 3 min; the power-up-1 cases are slow because the RAM is built from logic. Then run
  `altera/parse_quartus.py <build>/q/<case> > records/altera/<case>.json` for each case.
- Altera simulation: `altera/sim/run_q_sim.sh <build>/q > records/altera_gate_sim.txt`. This needs Icarus Verilog 12.
- `python3 summary.py` rebuilds `records/summary.json`, and `--check` tests it against the records.
- A different Vivado or Quartus release can give different counts.

## Known gaps and limits

- One run per arm and no noise estimate (X8 and X9 were repeated three times on Vivado with identical counts). Fmax
  differences under about 10 % on the arms without a hard block are placement noise.
- No board: the IOB and I/O-register power-up values are what the tools put in the netlist and bitstream settings, not
  values read on hardware. The 7 series ILOGIC/OLOGIC INIT was not checked in the bitstream bits. UG574's note that
  Laguna (SLR-crossing) flip-flops share INIT per TX/RX pair does not apply to the single-SLR K26 and was not tested.
- The AMD simulation is functional (the unisim FDRE/FDCE models with `glbl`), not timing.
- The Altera simulation is functional on Icarus with the vendor atom models; no SDF was used.
- Cyclone V was not simulated (encrypted DSP model).
- Questa FSE was not used: there is no licence (`SALT_LICENSE_SERVER` not set). The owner can request the free licence
  if a Questa run is wanted.
- MAX 10 configuration from its internal flash against JTAG SRAM loading was not measured: no board runs in this brief.
  The device documents describe the same POR and user-mode entry for both, and the register power-up comes from the same
  configuration image. Documentation only.
- Altera Design Assistant was not run (brief 204 noted it may not support MAX 10).
- Cyclone V "ALMs needed" is the fitter's packing estimate (fractional), not a count of whole ALMs.
- Hyperflex parts (Stratix 10, Agilex) were not tested: they are not in Quartus Lite. AN 919 (snippet only) recommends
  removing initial conditions there.
- The VHDL integer arm Q9 has no explicit-0 pair on Altera. Its cost is not separated; its power-up value is measured.
