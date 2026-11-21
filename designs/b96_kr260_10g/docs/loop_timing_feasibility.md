# Loop-timed transmit and GTH buffer bypass for the 10G link: feasibility (brief 96F, 2026-11-19 night)

Status: **paper and simulation only.** Nothing here ran on a board, in Vivado or in xsim. The only code is a Python model of the tracking loop
(`model/loop_timing.py`, records in `results/b96f/`). Every hardware claim carries a document, section and page; anything that could not be
read is marked **unconfirmed**. Documents read: UG576 v1.7.1 (18 Aug 2021, local copy `_amd_docs/UG576_ug576-ultrascale-gth-transceivers.pdf`,
page numbers are the printed ones), DS925 v1.30 (9 Jul 2026, local), the AMD board files `kr260_carrier` 1.1 (local copy shipped with Vivado), the knowledge
bank's KR260 and K26 notes, and, as web pages, PG182 v1.7 search results, a third-party summary of the article the brief names, and secondary
sources for IEEE 802.3 and ITU-T G.8262 (the standards are not on this machine). XAPP1276 itself could not be retrieved by 96F (the AMD page timed out). **Brief 96F2 later read it (the Japanese translation, v1.2) and AMD's low-latency blog; see `docs/loop_timing_sources.md`, which corrects verdict 10, the V1 definition and the TXPI remark below.**

## 1. Verdicts

| # | Item | Verdict | Basis |
|---|---|---|---|
| 1 | GTHE4 QPLL fractional-N, resolution | **Feasible, confirmed** | UG576 p.51 (Equations 2-5, 2-6, Table 2-13): `SDMDATA` 0 to 2^24 - 1, `SDMWIDTH` 16, 20 or 24, UltraScale+ only. One step at N = 66 is 0.9 ppb of the VCO (0.0009 ppm). |
| 2 | Run-time update of the fraction | **Feasible, confirmed in principle** | UG576 p.57 to 58 ("Dynamic Frac-N", Figures 2-14, 2-15, Table 2-16): `SDM*DATA` stable one system clock, then `SDM*TOGGLE` high 3 and low 3 feedback clocks; "to achieve the same functionality that the TXPIPPM provides". A deviation of more than 200 ppm from the VCO frequency at the last QPLL reset needs a QPLL reset (p.58). |
| 3 | Reaching the dynamic ports from the Transceiver Wizard | **Answered by brief 96F1 (Vivado 2026.1 probe, `results/b96f1/wizard_probe/`): not through the core; yes with the QPLL outside it** | Inside the Wizard core the SDM ports are tied to constants and only the static numerator (`TX_/RX_QPLL_FRACN_NUMERATOR`) exists; with `LOCATE_COMMON = EXAMPLE_DESIGN` the core takes `qpll0clk_in`/`qpll0refclk_in` and our own `GTHE4_COMMON` instance exposes `SDM0DATA`/`SDM0TOGGLE`. (Was: unknown. Original text follows.) PG182 v1.7 has a static "QPLL Fractional-N" numerator (0 to 16777215, 0 = off; search result, Advanced Clocking Section). Whether `SDM0DATA`/`SDM0TOGGLE` can be exposed is not in anything read; a Wizard property probe (a Vivado job, not run: both heavy slots were taken) or a hand-instantiated `GTHE4_COMMON` or DRP writes (UG576 Appendix C lists `SDM0DATA1_0`/`SDM0DATA1_1`) would settle it. |
| 4 | CPLL as the steered PLL | **Not feasible** | UG576 p.51: fractional-N is "supported using the QPLL"; the CPLL has none (Table 2-9, p.47). DS925 v1.30 Table 99: CPLL line rate at output divider 1 is 4 to 8.5 Gb/s for this speed grade, so 10.3125 Gb/s is outside it anyway. |
| 5 | A fabric-generated reference into the QPLL | **Not feasible** | UG576 p.42 (`GTGREFCLK`): "reserved for internal testing purposes only". |
| 6 | What drives the SFP+ reference on the KR260 | **Unconfirmed** | See section 3. The pins (`MGTREFCLK0` of quad 224, Y6/Y5) and 156.25 MHz working on the owner's board are confirmed; the source device and whether it is programmable are not in any document read. |
| 7 | Centring the fractional range (nominal sits mid-range) with the board's reference | **Not feasible as built; routes exist** | At 156.25 MHz the nominal N is exactly 66.0 for every reference divider M, so a fixed 156.25 MHz reference can only tune one way from the nominal (section 4). Two-window operation, TXPI-biased windows (modelled), or a programmable reference (unconfirmed) are the routes. |
| 8 | RX buffer bypass | **Feasible, documented** | UG576 p.255 to 256, 259 to 260 and 270 to 271: `RXBUF_EN = FALSE`, `RX_XCLK_SEL = RXUSR`, `RXOUTCLKSEL = 010` (recovered clock drives `RXUSRCLK`), single-lane auto mode. It needs no frequency steering, because `RXUSRCLK` is the recovered clock (our RX domain already is). `RXSLIDE_MODE` must not be AUTO or PMA (p.249): our PCS slips in fabric, so unaffected. |
| 9 | TX buffer bypass with the transmit clock from the QPLL | **Feasible, documented** | UG576 p.135, 137 to 142: `TXBUF_EN = FALSE`, `TX_XCLK_SEL = TXUSR`, `TXOUTCLKSEL` = 011, 100 or 101 (reference clock or the programmable divider of the PLL; 101 follows a tuned QPLL), auto alignment by `TXDLYSRESET`. `TX_FIFO_BYP_EN` is required in bypass (p.140). |
| 10 | Transmit user clock taken from the recovered clock (one clock domain for the whole fabric, variant V1) | **Not supported as worded; a documented alternative exists (V1', corrected by 96F2)** | UG576 only describes `TXUSRCLK` from `TXOUTCLK` (p.135, 141, 159). XAPP1276 and AMD's low-latency blog (GTY, tested) keep `TXOUTCLK` (QPLL) as the one clock, pull the QPLL onto the recovered rate with a fabric DPLL, share it as `RXUSRCLK` and set `RXSYNC_SKIP_DA = 1`; UG576 p.151 documents the sharing for multi-lane GTH. Single-lane GTH: unconfirmed. `docs/loop_timing_sources.md` section 1. |
| 11 | Loop-timed TX (frequency tracking) holds within the GT's alignment range at +-100 ppm and drift | **Feasible in the model, unknown on hardware** | Model, section 7. The GT's delay-alignment range is +-4 ns full, +-2 ns half (UG576 p.138, 259); how it behaves under a slowly moving frequency difference is not in UG576. |
| 12 | An external jitter-cleaning PLL fed by the recovered clock (SyncE style) | **Not available on this board** | No cleaner PLL, and no path from a PL pin to `MGTREFCLK0`, appears in the board files or the knowledge bank; the Si5332 parts in the board file are 3.3 V LVCMOS system clocks into the PL (`board.xml` `hpa_clk0p_clk`, `hpb_clk0p_clk`). Unconfirmed against the schematic, which was not read. |
| 13 | Latency saving | **Predicted, not measured** | Section 6: 97C all3 161 ns to about 115 to 131 ns; against `rm_gp` about 53 to 75 ns less. The GT part is from a third-party article about a GTY transceiver: **unconfirmed for this GTH**. |

## 2. Line activity: is there always a recovered clock while the link is up?

The question (owner, via the planner): the loop needs a recovered clock whenever it runs.

- **Continuous signal.** The 10GBASE-R PCS sends 64B/66B blocks back to back; with no frame it sends idle blocks, so the line never stops
  while the transmitter is on. Each 66-bit block starts with a sync header that is 01 (data) or 10 (control) and is not scrambled, so there is
  always a transition at the header; the payload is scrambled, so the other positions carry a transition about half the time (secondary
  sources: Intel Arria 10 Transceiver PHY User Guide, "64B/66B Encoder and Transmitter State Machine"; IEEE 802.3 HSSG e-mail, msg00865,
  a discussion thread, not normative text). **The exact clause 49 wording (clause 49.2.4 and Figure 49-13, from memory) was not read: unconfirmed
  against the standard.** In our own design the PCS (`pcs_tx.sv`, `model/pcs.py`, 96) emits idle blocks whenever no frame is queued and the block
  lock FSM relies on the same sync headers (`docs/design.md` section 2.8); the 2026-11-19 board runs held block lock across 100 of 100 restarts.
- **Fault signalling.** When a receiver loses block lock its PCS reports local fault to the reconciliation sublayer (clause 46) which then
  sends remote-fault sequence ordered sets, so a partner that "receives nothing" still transmits a continuous signal. Same caveat: recalled from
  clause 46/49, **unconfirmed**. **Our PCS does not implement that state machine**: ordered sets are counted and shown as idles
  (`docs/design.md` section 2.6), so a partner's fault sequence is invisible as such to our decision logic. The tracker must therefore not use "no
  faults" as its health signal; it uses CDR lock (`rxcdrlock_out`, already an optional port in `ip/amd_ip.tcl`), block lock and its own phase
  detector.
- **EEE.** Energy-efficient Ethernet (IEEE 802.3az, clause 78) specifies low-power idle for 100BASE-TX, 1000BASE-T, 10GBASE-T, 1000BASE-KX,
  10GBASE-KX4 and 10GBASE-KR; a secondary overview says it "is not specified for optical PHYs" (IEEE 802.3az task-force documents and
  industry summaries; 10GBASE-SR/LR are not named in any source read). **So the likely answer is that EEE low-power idle does not apply to
  10GBASE-SR/LR, but this is unconfirmed against clause 78 itself.** A copper SFP+ module (10GBASE-T) is a different matter and is out of scope.
- **When it does not hold.** TX disabled at the partner (`rx_los`), a pulled fibre, a module in reset, or a partner that mutes its transmitter
  on fault: no recovered clock. The state machine of section 5 treats loss of CDR lock as loss of the reference.

## 3. Can the KR260 do it? (brief item 1)

**What drives the SFP+ reference clock: unconfirmed.**
- Confirmed: `MGTREFCLK0P/N_224` are pins Y6/Y5 (the Vivado package database, knowledge bank `device/xck26/primitives/xck26-gth-quad-224`);
  a 156.25 MHz reference worked: 100 of 100 restarts locked on 2026-11-17 and again on 2026-11-19 (`docs/design.md` section 1 and "Board result").
- Not in any document read: the oscillator or clock generator that drives it, and whether it is programmable. UG1092 has no clock table
  (knowledge bank `board/kr260/PROVENANCE.md`); the AMD carrier board file lists the Si5332 parts only as `hpa_clk0p_clk`/`hpb_clk0p_clk`,
  "3.3V LVCMOS Si5332 programmable oscillator used as clock on the board" (`kr260_carrier/1.1/board.xml`, `sub_type="system_clock"`): LVCMOS into
  the PL banks, which suggests the MGT reference is a different, differential source, but that is inference. Searches for the carrier
  schematic found nothing; a community board file (litex-boards PR 949) only repeats the pin names. **Action for the owner or a later
  brief: read the KR260 carrier schematic (public on the AMD Kria page, not fetched) and record the part and whether its I2C reaches the PS or PL.**
- Consequence for the design: **assume a fixed 156.25 MHz reference.** A programmable one is a bonus, not a premise.

**Why it matters.** The article the brief cites moves the reference to 155.075188 MHz so the QPLL sits mid-range between N = 66 and 67
(10312.5 / 66.5 = 155.0752 MHz, checked here; its tuning span is then about +-0.76 %). With 156.25 MHz the nominal 10.3125 GHz is exactly N = 66.0 for
every reference divider (M = 1 to 4 gives N = 66, 132, 198, 264), so the fraction can only move the line rate in one direction from the nominal
(`N = 66` with a positive fraction: faster; `N = 65` with a fraction just below 1: slower). The 200 ppm dynamic-update limit (UG576 p.58) applies to
the deviation from the VCO frequency at the last QPLL reset, so a window can be centred by resetting the QPLL at its centre value, but the
window cannot cross the integer boundary without changing N (a DRP write plus QPLL reset, hence a link outage).

**Routes round the one-sided window (modelled in section 7):**
1. Two windows (N = 66 and N = 65) chosen at acquisition from the measured partner offset. A partner within a few ppm of the nominal sits on the
   boundary and the loop chatters between windows (model: 16 to 51 window hops in 2 s at 0 and +-1 ppm; 1,098 hops over a 400 s drift across zero). **A hazard for any partner with a very accurate oscillator.**
2. TXPI bias: the TX phase interpolator gives a static, symmetric offset in steps of 61.04 ppm (`TXPI_PPM = 1`, `TXPI_SYNFREQ_PPM = 7`; UG576 v1.7.1 Table 3-33 formula,
   built and accepted on the board in 96C, `docs/design.md` section 9). Two overlapping windows, bias -61 and -122 ppm with the fraction always >= 0,
   cover -122 to +139 ppm with a 40 ppm hysteresis band and no QPLL reset; model: no chatter, same accuracy as a centred reference. **Unconfirmed, and 96F2 found it unlikely in the Wizard's bypass core:** that a
   TXPI code change coexists with TX buffer bypass and keeps `TXUSRCLK` aligned (UG576 p.160 describes `TX_PROGCLK_SEL = POSTPI` as the path that carries
   the PI's ppm offset into the parallel clock, which is the clock that must follow). The Wizard's bypass core powers the ppm block down (`txpippmpd_in` = 1) and takes the user clock before the PI (`TX_PROGCLK_SEL = PREPI`, `TXOUTCLKSEL` 101): see `docs/loop_timing_sources.md` section 4.
3. A programmable reference (unconfirmed present).
4. Using the TXPI alone as the actuator: not recommended (61 ppm steps; section 5).

**Other routes asked about.** CPLL from a fixed clock: not feasible (verdict 4). A PL-generated reference: not feasible (verdict 5). The TX phase interpolator in a feedback loop
"as 96C tried": 96C's result (0.0 ppm at every code) was measured in a fibre loopback, where the recovered clock is our own transmit clock, so it
**could not** show a relative offset whatever the actuator did; that is a consequence of the loopback, not proof that the PI does nothing (it is
the same caveat as section 8). The 96C report's wording "the transmit user clock follows the shifted serial clock" is supported by the counter
reading 0 ppm only together with that loopback; it is plausible (UG576 p.160) but not shown independently.

## 4. Buffer bypass: what the path uses today and what bypass needs (brief item 2)

**Today (97C and 96E, as built).** GT Wizard 1.7: QPLL0 at 10.3125 Gb/s from 156.25 MHz, RAW encoding, 64-bit user data on a 32-bit internal path,
user clock 161.1328125 MHz, TX and RX buffers **on**: `TXBUF_EN = TRUE`, `RXBUF_EN = TRUE`, `TX_XCLK_SEL = TXOUT`, `RX_XCLK_SEL = RXDES` (read back from the
built checkpoint, `results/b96c/txpi_probe.log`). Both user clocks come from the PMA (`TXOUTCLKSEL` 010, `RXOUTCLKSEL` 010). The PCS and gearbox are
in fabric. **Correction found while reading:** `docs/design.md` section 11 (table row "GT's own RX elastic buffer") says the 56A build "uses the
buffer bypass (`RXBUF_EN = 0`)"; the probe log and section 2.7 say the opposite (buffer on). The log is the record. (To be fixed in design.md by the planner or a later brief; not edited here to
keep this brief's diff to new files.) Brief 97's bypass probe failed (`results/b97/README.md`), so the Wizard properties `TX_BUFFER_MODE`/`RX_BUFFER_MODE` were never read. (Read by brief 96F1: `results/b96f1/wizard_probe/README.md`.)

**What bypass needs (UG576 v1.7.1).**

| | TX buffer bypass | RX buffer bypass |
|---|---|---|
| Attributes | `TXBUF_EN = FALSE`, `TX_XCLK_SEL = TXUSR`, `TX_FIFO_BYP_EN` (required, p.140), `TXOUTCLKSEL` 011/100/101 (p.141) | `RXBUF_EN = FALSE`, `RX_XCLK_SEL = RXUSR`, `RXOUTCLKSEL = 010` (p.260), `RXSYNC_OVRD = 0`, `RXSYNC_MULTILANE = 0` |
| Clock rule | `TXUSRCLK` must come from `TXOUTCLK` of the reference clock or the PLL's programmable divider; `TXPLLREFCLK` "required for the TX buffer bypass mode" (p.159) | `RXUSRCLK` from `RXOUTCLK` = the recovered clock; no local-clock option (Table 4-32, p.270) |
| Alignment | after any TX reset, PLL reset or reference or rate change: `TXDLYSRESET`, wait `TXDLYSRESETDONE` (>= 100 ns), then the second rising edge of `TXPHALIGNDONE` (p.141 to 142); then the delay alignment keeps adjusting for temperature and voltage within +-4 ns | the same after receiver or PLL reset, recovered clock change or rate change (p.260); CDR must be locked before alignment (p.269); repeat if the data is invalid after a reset |
| Cost | extra logic and constraints on clock sources; sensitive to `TXUSRCLK` jitter (Table 3-17, p.135) | no clock correction or channel bonding in the GT (p.256); sensitive to `RXUSRCLK` jitter (Table 4-32, p.271) |
| Mode | single-lane auto or manual (Table 3-22) | single-lane auto only (Table 4-31, p.260) |
| Status | `TXPHALIGNDONE`, `TXDLYSRESETDONE` | `RXPHALIGNDONE`, `RXDLYSRESETDONE` (Table 4-29) |

**Frequency requirement.** In both directions the PMA parallel clock (XCLK) and the user clock must have the same frequency, because the phase-alignment circuit
only adjusts phase (p.137, 255). For RX that is automatic (`RXUSRCLK` is the recovered clock). For TX it is automatic too if `TXUSRCLK` comes from the same
PLL that makes the serial clock (`TXOUTCLKSEL = 101`, `TX_PROGCLK_SEL` PREPI or POSTPI, p.160). That is why **bypass does not need loop timing**: bypass alone (variant B1 below) keeps
the rate matcher and still removes the GT buffers. Loop timing is a separate, second step that removes the fabric rate matcher or go-pulse crossing.

**Latency removed, per stage.** UG576 gives no numbers; it points to AMD answer records "UltraScale+ GTH Transceiver: TX and RX Latency Values" (AR 68177, p.18 and
reference 5), **not retrieved** (the support page returned an error). A third-party article on a GTY 10G Ethernet core quotes AMD AR 69011: default TX 7.7 to 10.9 ns and RX 13.2 to 17.1 ns, "latency saving about 18 to 25 ns" by phase-aligned bypass
(ttchisholm.github.io, "Designing 10G Ethernet" part 3); the article the brief names reports 27.83 ns round trip RX to TX at 32 bits with both bypasses (third-party summary, eda365). These are **GTY figures,
not confirmed for the K26's GTH**, and at a different user width. Our 64-bit user path at 161 MHz gives the fabric side one clock of 6.2 ns where the article's 32-bit path has 3.1 ns.

| Stage | Today | Bypass | Per-stage removal (unconfirmed, GTY) |
|---|---|---|---|
| TX phase-adjust FIFO | on | off, phase alignment | 7.7 to 10.9 ns (1.2 to 1.8 clocks) |
| RX elastic buffer | on | off, phase alignment | 13.2 to 17.1 ns (2.1 to 2.8 clocks) |
| TX gearbox / RX gearbox | in fabric (RAW) | unchanged | 0 |
| Fabric RX to TX crossing | 97C go-pulse crossing 4 clocks (3 in all3); 96E `rm_gp` +2.3 over 97C | removed (V1) or one clock (V2) | section 6 |

## 5. Design proposal: a loop-timed variant of the b96 path (brief item 3)

### 5.1 Clock trees (two variants)

- **B1, bypass only.** Both buffers bypassed as above; `TXUSRCLK` from the QPLL's programmable divider (`TXOUTCLKSEL = 101`), `RXUSRCLK` recovered. Two asynchronous domains remain, `rm_gp` (96E) stays. No steering. Saves the GT part only.
- **V2, two matched clocks.** B1 plus a controller that tunes the QPLL so the TX clock equals the recovered frequency. The domains are then equal in frequency with a slowly moving phase. The fabric crossing is one register stage with phase-aware capture (rising or falling edge chosen by a phase
  detector, so the crossing costs 1 to 1.5 clocks) and no rate matching. **Costs a CDC decision:** a crossing between two unrelated clock nets is a CDC-1 row in the flow's gate; the owner's decisions of 2026-11-19 are "no waiver" for the 96E direct read (item 3) and "no standing approval; owner decides each case" (item 9).
  The proof here would be dynamic (phase-bounded), not structural.
- **V1, one clock for the whole fabric.** *(Corrected by 96F2, `docs/loop_timing_sources.md` section 1: the one net is the transmit `TXOUTCLK` from the QPLL, not the recovered clock; the recovered clock only feeds the phase detector; `RXUSRCLK` = `TXUSRCLK`, RX bypass with `RXSYNC_SKIP_DA = 1`; AMD built this on a GTY. The text below is the original, kept for the record.)* `TXUSRCLK2` and `RXUSRCLK2` are the same net, the recovered clock; the QPLL is tuned so its TX parallel clock matches it, and the TX phase alignment absorbs the residual phase. **No fabric crossing and no CDC row.** Status: **unknown** (verdict 10), and the TX GT then needs the lock before its alignment is meaningful, so it is a
  fragile start-up. Recommended order: B1, then V2 behind the loop, then V1 only if XAPP1276 shows it is supported.

### 5.2 The controller: an FLL-assisted PLL (owner's request)

1. **Frequency acquisition (FLL), using the existing 96C frequency counter.** RXV27/RXV28 count the receive clock's cycles in a window of 2^24 core clocks (104.1 ms,
   0.1 ppm resolution; `docs/register_map.md`). One window after block lock gives the offset p. The model's acquisition takes the counter's quantised mean (+-0.1 ppm). Used alone, the counter is too slow to be the loop: a 50 ppm offset
   from the start gives a 5,207 ns phase excursion, a 1 ppm step 104 ns, a 0.1 ppm/s ramp 37 ns (`results/b96f/loop_timing_model.json`, section E). It is an acquisition detector only.
2. **Set the actuator** to the measured offset (window chosen by its sign if the reference is fixed), then align the TX bypass (auto sequence, p.141 to 142), then record the phase.
3. **Phase tracking (PLL).** A phase detector counts whole-clock slips and sub-clock position of the transmit domain against the recovered clock; a proportional-plus-integral filter (natural frequency 30 to 100 Hz, damping 1) writes `SDMDATA` at 10 kHz (ASSUMED; the SDM handshake itself needs about 1 us, UG576 Table 2-16).
   The phase set point is the phase at closure, so a loopback of unrelated phase does not integrate a constant error (but see section 8).
4. **Detector resolution matters.** With one core clock (6.2 ns) of resolution the phase can only be held to about +-3 ns of the set point (rms 1.6 ns static in the model), which does not fit the +-2 ns half range; with a quarter-clock detector (sampling four clock phases of one MMCM; an ASSUMED feasible addition) it holds 0.05 to 0.16 ns rms.
5. **Guards.** The integral is clamped to a window around the acquired frequency (holdover guard, section 8); a counter flags every clamp.

### 5.3 Actuators compared

| Actuator | Resolution and range | Status | Verdict |
|---|---|---|---|
| QPLL fractional-N, dynamic (FRACXO route) | 0.0009 ppm; one-sided at 156.25 MHz, at most 200 ppm per reset window (UG576 p.51, 57 to 58) | Documented; Wizard exposure unknown | **Preferred** (with the two-window or TXPI-biased scheme) |
| TX PI ppm controller (`TXPIPPM`) | 61.04 ppm per step, symmetric (96C measured the codes accepted); finer values need dithering between codes: a +-30 ppm square dither at 10 kHz would add about 1.5 ns p-p wander, at 1 kHz 15 ns (arithmetic here; the PI's own update rate is not given in UG576: **unconfirmed**) | Documented as a "VCXO replacement" feature (UG576 Table 1-1, p.16) | **Bias only**, not the fine actuator |
| CPLL | n/a | not feasible (verdict 4) | no |
| External jitter-cleaning PLL fed by the recovered clock (the SyncE approach, ITU-T G.8262 EEC) | whatever the part gives | **No path on the KR260**: the recovered clock can leave the PL on an ordinary pin, but nothing documented brings a clean clock back to `MGTREFCLK0` (Y6/Y5); the Si5332 outputs go into the PL. Needs a different board, or a modified carrier | not available |

**SyncE numbers where they can be cited** (secondary sources; G.8262 itself not read): an EEC Option 1 clock has a free-running accuracy of +-4.6 ppm, a minimum pull-in range of +-4.6 ppm and a wander-transfer low-pass bandwidth of 1 to 10 Hz (Option 2: 0.1 Hz at most), per the
2010 edition (Scribd copy) and Calnex's one-page summary; the 2018 and 2024 editions were not checked. Two consequences: (a) a SyncE clock assumes its source is itself traceable (about +-0.01 ppm), whereas a plain NIC's oscillator is only held to +-100 ppm, so the pull-in
range our loop needs (+-100 ppm) is much wider than an EEC's; (b) the 1 to 10 Hz bandwidth is a wander filter, set for jitter and wander accumulation along a chain of clocks, which is not our problem (one hop): the model shows 1 to 10 Hz is too slow for us if a step happens (below).
**Timing loop:** if both ends of a link loop-time from each other the pair has no reference and wanders; only one end of any link may follow.

### 5.4 What replaces the rate matcher

- B1: nothing changes (`rm_gp`).
- V2 or V1 locked: the buffer is bypassed in the data path (idle insert and delete are not needed because the frequencies are equal), but **the buffer is not removed from the design**: it stays as the pre-lock and holdover path, because loss of lock must have somewhere safe to go (section 6.1). The register map keeps its counters.

### 5.5 Failure modes and how the safety counters see them

| Failure | What happens | Counter or flag (proposed names; none exists yet) |
|---|---|---|
| Partner TX off, fibre pulled, CDR lost | no reference | `rxcdrlock` low, block lock low (existing RXV counters); state to HOLDOVER |
| Partner offset leaves the window | u clamps; phase walks | `lt_sat_ticks`, `lt_window_hops`; state to HOLDOVER after N ticks |
| Phase walks beyond +-2 ns of the set point | crossing or GT alignment margin gone | `lt_phase_over` (peak |phase| since clear) |
| Partner steps in frequency (a clock switch in the partner) | transient (model: 30 ppm step, 20 ns peak at 100 Hz) | `lt_phase_over`; state to HOLDOVER, then re-acquire |
| Bypass alignment fails or loses done | data invalid | `lt_tx_align_fail`, `lt_rx_align_fail`; re-run alignment; existing `bad`, `err`, `order_bad` counters stay 0 or the run fails (`SAFETY_TX`, `SAFETY_RX`) |
| Loopback or timing loop | the error is unobservable | `lt_guard_hits` (clamp to the holdover guard, section 8) |
| Link restart (RX reset) | acquisition again | `lt_restarts`; the existing restart counters |

The existing `safety_verdict` (`host/b96_bench.py`) treats any non-zero `poisoned`, `dropped`, `underrun`, `late`, `stale`, `bad`, `err`, `toolong`, `order_bad` as a failure; the loop adds its own set, judged the same way.

## 6. Start-up, lock and failure sequence (owner's addendum 3)

States, each with its exit condition and its counters. The GT's TX bypass state is static (set at build time); what switches is the fabric crossing.

1. **FREE_RUN.** Link up, QPLL at nominal (u = 0), `rm_gp` crossing in use (96E, 2.3 clocks over 97C), trading path as today. The CDR tolerates the offset (the recovered clock is whatever the partner sends). No traffic is needed from the partner: its idle blocks are continuous (section 2). Counters: restarts, block lock.
2. **BLOCK_LOCK.** PCS block lock held for a minimum time and `rxcdrlock` high (RX alignment done if RX bypass). Counter: `lt_lock_time`.
3. **FREQ_ACQ.** One counter window (104 ms) measures p; the actuator is set; the TX bypass alignment is run if it has not been; wait `TXPHALIGNDONE`. Fail: `lt_tx_align_fail`.
4. **PHASE_LOCK.** PI loop closes; set point recorded. Locked flag when |phase| < 1 ns and the clamp has not been hit for 1 s. Fail: timeout, `lt_sat_ticks`.
5. **LOCKED.** The fabric crossing switches to the direct path **at an idle gap** (as the rate matcher inserts and deletes: a block of idles is added or dropped, never data, ordered sets or terminate blocks), so no frame is cut. Counter: `lt_switches`. The trading path is held (no order is sent) across the switch, then re-armed; `late`, `stale` and `order_bad` must stay 0.
6. **HOLDOVER** (on loss of lock, reference or guard): hold the last SDM word (a frequency within the partner's wander for seconds to minutes: the model's drift of 0.01 to 1 ppm/s gives 0.6 to 60 ppm per minute, so the hold time that keeps phase within the margin is of the order of a second to tens of seconds at the worst partner drift; real oscillator drift is slower and unmeasured), switch the crossing back to `rm_gp` at an idle gap, count `lt_holdovers`, then go to FREQ_ACQ when the reference returns. The hold value is the last locked u, not the guard edge.

**What "run the 96E path before lock, switch only once locked" means for the GT:** B1's GT bypass is independent of the loop (V2 clocks both TX sides from one PLL), so the GT stays bypassed in states 1 to 6 and only the fabric crossing moves. In V1 the GT TX alignment depends on the loop and the sequence is stricter.

## 7. Tracking-loop model (brief item 4)

`model/loop_timing.py`; records `results/b96f/loop_timing_model.json`; tests `tests/test_b96f_loop_timing.py` (8, run in under 2 s). Inputs: SDM step, 200 ppm rule, alignment ranges and the TXPI step are from UG576 and 96C; **the update rate (10 kHz), loop delay (2 ticks), measurement jitter (0.3 ns rms) and the QPLL-reset outage (20 ms) are assumptions** (the JSON repeats them). The partner is a function of time; the detector is a whole-clock (or quarter-clock) cycle counter.
Not modelled: the GT alignment circuit's own behaviour, QPLL bandwidth and jitter, CDR dynamics.

Headline results (all from the JSON):

- **Static offsets -100 to +100 ppm, 2 s, FLL then PI at 100 Hz:** the acquisition error is at most 0.1 ppm (counter resolution), the final u equals the partner to 0.001 ppm for |p| of 50 or more, and the phase stays within +-1.4 ns of its set point for the one-clock detector at |p| >= 50 and +-3.0 ns at 0 and +-1 ppm (quantisation limit).
- **Fixed 156.25 MHz reference, two one-sided windows:** correct away from zero, but at 0 and +-1 ppm the loop chatters: 6 to 22 window hops in 2 s (each is a QPLL reset and outage); over a slow drift across zero, 155 to 1,098 hops. **TXPI-biased overlapping windows or a centred reference: 0 hops and the same accuracy as the centred case.**
- **Drift across zero (-2 ppm, +0.01, +0.1, +1 ppm/s):** phase within 3.2 to 3.4 ns (the quantisation floor) for the centred and TXPI-biased cases at all three rates.
- **Step in the partner's frequency (30 ppm; a real oscillator does not do this, a partner clock switch might):** peak phase 177 ns at 10 Hz, 60 ns at 30 Hz, 20 ns at 100 Hz, 11.5 ns at 300 Hz. None keeps it inside +-4 ns, and 300 Hz makes the actuator noisy (u noise 15.7 ppm rms). **So a step is handled as loss of lock, not tracked.**
- **Bandwidth trade-off** (static 20 ppm, 0.1 ppm/s drift, 5 ppm step; one-clock and quarter-clock detector), closed-loop -3 dB point (zeta 1): 3 Hz loop passes 7.4 Hz; 10 Hz passes 24.8 Hz; 30 Hz passes 74.5 Hz; 100 Hz passes 248 Hz; 300 Hz passes 745 Hz:

  | Loop natural frequency | Jitter above this passes? (-3 dB) | 5 ppm step peak phase | Actuator noise, quarter-clock detector |
  |---|---|---|---|
  | 3 Hz (EEC-like) | above 7.4 Hz attenuated | 98 ns | 0.006 ppm rms |
  | 10 Hz | above 24.8 Hz | 29 ns | 0.02 ppm rms |
  | 30 Hz | above 74.5 Hz | 10 ns | 0.06 ppm rms |
  | 100 Hz | above 248 Hz | 3.5 ns | 0.29 ppm rms |
  | 300 Hz | above 745 Hz | 2.1 ns | 2.1 ppm rms |

  **A 30 to 100 Hz loop is the compromise:** it keeps a 5 ppm step near +-4 ns, passes only the partner's wander and low-frequency jitter, and does not turn the detector's quantisation into actuator noise. A SyncE-style 1 to 10 Hz bandwidth cannot hold the phase through a 5 ppm step; it can hold a +-4.6 ppm static offset easily.
- **The existing frequency counter as the whole controller:** useless as a loop (peak phase 37 ns on a 0.1 ppm/s ramp, 104 ns on a 1 ppm step, 5.2 us on a 50 ppm start); right as the acquisition detector.

## 8. Loopback caveat (owner's addendum 4)

In a fibre loopback the recovered clock **is** our transmit clock (delayed by the loop). Steering TX to it closes a loop with no reference: the frequency difference is zero whatever u is, so the loop cannot see an error and cannot correct one.

- Model (section D of the JSON): a 6 ns phase kick (a realignment or bit slip, which has no frequency cause the loop can remove) at 1 s makes the integral run to the window edge (u at +200 ppm, saturated 80 % of the time) with no guard, and with a deadband plus leak (the leak toward the acquired value is too weak). A **holdover guard** (u clamped within 5 ppm of the acquired value) holds u at +5.0 ppm and raises a flag (41,041 guard-hit ticks): the frequency still moved by the guard, so the guard must be small and the flag must be a test failure, not silent.
- **What a loopback can test:** the start-up sequence and every counter in sections 5 and 6; RX and TX bypass alignment (`TXPHALIGNDONE`, `RXPHALIGNDONE`, repeated restarts); **buffer-bypass latency at a fixed frequency** (E, L, D against 97C and 96E, at u = 0); that the controller holds still when there is nothing to track; that the guard catches an injected phase kick; repeatability across 100 restarts.
- **What it cannot test:** frequency tracking, the loop bandwidth, the window logic, holdover, or the partner's offsets. Those need an independent clock: the owner's coming 10G NIC (96E real-offset plan, option B; owner decision 4, 2026-11-19), or a second board with a different oscillator, or a programmable reference. The board test plan (`docs/loop_timing_board_test_plan.md`) is ordered accordingly.

## 9. Open items, for the planner

1. ~~Read XAPP1276~~ Done by 96F2 (Japanese v1.2; `docs/loop_timing_sources.md`): V1 redefined, controller and loop parameters recorded; still open: whether a dynamic SDM update keeps TX bypass aligned (XAPP1276 never mentions bypass).
2. Read the KR260 carrier schematic for the `MGTREFCLK0` source and its programmability (owner or a later brief).
3. ~~A Wizard property probe~~ Done by brief 96F1 (`results/b96f1/wizard_probe/`).
4. Retrieve AR 68177 (GTH latency values) to replace the GTY figures. **96F2 could not either** (AMD's support site is unreachable from here); needs a logged-in browser or a board measurement.
5. Owner decision needed before any V2 RTL: the direct crossing is a CDC-1 case (decisions 3 and 9 of 2026-11-19).
6. A sub-clock phase detector (quarter-clock sampling) is needed in V2 and is not in the design.
7. Fix `docs/design.md` section 11's statement that 56A's Wizard build uses the RX buffer bypass (it does not).

## Reproduce

`python3 designs/b96_kr260_10g/model/loop_timing.py results/b96f/loop_timing_model.json` (about 40 s), `python3 results/b96f/latency_prediction.py results/b96f/latency_prediction.json`, `python3 -m pytest designs/b96_kr260_10g/tests/test_b96f_loop_timing.py`.
