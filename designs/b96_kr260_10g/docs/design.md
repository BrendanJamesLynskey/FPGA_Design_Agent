# b96_kr260_10g: design note (written before the RTL; brief 96, 2026-11-16)

Goal: a real 10GBASE-R link from the KR260's SFP+ cage (GTH quad 224) with **our own** PCS and MAC, so a PC network card
or a fibre loopback can carry the mock trading path of brief 58A at 10 Gb/s, with the latency of every register on the
path stated. Nothing here is copied from any other implementation or from the standard's text; the standard is cited by
clause and figure, and the figure numbers below are from memory of IEEE 802.3 clause 49 (the standard is not on this
machine), so the review checks them.

## 1. Stage 0: what the board gives us (no hardware)

| Fact | Value | Evidence | Status |
|---|---|---|---|
| Lane | one GTH lane, `GTHE4_CHANNEL_X0Y6`, quad 224 channel 2, RX T2/T1, TX R4/R3 | Vivado package database (56A, `results/56a_serdes/gt_sites.txt`) | confirmed |
| Speed | K26 is -2LV: GTH at most 12.5 Gb/s; 10.3125 Gb/s is inside QPLL0 divider 1 (9.8 to 12.5) | DS925 v1.30 table 99 | confirmed |
| Cage | SFP+ connector J23, cage J24, 3.3 V, 600 mA | UG1092 r1.1 (as read in the knowledge bank) | confirmed |
| Reference clock pins | MGTREFCLK0 of quad 224 = Y6/Y5 | Vivado package database | confirmed |
| Reference clock frequency and source | 156.25 MHz, source not known | Taxi `sfp.xdc` (`create_clock -period 6.400`); a community Aurora tutorial uses a 156.25 MHz differential reference on this board (search snippet only) | **unconfirmed**: UG1092 has no clock or pin table; the schematic could not be fetched offline |
| Control pins | TX_DISABLE Y10, MOD_ABS W10, RX_LOS J12, TX_FAULT A10 (LVCMOS33) | pin-to-SOM mapping from AMD board files; functions from Taxi | **unconfirmed** functions and polarity |
| I2C | SCL AB11, SDA AC11 | AMD board file `sfp_iic` | confirmed |

What stays open, and what we do about it:

- The reference may not be 156.25 MHz. With the QPLL0 **integer** dividers (M 1 to 4, N 16 to 160, UG576 ch. 2) only the
  references 156.25 (N 66), 312.5 (N 33), 161.1328125 (N 64) and 322.265625 MHz (N 32), and their multiples of N and M, give
  exactly 10.3125 GHz; 100, 125, 150, 200 and 250 MHz do not (enumeration in `scripts/refclk_options.py`). The UltraScale+ QPLL
  also has a fractional-N divider (UG576, the SDM fields), which could make N = 82.5 from 125 MHz or N = 103.125 from 100 MHz
  exactly, at the price of more PLL jitter and a Wizard configuration 56A did not build or test. So if the board's reference
  is not in the 156.25 family, the next step is a fractional-N Wizard build, not a guess; the board plan tests the
  reference first (PLL lock and `tx_done` at the 156.25 MHz settings) and stops with a report if it fails.
- Nothing is driven that the open pins could damage: `tx_disable` resets to 1 (laser off) exactly as in 56A.

## 2. Decisions and the alternatives

### 2.1 Own PCS, not the AMD 10G Ethernet PCS/PMA

`xxv_ethernet` is refused at synthesis on the Basic licence (56A, `results/56a_serdes/licences.md`); `ten_gig_eth_*`
does not exist for this part. We use the GT Wizard (builds on Basic) in RAW mode and write the PCS in fabric. Cost:
our own verification; benefit: every register on the path is ours and named, and the latency can be low and counted.

### 2.2 Gearbox in fabric, GT in RAW

The GTH has a hardware 64B/66B gearbox, but only in the Wizard's 64B66B encoding mode (UG576 ch. 3), which 56A did not
build and which pulls the scrambler choice and the sequence counter behind IP we cannot see. 56A proved RAW 64-bit
(user clock 161.1328125 MHz) builds on Basic and runs the lane, so the 66-to-64 gearbox, the scrambler, block lock and
bit slip are all ours. The price is the fabric barrel shifter on receive (section 4) and one clock of pause in 33 on
the data path.

### 2.3 One clock per direction, no 156.25 MHz MAC and no FIFO

A 64-bit RAW word carries 64 of the 66 bits of a block, so the user clock is 10.3125 Gb/s / 64 = **161.1328125 MHz**
(TXUSRCLK2, RXUSRCLK2), not 156.25 MHz. 156.25 MHz is the XGMII clock of the standard: 64 data bits per clock at
10 Gb/s. We run the MAC at the user clock and let the PCS take one pause in 33 clocks (the gearbox needs 33 words for 32
blocks): `adv` low for one clock. The MAC state machines advance only when `adv` is high; on receive a `valid` strobe
accompanies each decoded block. Average payload rate 161.1328125 x 64 x 32/33 = 10.0 Gb/s exactly.

Alternative: a 156.25 MHz MAC behind an asynchronous FIFO. It costs several clocks per direction, plus a variable depth,
and the FIFO adds nothing the pause does not. Rejected for latency. The 156.25 MHz period (6.4 ns) and 161.13 MHz period
(6.206 ns) differ by 3%, so every latency below is given in clocks and in ns at 6.206 ns.

If timing at 161.13 MHz had failed, a 32-bit RAW path at 322.27 MHz (brief's fallback) would be the next step; it did not
need to be taken (see the report for the slack).

### 2.4 The MAC is new, 64 bits wide

The 58A MAC (`ip_lib/eth_mac_rgmii`) is byte-wide with RGMII pins and a 1 Gb/s clock crossing; widening it would change
everything but the CRC polynomial. A new 64-bit MAC with an XGMII-style 64+8-bit interface is smaller than the
adaptation and is what the PCS needs. TX: preamble in the first word, CRC in the last, IFG enforced, no padding (sources
supply at least 60 bytes; asserted). RX: cut-through words, start in lane 0 or lane 4, terminate in any lane, the FCS
verdict at the end by the CRC residue.

### 2.5 The trading path in variant (b): `trade64`, not a widened `trigger_core`

`trigger_core` is a byte-wide, one-clock-per-byte design (8 ns per byte at 125 MHz), with a book, 8 rules, interlocks,
sequence-gap logic and ARP. At 10 Gb/s a frame arrives 8 bytes per clock, so the core cannot sit behind the 64-bit
MAC without a down-converter that would add the serialisation time we are trying to measure. Widening the whole core is
its own project. **Variant (b) therefore carries a new, small 64-bit path `trade64` that speaks the same wire format
(Bench Feed v1, `designs/b58a_trigger/docs/bench_feed_v1.md`) and takes the same decision on the first message of a
frame** (ask at or below a threshold: a buy order), with these parts of 58A *not* carried over: the order book and
top-of-book tracking, the 8-rule table and shadow commit, sequence-gap detection and halt-on-gap, the price band,
position and token-bucket interlocks, the ML arm, the cancel-after-send path, and the IPv4 header checksum check. It
keeps: cut-through decision at the price field, a pre-built order frame (66 bytes plus FCS), speculative send with the
order's FCS poisoned if the incoming frame turns out bad, a kill bit and an arm bit, and the order counter. The brief's "58A
mock trading path (ML_ARM=0)" is thus met in function and format, not in code; the decisions are checked against
`designs/b58a_trigger/model/benchfeed.py` frames. A 64-bit port of the full core is a follow-up for the planner.

### 2.6 Where the decision lives and how it crosses clocks (as built for brief 96; superseded by section 9, brief 96C)

The receive side is in RXUSRCLK2 (the recovered clock; independent of TXUSRCLK2 to within the partner's parts per
million), the order leaves in TXUSRCLK2. Streaming frames across would need an elastic FIFO with its variable delay.
Instead the decision is made in the RX domain and only a small **go message** (instrument, price, order id, "poison" level)
crosses, by `xpm_cdc_handshake` (3 to 4 destination clocks); the TX domain owns the pre-built order frame and starts
sending when the go arrives. The poison level for a bad incoming frame crosses by `xpm_cdc_single`; the order frame is 9
words long, so the verdict arrives before the order's last word (a timing assumption, counted by `late`; for a feed of the longest length the rule acts on, 78 bytes, the verdict is about 6 to 8 clocks after the decision, not 1 to 2, and since 96C, with no crossing delay on either, the margin to the order's last word is about a clock smaller than before: `late` counts a miss and the order is poisoned, fail closed) Configuration crosses by `xpm_cdc_handshake` per domain.

### 2.7 RX elastic buffer in the GT

56A's Wizard configuration left the buffer mode at the Wizard default (read back from the generated `.xci` in the report).
With the buffer on, the GT absorbs only the phase difference between its PMA clock and RXUSRCLK; RXUSRCLK2 is still the
recovered clock, so the RX and TX fabric domains stay asynchronous, as built. Bypassing it (`RX_BUFFER_MODE 0`) removes
buffer-depth variation at link-up but adds the Wizard's alignment procedure and a second configuration. **Decision: first
build with the buffer on (the 56A-proven configuration); the fixed-latency variant is a stage-3 experiment, measured
only if the first link-up distribution (section 6) shows the buffer matters.** Latency numbers for the GT's own
serialiser, CDR and buffer are not in our simulation; they are what the loopback measurement of stage 3 yields.

### 2.8 Block lock, bit slip, errors

Block lock follows the clause 49 receive state diagram (Figure 49-14, from memory): hunt for 64 consecutive valid sync
headers (01 or 10) with no invalid one; in lock, 16 invalid headers in a 64-header window lose lock; on a failure
while hunting, **slip** one bit. Our slip is registered: the barrel shifter drops one bit one clock after the decision,
and the FSM ignores the next 2 blocks (the pipeline's old alignment). Lock time is 64 blocks at the right alignment plus the wrong ones tried first (a wrong
alignment shows an invalid header within a few blocks on random scrambled data): 67 to 275 clocks (0.4 to 1.7 us) over all 66 bit offsets with idle
traffic (`results/b96/lock_time_model.json`, from the bit-exact model). A header sequence built to look valid at every alignment could take longer; the standard's
state machine has the same property.

Decoding: an invalid sync header (00 or 11) or an unknown block type becomes an all-/E/ block and a counter; an ordered
set is counted and presented as idles (the reconciliation sublayer's link-fault state machine is **not** implemented:
known gap); block type 0x66 (ordered set then start in lane 4) is treated as an ordered set.

## 3. Datapath and registers (every register on the path)

TX (TXUSRCLK2 domain; `adv` = 1 except one clock in 33):

| Stage | Register | What it does |
|---|---|---|
| MAC `mac64_tx` | `o_d`, `o_c` (XGMII word and control) | preamble word, data, FCS in the last word, T, idles |
| PCS `pcs_tx` | `gt_d` (64 b), `acc`, `n`, scrambler history | encode, scramble, merge the block at bit offset `n`, emit 64 bits (one stage) |
| GT | `TXDATA` | the wizard's own FPGA-interface registers and the GT's internal path are the GT's |

Encode, scramble and gearbox are one stage (one register, `gt_d`, plus the remainder `acc`): **2 registers from the MAC's output register to the GT**: the
MAC's `x_d` and the PCS's `gt_d`. A block is 66 bits and a word 64, so a block always spills into the next word: the first bit of the start block is on
TXDATA one clock after the MAC's output register, its last bit two clocks after.

RX (RXUSRCLK2 domain):

| Stage | Register | What it does |
|---|---|---|
| GT | `RXDATA` | the GT's |
| `pcs_rx` A | `acc` (192 b), `cnt`, `blk` (66 b) | merge, slip, extract one block |
| `block_lock` | FSM state, `sh_cnt`, `inv_cnt`, `lock` | headers only, per block |
| `pcs_rx` B | `x_d`, `x_c`, `x_v` | descramble (state: last 58 bits), decode |
| MAC `mac64_rx` | `r_d`, running CRC, `eof` | cut-through word out, residue check |

## 4. Interfaces

XGMII-style: `d[63:0]`, `c[7:0]`, lane i = bits 8i+7:8i; control characters 0x07 idle, 0xFB start, 0xFD terminate, 0xFE error.
Block formats used (payload bit numbers; type byte in [7:0], header 01 = data, 10 = control):

| Type | Content |
|---|---|
| 0x1E | 8 x 7-bit control codes (idle = 0x00, error = 0x1E) at [14:8] ... [63:57] |
| 0x78 | start in lane 0, data D1..D7 at [63:8] |
| 0x33 | control C0..C3 at [14:8] .. [35:29], 4 spare bits, start in lane 4, D5..D7 at [63:40] |
| 0x87 0x99 0xAA 0xB4 0xCC 0xD2 0xE1 0xFF | terminate in lane 0..7: data bytes below, 7-k reserved zero bits, 7-k control codes |
| 0x2D 0x4B 0x55 0x66 | ordered sets: counted, shown as idles |

Scrambler: self-synchronising, polynomial x^58 + x^39 + 1, over the 64 payload bits, sync headers not scrambled, bit 0 first.

## 5. Latency definitions (what the report measures)

- **TX latency**: clocks from the clock edge on which the MAC's first (preamble) word is in its output register to the
  edge on which the 64-bit GT word that contains the **last bit of the start block** is on `TXDATA`. The block can start
  in any of 32 bit offsets (the gearbox phase), so the report gives the minimum and maximum over all phases, not one number.
- **RX latency**: clocks from the edge on which the GT word that contains the **last bit of the start block** is on
  `RXDATA` to the edge on which the MAC's output register holds the first word of the frame (the preamble word is not
  forwarded; the first word is the destination address word).
- The lock time and the GT's own latency are excluded and reported separately.
- In ns: clocks x 6.2058 ns (161.1328125 MHz).
- How these map onto STAC-T0 and "wire-to-wire" figures (brief 109): [../../../docs/latency_definitions.md](../../../docs/latency_definitions.md).

## 6. Loop measurement method (pre-registered; stage 3)

With one port the loop crosses the link twice for the trading loop.

- **Echo**: TX start of a probe frame (UDP port 5802) to RX start of the same frame: E = T_tx + fibre + T_rx.
- **Trading loop**: TX start of a feed frame to RX start of the order (port 5801): L = E1 + D + E2 where D is the time
  from RX-start of the feed to TX-start of the order. So **D = L - 2E, not L - E** (the brief's "trading loop minus one echo"
  counts one pass of the link; the loop has two). Stated here before any data; if the owner's meaning differs it is
  recomputed from the recorded L and E.
- **Counter**: one free-running 32-bit counter in TXUSRCLK2. (Brief 96C: the RX start is stamped in the same clock by the MAC's start strobe behind the elastic buffer, no crossing; it includes the
  buffer's latency, 5 to 6 clocks in simulation, varying by a clock. Before 96C the RX start crossed by `xpm_cdc_pulse`, known to one clock plus the fixed synchroniser delay.) Uncertainty stated as +/- 1 clock (6.2 ns).
- **Link restarts**: at least 100 restarts (RX datapath reset), min, max and distribution of E and L per restart.
- **Subtract**: the measured fibre length x 4.9 ns/m (group index about 1.468 for G.652/G.657 fibre; the lead is 'about
  1 m'; measure it) and the optics' own delay, **unknown** unless the module's datasheet gives it.
- A PCS talking to itself accepts its own symmetric mistakes; only an independent NIC proves interoperability.

## 7. Verification plan

1. `model/pcs.py`: independent Python reference (serial scrambler, block encode/decode, block-lock FSM, a bit-level
   gearbox), bit-exact against the RTL on random frames, idles, ordered sets and bit-error runs. The RTL scrambler is
   64 bits in parallel; the model is bit-serial, so the two do not share a structure.
2. Clause 49 test patterns: the standard's own scrambler test vector is not available here and is not reproduced from
   memory. In its place: m-sequence checks of the LFSR (period of the 58-bit generator, scrambler of zeros equals the
   recurrence, descrambler(scrambler(x)) = x, self-synchronisation within 58 bits from any seed) and the hand-derived block
   formats of section 4. Stated in the report as a gap.
3. cocotb + Icarus: PCS loopback with a bit-serial channel model (arbitrary bit offset, bit slips, bit errors); lock
   time; lock loss; MAC TX against a Python frame encoder; MAC RX with S0 and S4 starts, every terminate lane, bad FCS;
   `trade64` against the 58A frame builder; latency measured.
4. Verilator -Wall (5.020 local, CI 5.048) on everything that does not contain the GT.
5. xsim: the real GTHE4 secureip model is refused by the Basic simulator (54,716 instances against 50,000: 56A). So the
   serial loopback uses a behavioural GT stand-in in xsim and Icarus; the GT itself is tested on the board.
6. Vivado builds (a) near-end PMA loopback self-test, (b) SFP+ live with `trade64`; flow and GT gates.

## 9. Rate matching and the receive-to-core crossing (brief 96C)

**Build option, default off (owner decision, 2026-11-19).** The elastic buffer below is a *build option*: the top-level parameter `RATE_MATCH` (`kr260_10g_top`, `b96_core`; generic in `build.yaml`) selects it.
`RATE_MATCH = 0` (the **default**, the base design and `lat_all3`) is the receive path of main 6909e43f exactly (brief 97C, board-proven: loop latency L 50 clocks for the base, 46 for all3):
`rtl/rx_path_legacy.sv` (that file, renamed), the go and event pulses and the order bus crossing from the receive clock to the transmit clock. `RATE_MATCH = 1` is everything this section describes.
Both settings have the same register map; with 0 the words only the buffer drives (RXV18 to RXV28: the rate-match counters and the frequency counter) read 0, and FEATURES bit 3 reads 0 (1 with the buffer).
The rate-matched builds that were measured on the board (below) are `ppm_ctl` and `ppm_all3` (also set `RATE_MATCH = 1`; their TX phase-interpolator attribute is in `ppm.xdc`) and the `rm_ctl` and `rm_all3` build files (the base and `lat_all3` with `RATE_MATCH = 1`).
`GO_REG` (default 1) is the one option left of brief 97's `lat_all3` edit on the 0 path: the go-pulse crossing's output register, which `lat_all3` builds without (0). **Why default 0:** the buffer is needed when a partner's clock differs from ours (a real
link, not a loopback), and costs 11 clocks (68 ns) on this board (below), so the design that is board-proven and fastest stays the default and the buffer is chosen when a link needs it.
**How the default is shown to be the old design:** `results/b96c/eqy_default/` (formal equivalence of the `RATE_MATCH = 0` core against main 6909e43f's core, XPM macros as wires, GT as a black box, with the four stated edits to the proof copy
and the limits: README there) and the core bench at 0 (`tests/core_cocotb_default.py`, main's own bench; 11 clocks, no spread, as 97C; `results/b96c/core_sim_default.json`). Both settings are simulated in CI (`tests/test_b96_pcs_rtl.py`).

**The question.** In the SFP+ loopback the receive clock is recovered from our own transmission, so it has exactly the frequency of the transmit clock. A real partner
(a NIC, a switch) differs by up to +-100 ppm (IEEE 802.3 clause 49), so the two user clocks drift against each other by a clock cycle every 10,000 clocks (62 us) at
100 ppm, and a design that moves a stream across them needs rate matching: delete idles when the partner is faster, insert them when it is slower.

**What the design before 96C did, and what simulation showed.** It crossed only *events* from the receive clock to the transmit clock (the go pulse and a few
pulses by `xpm_cdc_pulse`, the order's fields as a quasi-static bus): no frame stream crossed, so there was no buffer to overflow. Run against a simulated partner whose clock
differs by +-100, +-300 ppm (and +-3000 ppm in a stress run), with 400 feed frames each, it lost nothing, duplicated nothing and fired every order
(`results/b96c/ppm_sim_baseline*.json`). That is a null result and is stated first: **the pre-96C design did not fail at any offset we simulated.** Its dependence on
the offset was indirect: the timestamp of a received frame is late by the crossing's fixed latency plus one clock of phase, and the order bus is sampled five clocks after the
go pulse (`stale` counts a miss), an assumption that holds for any drift this small but is a timing assumption. Rate matching was built because a real link needs it
wherever frames cross (any forwarding, bridging or host-facing path), because it removes those assumptions and, as measured below, because it costs almost no latency here.

**Architecture now.** `pcs_rx` stays in the receive clock. Its decoded blocks (data, control, an ordered-set flag) are written into `rate_match` (a 16-block elastic buffer: AMD's `xpm_fifo_async`, distributed RAM, first-word-fall-through, read data count; the macro carries the pointers, the memory and their clock-crossing
constraints. A hand-made block memory read in the other clock was tried first and gave report_cdc CDC-1 Critical, 38 rows, with or without `set_max_delay -datapath_only` and with `xpm_memory_sdpram`
(`results/b96c/cdc_probe.rpt`, `cdcexp/cdc_x.rpt`): the flow's gate `post_synth_cdc_no_critical` allows none); everything after it, `mac64_rx`, `trade64` and the order path, runs in the transmit user clock (the core clock). The go
pulse, the order bus and the five event pulses of the old design are gone; the decision reaches the order logic in the same clock domain.

**Policy (rtl/rate_match.sv, model/ratematch.py):**
- every valid block is written; if the macro says full (it sees an old read pointer, so this is conservative) the block is dropped and counted (`rm_ovf`);
- the reader outputs at most one block a clock, in 32 of 33 clocks (the 33rd, the pause clock, is the transmit gearbox's cadence);
- in an output clock: a block visible -> pop and output it; none visible and the last output not inside a frame -> **insert one idle block** (`rm_ins`); none visible inside a frame -> output
  nothing for one clock (`rm_stall`; the MAC holds its state; nothing is lost);
- in the pause clock: visible fill (the macro's read data count) above HI (4), last output not inside a frame, at least MIN_KEEP pure idle blocks just output (default 0), head a pure idle block -> **delete it** (`rm_del`);
- *inside a frame* means the last block output was a start block (lane 0 or 4) or a data block. A *pure idle* block is an all-idle control block that is not an ordered set.
  **Ordered sets (the link-fault signalling), error blocks, terminate blocks and every block with data are never inserted, duplicated or deleted**, so no frame and no needed ordered set is touched (checked
  frame by frame against an independent parser in `tests/ratematch_cocotb.py`, with ordered sets and error blocks in the stream);
- while the synchronised block lock is low the reader discards the buffer, one block a clock, and outputs nothing.

**Limits, stated.** (1) *Minimum-gap traffic.* A conforming sender's 12-byte gap holds one pure idle block between a terminate and the next start. A partner 100 ppm fast sending
only minimum gaps must have 100 ppm of its stream deleted (one idle block in about 12,000 blocks); with `MIN_KEEP = 1` (delete only after an idle block was already output) that gap can never be shortened and the buffer overflows
(bench `minimum_gap_partner_faster` with `B96_RM_MIN_KEEP=1`: +300 ppm, 5000 frames: `rm_ovf` > 0, frames cut and failing their FCS, never silent). **The default is therefore `MIN_KEEP = 0`**: a lone idle block between frames
may be deleted, and the bench with it (same stream) loses nothing. The price: the gap after such a deletion can be as small as the terminate block's own trailing idles plus the start block's leading idles (0 to 7 and 0 or 4 bytes),
below the usual 12 bytes. This design's MAC does not check it. **IEEE 802.3 clause 46 and 49 were not available on this machine, so the standard's own minimum receive gap and its deficit-idle-count rules were NOT read**:
whether a downstream consumer would accept such a gap is unverified, and the rule "never delete the last idle block" (`MIN_KEEP = 1`) is the conservative setting if it matters. (2) Inserted idles are plain `/I/` blocks;
a real partner PHY's idle checks are not exercised. (3) Nothing here forwards frames to the transmitter: the buffer exists for the receive path only. (4) The FIFO macro's real latencies are not in the Icarus stand-in
(written from UG974's port descriptions); the board measures them.

**Latency cost.** Simulated with the Icarus stand-in of the macro, in-phase clocks, GT word of the price to GT word of the order's start block: **12 to 13 clocks** (74.5 to 80.7 ns) against 11 before (the receive path through the buffer is
5 to 6 clocks; the 4-clock go crossing it replaces is gone): about +1 to +2 clocks. A first version with a hand-made buffer measured 13 to 14. **The board measured +11 clocks, not +1 to +2 (see "Board result" below);
the stand-in is why: it has fewer pipeline stages than AMD's macro. The analysis and a measurement of the real macro in xsim are in "Why the simulation missed the latency".**

**Frequency counter.** A free-running 32-bit count of receive clocks crosses as a gray code; in the core clock a window of 2^24 clocks (104 ms) and the difference of the last two
samples give the receive clock's cycles per window (RXV27, RXV28): ppm = (count - 2^24) / 2^24 x 10^6, resolution about 0.1 ppm. The board run reports every point's offset from this
counter, not from the setting that was meant to cause it.

**Phase-interpolator ppm controller (UG576 v1.7.1, "TX Phase Interpolator PPM Controller", Tables 3-33 and 3-34, Equation 3-3).** `TXPPM` (0x01C) drives TXPIPPMEN, TXPIPPMSEL and TXPIPPMSTEPSIZE.
From the guide: the controller needs TXPIPPMSEL = 1 and TXPIPPMEN held at 1 while an offset is wanted; TXPIPPMSTEPSIZE[4] = 1 increments the PI code (0 decrements) and [3:0] is the amount, 0 to 15; the offset in continuous mode is
ppm = 10^6 x step / (64 x TXOUT_DIV x TX_INT_DATAWIDTH x (TXPI_SYNFREQ_PPM + 1)); `TXPI_PPM` (UltraScale+) "enables gating reset to the TXPIPPM controller": with 0 the controller is held in reset. The Transceiver Wizard fixes
TXPI_PPM to 0 and TXPI_SYNFREQ_PPM to 1; at 10.3125 Gb/s with a 32-bit internal width (TXOUT_DIV 1) that default gives 244 ppm a step, too coarse for +-100 ppm. The ppm_* builds therefore set TXPI_PPM = 1 and TXPI_SYNFREQ_PPM = 7 through
`ppm.xdc` (both attributes confirmed settable on a synthesised netlist, `results/b96c/txpi_probe.log`), giving **61.04 ppm a step**: reachable points 0, +-61.0, +-122.1, +-183.1 ppm (steps 1, 2, 3), not the brief's 50/100/150.
The controls are clocked in TXUSRCLK (322 MHz), as the guide requires when the internal width is below the user width. The guide's own example (Figure 3-30, "data stream frequency re-synthesis") shows the TX user clock staying on the reference and the fabric doing
character insertion and removal: so the TX buffer, fed at the reference rate, will see the shifted line rate. **Still unknown, and the board decides:** whether TXUSRCLK2 in this Wizard configuration (`TXOUTCLKSEL = 3'b010`, PMA clock)
follows the shifted serial clock (then the receive and core clocks move together and the frequency counter reads 0 ppm at every code, with no relative offset by this route), or stays on the reference (then the GT TX buffer drifts and `GT_BUF` shows overflow/underflow after its depth is used up).
Nothing in the report claims an offset the counter did not measure.

### Board result (2026-11-19, KR260 and an optical loopback; `results/b96c/hw/20261119_080724/`)

The board ran four rate-matched builds from f47986f4 (`rate_match.sv` stamp 95356208; HEAD's lint-only rewrite of that file, a generate-if for `keep_ok`, is proved equivalent to it by eqy, brief run order 2026-11-19 ~08:10):
the base with the buffer (`control`), the all3 variant with the buffer (`all3`), and the two with the TX phase-interpolator controller (`ppm_ctl`, `ppm_all3`). Every number below is in the `stage3.json` and `ppm_session.json` of its variant directory.

**Safety: accepted on all four.** 100 of 100 restarts locked; 500 of 500 orders sent = fired = `order_ok` per variant; every fault counter 0 (poisoned, dropped, underrun, late, stale, bad, err, toolong, order_bad, blocked); polarity ok; SYSMON temperature, VCCINT, VCCAUX and VCCBRAM
inside the DS925 windows at the start and end of every dwell (28 C, 0.715 V, 1.79 to 1.80 V, 0.847 V). At 0 ppm, a 20 s dwell of armed orders: 161,132 orders, all `order_ok`; rate-match inserts 0, deletes 0, overflow 0, stalls 0, visible fill 2 to 3 blocks; GT buffer status 0.

**The ppm finding: no relative offset by this route.** The frequency counter read 0.0 ppm at every TX phase-interpolator code tried (steps 0 to 9, up to a predicted 549 ppm, on both ppm builds), the link stayed up and the GT buffers stayed clean; every non-zero target is recorded
**unreachable**, not passed. The transmit user clock follows the shifted serial clock, and one reference clock feeds both directions, so the receive clock and the core clock move together. **Rate matching under a real offset is therefore not demonstrated on hardware.** It needs
a second reference (two boards, or a second oscillator on the receive side). The simulated partner at +-100, +-300 ppm (`results/b96c/ppm_sim_ratematch.json`) is the only evidence of its behaviour under an offset.

**Latency, rate-matched builds (medians over 100 restarts; clocks of 6.206 ns):**

| Build | E (echo) min / max per link | L (loop) | L minus E (tick to trade) | Against 97C |
|---|---|---|---|---|
| control (base + buffer) | 24.5 / 25.0 | 61 | 36.5 clocks, 226 ns | L 50 to 61: +11 clocks, +68 ns |
| all3 (+ buffer) | 24.0 / 25.0 | 57 | 33 clocks, 205 ns | L 46 to 57: +11 clocks, +68 ns |
| ppm_ctl, 0 ppm | 24.0 / 24.0 | 59 | | (the ppm attribute set; same RTL as control) |
| ppm_all3, 0 ppm | 24.0 / 25.0 | 57 | | |

(The 97C values are `results/b96/hw`, E 20, L 50 and 46; the E medians above are of the per-link minima and maxima as listed in each `stage3.json`.) The prediction made before the board run (`run_96c_stage3.sh`: L 52 to 54 and tick-to-trade 191 to 198 ns for the base) **was missed by 7 to 9 clocks.**

### Why the simulation missed the latency (brief 96C addendum 2)

Two lines. The Icarus stand-in for `xpm_fifo_async` (`flow/cdc_models`) is a pointer-and-memory model with one synchroniser per pointer; AMD's macro registers the crossed write pointer again on the read side, derives `empty` and the read data count from that registered, synchronised pointer
(the extended pointer for the count has two more synchroniser stages in first-word-fall-through mode), so a block becomes visible to the read side several clocks after it was written, and the buffer then rests at a visible fill of 2 to 3 blocks (board: `rm_fmin` 2, `rm_fmax` 3) on top of that.
The in-phase simulation could not show it because the stand-in has no such stages, and the real macro's latency also depends on the phase between the two clocks.

From the macro's source (Vivado 2026.1, `data/ip/xpm/xpm_fifo/hdl/xpm_fifo.sv`, read here, not copied): the write pointer crosses by `xpm_cdc_gray` (`CDC_SYNC_STAGES` = 2 flip-flops) and then a register (`wpr_gray_reg`) in the read clock; `empty` (`ram_empty_i`) is a register loaded from a comparison of that registered pointer with the
read pointer; `rd_data_count` comes from a second, extended pointer synchronised with `DEST_SYNC_FF` + 2 stages when `READ_MODE` is first-word-fall-through (as here). The policy in `rate_match.sv` acts on `empty` and `rd_data_count`, the *delayed* view, so it holds a deeper true fill than it sees.

**Measured, not argued:** `sim/tb_rm_latency.sv` is one testbench, run on the stand-in (Icarus) and on AMD's macro (xsim 2026.1), at four phases between the clocks, 38 frames each, traffic 32 blocks in 33 clocks with a nine-block frame every 200 blocks
(`results/b96c/rm_latency_sim.json`): the time from the clock that loads a frame's start block into the receive path's output register to the clock that loads it into the buffer's output register, in core clocks, mean (min to max):

| Phase (read clock lag, ps) | Stand-in | AMD macro (xsim) |
|---|---|---|
| 0 | 7.7 (7.0 to 8.0) | 11.2 (9.0 to 13.0) |
| 1550 | 7.2 (6.3 to 7.3) | 10.4 (8.3 to 12.3) |
| 3100 | 7.5 (6.5 to 7.5) | 10.7 (8.5 to 12.5) |
| 4650 | 7.7 (6.8 to 7.8) | 10.9 (8.8 to 12.8) |

The real macro adds **3 to 5 clocks over the stand-in at every phase, and widens the spread to about 4 clocks** (the stand-in's is about 1). That accounts for about 5 to 6 of the 9 to 10 clocks missed, not all of them: the buffer takes 10.4 to 11.2 clocks on average with the real macro in this testbench, against the 5 to 6 of the core bench with the stand-in; it replaces the 4-clock go crossing (`cross_go`), so the net is about +6.4 to +7.2 clocks against the +1 to +2 predicted, and the board's +11 leaves about 4 clocks **not explained**: this testbench's traffic is a stand-in for the PCS's stream, not the board's (a looped-back frame stream with the board's gap pattern), and the GT's own delays are the same in both designs.
Brief 96E (a lower-latency buffer: no first-word-fall-through count, an own read-side comparison of the crossed pointer, a shallower fill target) is the route to remove most of the cost where the buffer is wanted.

### Next steps (from the board result)
1. **Brief 96E, a lower-latency elastic buffer:** the cost above is the macro's synchroniser and register stages plus the fill it rests at; a buffer of the same policy with its own gray-pointer crossing (checked by report_cdc) and a fill target of one block is the aim; the figure to beat is +11 clocks (68 ns).
2. **A real offset:** two boards, or one board with a second oscillator on the receive side; the TX phase-interpolator route does not give one (this section). Until then the buffer is shown by simulation only under an offset.
3. The default stays the 97C path (`RATE_MATCH = 0`); a build for a real NIC link sets `RATE_MATCH = 1`.

## 10. On-chip RX eye scan (brief 96D, 2026-11-19)

**What it adds.** A build parameter `EYESCAN` (default 0: the build is unchanged, the GT's DRP and drive ports are tied to the constants they always had). With `EYESCAN = 1` (the `eyescan/` build, with `es.xdc`): a DRP
master and eye-scan point sequencer in the free-running clock (`rtl/es_ctrl.sv`), eight registers (DRP_ADDR, DRP_DATA, ES_CMD, ES_STAT, ES_POINT, ES_TMO, ES_RES at 0x024 to 0x03C, and GT_DRIVE at 0x084; FEATURES bit 4), and the host
side in `flow/eyescan/` (`python -m flow.eyescan`, datasheet in `flow/eyescan/README.md`).

**Why the sequencer is in RTL.** One point is about ten DRP accesses; over the JTAG cable each register operation costs tens of milliseconds, so a 1023-point scan would spend minutes in overhead per access type. The sequencer does one
point per command (a read-modify-write of three DRP words, a poll, two reads, a stop) in under a microsecond of fabric time; the host adds the adaptive prescale ladder, the save and restore and the maths. The twin
(`model/eyescan.py`) lists the DRP traffic one point must produce; `tests/eyescan_cocotb.py` compares it access by access with the RTL's, against a DRP stand-in in `sim/gth_wiz_model96.sv` (a 1024-word register file and the
WAIT, RESET, COUNT, END state machine of UG576 Figure 4-21; its error count is a fixed mixing function of the offsets, a fixture, not physics).

**Decisions and what a user could get wrong.**
- `ES_EYE_SCAN_EN` and `ES_ERRDET_EN` are set in the bitstream (`es.xdc`), because the Wizard leaves both FALSE (read in the generated channel wrapper) and UG576 says re-enabling needs a PMA reset, which would restart the link.
  The host refuses a build where they read 0 (DRP 0x03C [9:8]).
- The sequencer does not restore the offsets and prescale it writes; the host saves 33 DRP words first (the GTHE4's ES_QUALIFIER, ES_QUAL_MASK and ES_SDATA_MASK are ten 16-bit words each; brief 96D saved 18 because it wrote only five, see `results/b96d/hw/README.md`) and writes them back and reads them again (`restore.ok` in every capture).
- TX swing and cursors are driven from a register (GT_DRIVE) in `EYESCAN` builds only. The reset value is the design's old constant (TXDIFFCTRL 11000, 873 mVppd, no cursors); the host and the owner's script never go above it.
- The eye is after the equaliser and each point's depth is limited by its bits; see `flow/eyescan/README.md`.
- The default build was not rebuilt for this brief: with `EYESCAN = 0` the new logic is not elaborated and the GT ports carry the same constants. The regression benches of both `RATE_MATCH` settings pass; an equivalence proof of the default
  against main was not rerun (the change is a generate branch that is not taken).

**IBERT cross-check is not available on the Basic licence.** `ibert_ultrascale_gth` 1.4 creates, generates and synthesises out of context, but top synthesis of a wrapper that instantiates it stops with `ERROR: [Chipscope 16-620] Detected ibert instance 'u_ibert' in the design. Your current selected license is BASIC. This license doesn't cover the feature you selected.` (`results/b96d/ibert_probe_results.txt`; a first run failed only because of a wrapper error, fixed and rerun). The check on the real link is therefore the repeat scans and the TX sweep, not IBERT.

**Not measured.** Nothing in this section has run on a board. The DRP addresses, the 32-bit reading of "bits per sample" and the masks are from UG576 v1.7.1 and are checked in simulation only against our own stand-in.

## 11. A lower-latency elastic buffer (brief 96E, 2026-11-19)

**Result in one line.** `RATE_MATCH = 1` with `RM_OWN = 1` (our own gray-pointer buffer, `rtl/rate_match_gp.sv`, `ENT_SYNC = 1`, build `rm_gp`) adds **+2.3 clocks** (about 14 ns) of GT-port-to-GT-port tick-to-trade over the 97C path in xsim with AMD's real macros, against +5.3 for the buffer of section 9 (`xpm_fifo_async`; the board measured that one at +6.5). That is 0.3 clock outside the brief's "within 2 clocks".
A faster variant (`ENT_SYNC = 0`, build `rm_gp_direct`, +1.2 clocks) exists but fails the flow's CDC gate (38 CDC-1 Critical rows in `report_cdc`), so it is not the default; see "The buffer". Nothing here has been measured on a board (none was approved for this brief): see "What the board must still show".

### Where the board's +11 clocks came from (the accounting)

The +11 of section 9 is the change in the loop latency `L`, and `L` counts the receive path **twice** (section 6: `L = E1 + D + E2`, `E` = transmit start of a probe to the receive-start stamp, `D` = receive-start stamp of the feed to the order's transmit start). The 96C prediction (+1 to +2) and its
later explanation (+6.4 to +7.2) were per-traversal numbers compared with this two-traversal total, which is why "about 4 clocks stayed unexplained". Recomputed from the board's own records (`results/b96c/hw/20261119_080724/control`, `results/b97c/hw/20261118_194221/control`, medians of 100 restarts):

| Quantity (clocks) | 97C board | 96C buffer, board | Change |
|---|---|---|---|
| E (receive-start stamp path, once) | 20 | 24.5 | +4.5 |
| D (feed stamp to order start) | 10 | 12 | +2 |
| L = 2E + D | 50 | 61 | **+11** (= 2 x 4.5 + 2) |
| GT-port tick-to-trade = change in E + change in D | | | +6.5 |

The same quantities in xsim with the real macros (`results/b96e/core_lat_sim.json`, mean over four phases between the clocks, `sim/tb_lat_core.sv`, whole core): receive-start stamp path `S` 5.6 (97C path) and 10.1 (96C buffer): **+4.5, the board's +4.5**; `D` 10.4 and 11.1: +0.75 (board +2); tick-to-trade 10.6 and 15.9: +5.3 (board +6.5);
so the simulated change in `L` is 2 x 4.5 + 0.75 = **9.75 against the board's 11**. **What is left: 1.25 clocks, put in `D` because D is derived as L - 2E (E's own resolution is about half a clock: its per-link minima and maxima medians are 24.5 and 25, and a half-clock of E moves D by one, so the split between E and D is an assumption)** (the board's +2 against the simulated +0.75). It is not explained by simulation: the transceiver is a stand-in in xsim (the real GTHE4 model is refused: 54,716 instances against 50,000), so
anything the GT adds on the board and that differs with the buffer's fill or phase is absent; a post-route timing simulation is not possible for the same reason. It needs the board build with counters (below). The earlier statement that 4 clocks were unexplained is withdrawn: 1.25 are.

Per-stage reading, for the macro buffer's 9 clocks in the whole core (PCS output register to buffer output register, 8.5 to 9.3 over the phases; 10.4 to 11.2 in the buffer-only testbench, whose resting fill is higher): the macro crosses the write pointer through `xpm_cdc_gray` (two destination flops after a source register), registers it again, derives `empty` and the first-word-fall-through output from that register,
and the read data count through two more synchroniser stages (from the macro's source, section 9). The resting fill adds to the wait: with `HI = 4` the policy leaves up to four visible blocks in the buffer. Setting only the fill target to 1 on the macro takes the buffer from 10.4 to 11.2 clocks (tb_rm_latency, section 9) down to 8.3 to 9.0
(`results/b96e/rm_latency_sim.json`, `impl 0 hi 1`): about 2 clocks of the cost is fill; the rest is the macro's total (stages and phase), not a per-stage count. The whole table is in `latency_stages.yaml` (`accounting_96e`).

### The options and what they cost

| Option | Buffer latency, PCS out to buffer out (xsim, mean over 4 phases): in `tb_rm_latency` / in the whole core | Tick-to-trade change vs 97C | Safety and CDC | Verdict |
|---|---|---|---|---|
| 96C: `xpm_fifo_async`, fill target 4 | 10.8 / 8.9 | +5.3 (board +6.5) | report_cdc clean; AMD's macro | the build option of section 9 |
| same macro, fill target 1 | 8.7 / not run | about +3 (estimate: 2 clocks less) | same; policy change only | not built: still +3 |
| **96E: own gray pointers, per-entry synchronisers and a 3-flop pointer (`ENT_SYNC = 1`), fill target 1** | **6.6 / 5.8** (5.5 to 6.3 in the core) | **+2.3** (+2.25 to +2.4 by phase) | `ASYNC_REG` crossings only; `report_cdc` clean; data settled a full clock before the pointer admits it | **chosen: safe, passes the gates, 0.3 clock over the brief's 2** |
| 96E: own gray pointers, direct read of the entry flops (`ENT_SYNC = 0`, the standard async-FIFO read) + `set_max_delay -datapath_only` | 5.5 / 4.8 | +1.2 | safe by the pointer rule, but `report_cdc`: 38 CDC-1 Critical, gate `cdc_no_critical` fails | not shippable without a CDC waiver (a decision for the planner); kept as `rm_gp_direct` |
| GT's own RX elastic buffer with clock correction (UG576) | not measurable: needs a Wizard change and the board | | | **not done**: the Wizard build has both GT buffers enabled (`TXBUF_EN = RXBUF_EN = TRUE`, read back in `results/b96c/txpi_probe.log`; corrected 2026-11-20 by brief 96F, which earlier text here said was the buffer bypass); bypassing them removes the GT's own buffer latency, a GT property still to be measured on the board (brief 96F, `docs/loop_timing_feasibility.md`); UG576's clock correction works on 8B/10B-style or user-defined sequences, and whether it applies to 64B/66B in this configuration was not established here |
| Decision in the recovered clock, only the order crosses | 0 (it is the 97C path) | 0 | the 97C path: events cross, the stream does not | exists already as `RATE_MATCH = 0`; it needs no rate matching for the trading decision (96C showed it survives +-3000 ppm), and rate matching would be needed only for a consumer of the frame stream in the core clock, which this design does not have |

### The buffer (`rtl/rate_match_gp.sv`)

Same ports and the same insert/delete policy as `rate_match.sv`. 16 blocks of 74 bits in flip-flops in the write clock, each written once and held until the reader has released it (the writer sees the read pointer and never overwrites an unread entry). The write pointer crosses as a gray code (`xpm_cdc_gray`: a source register one write clock after the entry was loaded, then destination flops).
The read pointer crosses back the same way; the writer stops at 16 outstanding blocks as it sees them. The policy reads the exact pointer difference as the read side sees it (`HI = 1`, not the macro's lagging count with 4). The pointers are never reset (the reader drains while the lock is low).

**Two read structures were built (parameter `ENT_SYNC`, build parameter `RM_DIRECT`).**
1. **`ENT_SYNC = 1` (default, `rm_gp`).** Every entry is also copied bit for bit through its own two-flop `ASYNC_REG` synchroniser (`xpm_cdc_array_single`) and the write pointer crosses with **three** flops. A data bit that goes metastable in its first flop resolves within a clock, so its copy has settled after its second flop; the pointer's third flop makes the pointer arrive at least one clock later than that, whatever the routing skew between the bits (while it is under a clock).
   This is what the first version lacked: with a two-flop pointer the margin was 0 to 1 clock and a late-resolving bit could arrive in the pointer's clock, a torn word (the planner's review, 2026-11-19). It costs one clock.
2. **`ENT_SYNC = 0` (`rm_gp_direct`).** The standard asynchronous FIFO read, as the planner asked: the reader selects the entry flops directly with its read pointer and registers the result in the read clock; the pointer (2 flops) admits an entry about 2 read clocks after it changed, so it is stable when read; the path is bounded by `rate_match_gp.xdc`
   (`set_max_delay -datapath_only` 6.206 ns, one read-clock period, from the entry flops to the instance's read-clock registers, scoped by name, AMD's XPM FIFO constraint style, `flow/xpm_cdc.tcl`). **Result: Vivado's `report_cdc` cannot classify it:** 38 CDC-1 "1-bit unknown CDC circuitry" Critical rows (the entries were inferred as distributed RAM; the endpoints are the output register, `in_frame`, and the enables of `n_del` and `rbin`), each already listed with exception
   "Max Delay Datapath Only", so the constraint does not change the classification, exactly as in 96C's hand-made buffer (`results/b96c/cdc_probe.rpt`, same 38). The flow gates `post_synth_cdc_no_critical` and `cdc_no_critical` fail (28 of 29 gates); methodology had no criticals; timing met (WNS +0.079 ns). AMD's own FIFO is not flagged because its memory path is inside the macro; a design of our own
   cannot get the same classification without a waiver, which suppresses a gate and is not done here. The direct variant is kept (parameter, twin test, build record) as the measurement of what the standard structure would give: **4.8 clocks in the core, +1.2 tick-to-trade**.

Latency is set by the pointer crossing, not by the data path: removing the data synchronisers (variant 2) is one clock faster only because the pointer has two flops instead of three; the data synchronisers themselves ran in parallel with the pointer.

**MTBF, stated.** The pointers and (variant 1) every data bit cross in two-flop `ASYNC_REG` synchronisers (`xpm_cdc_gray`, `xpm_cdc_array_single`: the structure whose MTBF AMD documents) at 161 MHz. Variant 1's one-clock settling margin is the standard "wait one more clock before using multi-bit data" rule; it is checked in simulation (the twin, the whole-core bench), not proved.
Known gap: The per-entry data path to the first synchroniser flop (write-clock entry flop to the first `xpm_cdc_array_single` flop) has no max-delay bound: the one-clock margin of `ENT_SYNC = 1` covers normal routing, but it is not constrained. Caveat: the gray pointer assumes at most one step per destination clock, which a write clock up to 200 ppm faster can break briefly (the macro has the same exposure; the Icarus stand-ins cannot test it).

### The builds (`rm_gp`, `rm_gp_direct`)

Through the heavy slot with `FDA_VIVADO_THREADS=1` under a 6 GiB scope (`results/b96e/builds/<name>/`; both built from clean trees).

| Build | Gates | WNS / WHS (ns) | LUT / FF | Power, Tj | `report_cdc` | Stamp |
|---|---|---|---|---|---|---|
| `rm_gp` (`ENT_SYNC = 1`, built at 9c8f1319) | **all 29 true** | +0.164 / +0.010 | 6,730 / 18,938 | 1.105 W, 48.2 C | no CDC-1; 0 critical; CDC-3 info 1,194; CDC-6 warning 6 (as before); the gates `cdc_no_critical` and `cdc_structure_clean` pass (`cdc_summary.txt`) | `b72d3f46`, recomputed from the tree: `b72d3f46` |
| `rm_gp_direct` (`ENT_SYNC = 0`, built at an earlier commit of this branch) | 28 of 29: `post_synth_cdc_no_critical`, `cdc_no_critical` fail | +0.079 / +0.011 | 6,557 / 15,434 | | **CDC-1 Critical 38** (`cdc_summary.txt`) | `05b0a150` (RTL since changed by the `ENT_SYNC` parameter: not reproducible from this tree) |

`rm_gp`: DRC and methodology critical warnings 0 (15 methodology warnings: LUTAR-1 x5, XDCH-2 x10, as before); 1,422 s, Vivado resident peak 4,398 MiB, the 6 GiB scope cap was hit 35 times with 16 MiB of swap (the base build had none; harmless here, but run it alone); 0 DRC errors. Against `rm_ctl` (the macro buffer): +117 LUT, +3,271 FF.
Stamp check: `flow.prepare.sources_sha256` over the sources, constraints and IP Tcl of `designs/b96_kr260_10g/rm_gp/build.yaml`, recomputed from the current tree, equals the build's stamp, and `git diff` of the RTL, the build directory and the flow since the build commit is empty. The bitstream (`rm_gp/build/base/kr260_10g_top.bit`, git-ignored) has not been loaded on a board.
The first per-entry-synchroniser version's records (2-flop pointer, WNS +0.105 ns, all 29 gates, stamp `1a2fa1a8`) are kept in `results/b96e/builds_v1_per_entry_sync/` and `results/b96e/v1_per_entry_sync/`: rejected for the 0-to-1-clock margin above.

### How it was checked

- `tests/ratematch_cocotb.py` against the new twin `RateMatchGP` (`model/ratematch.py`), for both `ENT_SYNC = 1` (`test_rate_match_gp_cocotb`) and `ENT_SYNC = 0` (`test_rate_match_gp_direct_read_cocotb`), output for output and every counter, on the 96C scenarios (same clocks, partner +-400 ppm, minimum-gap +300 ppm over 5000 frames, ordered sets and errors, lock drop, counter clear): `test_rate_match_gp_cocotb` passes; every frame intact, overflow 0.
- The whole-core bench with the own buffer (`test_core_cocotb_rm_own`, `ENT_SYNC = 1`): all tests of `tests/core_cocotb.py` pass.
- xsim with the real macros, whole core: `sim/tb_lat_core.sv` (above); the buffer alone: `sim/tb_rm_latency.sv`.
- The default (`RATE_MATCH = 0`) path is untouched: the `eqy` proof of 96C re-run on this branch (`results/b96c/eqy_default/result_default.txt`) and the default bench.
- `tests/test_b96_generics.py`: the structural check of `GO_REG` in `lat_all3/build.yaml` against `lat_all3/variant.json` (96C follow-up).
- The xsim refusal of `initial` blocks beside `always_ff` in `rate_match.sv` is fixed (declaration initialisers); `b96_core.sv` has a declaration moved before its first use (`tx_pol_t`, `rx_pol_r`: xsim refuses the implicit declaration). Neither changes behaviour; the second is on the default path and is covered by the eqy re-run.

### What the board must still show

1. E, L and D of the `rm_gp` build (`_handoff/fpga_agent/run_96e_stage3.sh`): predicted from the simulation (`rm_gp`: receive-start path +1.4, D +0.9, so dL = 2 x 1.4 + 0.9 = 3.7), plus the 1.25 of `D` that simulation does not explain: L about 54 to 55 clocks (97C 50, 96C buffer 61), tick-to-trade about +2.3 to +3.5 clocks.
2. The buffer's own counters at 0 ppm (RXV18 to RXV26: inserts, deletes, stalls, overflow, fill min and max).
3. The remaining 1.25 clocks of `D`: a build with ILA or stamp counters at the buffer's input and output, or the same quantity from the E and D of two builds.
4. Behaviour under a real offset: `docs/real_offset_plan.md` (a plan for the owner to approve; nothing bought or wired).

## 12. GT buffer bypass, build `rm_gp_bypass` (brief 96F1, 2026-11-20)

Both GT elastic buffers (TX and RX) bypassed on top of build `rm_gp`; everything else as `rm_gp` (`RATE_MATCH = 1`, `RM_OWN = 1`, `ENT_SYNC = 1`). No loop timing, no direct crossing: the elastic buffer `rm_gp` still does the receive-to-transmit crossing. The default build and `rm_gp` are unchanged. **Nothing here ran on a board**; the saving is the 96F prediction (E falls 2.9 to 4.5 clocks, tick-to-trade about 205 ns to 177 to 187 ns, third-party GTY figures, UNCONFIRMED for this GTH) and the board test is pre-registered (`results/b96f1/preregistration.md`, script `_handoff/fpga_agent/run_96f1_stage1.sh`).

**How it is built.** `ip/amd_ip_bypass.tcl`: the Wizard configuration with `TX_BUFFER_MODE 0`, `RX_BUFFER_MODE 0` (the Wizard then selects `TXOUTCLKSEL` 101 itself and adds the auto-mode buffer-bypass controllers; it also moves `FREERUN_FREQUENCY`, which the script sets back to 100 MHz). `rm_gp_bypass/rtl/b96_core.sv` is a copy of `rtl/b96_core.sv` (a unit test lists the only lines that differ) with the controllers' ports connected and `rm_gp_bypass/rtl/gt_bp_gate.sv` (since 96F1b wrapped by `gt_bp_ctl.sv`, section 12.1) in each direction: the paths leave reset only when the reset helper is done AND the controller has restarted and finished for this sequence with no error (the controller's done from the previous sequence stays high for 6 to 12 clocks after the reset-done edge, measured in `results/b96f1/bypass_seq/`). TX_DONE and RX_DONE (GT_STAT) follow that gate. FEATURES bit 6 and GT_BUF bits 15:10 are new (`docs/register_map.md`). Stage 0 findings (options, ports, attributes, dynamic fractional-N): `results/b96f1/wizard_probe/README.md`.

**Simulated, and not.** (a) The Wizard's own controllers (generated sources) with our gate against a stand-in transceiver: 28 checks pass (start by itself on the reset-done edge, done and error, stale done, error holds the gate, reset clears; alignment times 3 to 400 clocks). (b) The whole core in xsim with the real XPM macros and a stand-in transceiver with controller ports: link up, 8 orders, tick-to-trade 13.4 clocks, identical to `rm_gp` (13.4): the datapath is unchanged. **Not simulated:** the GTHE4 itself (the Basic simulator refuses the real model), so the alignment latency, the phase it gives and the saving are unknown until the board. The stand-in's alignment time is not a measured figure.

**Build results** (`results/b96f1/builds/`, both built from this tree through the heavy slot, Vivado 2026.1, 1 thread):

| | `rm_gp` (rebuilt here) | `rm_gp_bypass` |
|---|---|---|
| Gates | 29 of 29 | 29 of 29 |
| WNS / WHS (ns) | +0.055 / +0.011 | +0.090 / +0.010 |
| LUT / FF / BRAM / DSP | 6,842 / 18,940 / 0 / 0 | 6,878 / 19,006 / 0 / 0 |
| Power (vectorless) | 1.124 W | 0.933 W |
| `report_cdc` | 0 critical (CDC-3 info 1,194; CDC-6 warning 6; CDC-15 warning 2,107) | 0 critical (CDC-3 info 1,198; CDC-6 warning 6; CDC-15 warning 2,107); no waivers |
| Methodology | 0 critical, 15 warnings (LUTAR-1 x5, XDCH-2 x10) | 0 critical, 15 warnings (as before) |
| Stamp | `6fd8a2bf` | `b2a7aeea` |
| Wall, resident peak | 1,530 s, 4,436 MiB (scope cap hit 87 times) | 1,441 s, 4,413 MiB (0 hits) |

`report_property` of the GTHE4_CHANNEL in both post_route checkpoints: TXBUF_EN and RXBUF_EN TRUE against FALSE, TX_XCLK_SEL TXOUT against TXUSR, RX_XCLK_SEL RXDES against RXUSR, TX_FIFO_BYP_EN 0 against 1, TX_PROGDIV_CFG 0 against 16 (`results/b96f1/wizard_probe/`). The vectorless power difference is a tool estimate, not a measurement. The `rm_gp` control here (WNS +0.055) differs from 96E's record (+0.164) because the tree is current main, not the 96E branch.

**Caveats.** The TX phase-interpolator ppm block is powered down by the Wizard in this configuration (`TXPIPPMPD_VAL = 1`): the ppm registers do nothing here. In loopback there is no frequency offset, so the rate matcher's slip path is not exercised. The controllers' reset drive was our choice in 96F1 and is AMD's example design's since 96F1b (section 12.1). The bypass controllers' done and error are in the status registers; TXBUFSTATUS and RXBUFSTATUS are meaningless with the buffers bypassed.

### 12.1 Reset drive and alignment timeout with retry (brief 96F1b, 2026-11-20)

Build `rm_gp_bypass` only; the default build and `rm_gp` are unchanged. `rm_gp_bypass/rtl/gt_bp_ctl.sv` wraps each direction's buffer-bypass controller (and `gt_bp_gate`). It follows the Wizard's generated example design (PG182; the example's top and init files were generated and read in brief 96F2, whose note is `designs/b96_kr260_10g/docs/loop_timing_sources.md` section 2; the generated files are AMD's and are not committed). The citation for leaving out AMD's RX term is that note's reading of the comment in AMD's generated example (the RX controller's reset also includes the TX controller's done "for this loopback configuration").

| Behaviour | What it does | Why / where it differs from AMD's example |
|---|---|---|
| Reset source | the user clock helper's **active** level (`gtwiz_userclk_{tx,rx}_active_out`) through `xpm_cdc_async_rst` (4 stages, asynchronous assert, synchronous release) clocked by that direction's user clock | AMD's example: the inverse of the same level through a 5-flop reset synchroniser (the house rule allows an asynchronous reset only in a synchroniser). 4 stages is the house XPM convention. The reset falls on a rising clock edge, 5 clocks after the level rises (measured in `tb_bp_ctl`). |
| RX reset has no TX term | AMD also holds its RX controller in reset while the TX controller is not done; we do not | AMD's own comment marks that term as specific to its loopback example. RX alignment (RXDLYSRESET, RXSYNCDONE, RXPHALIGNDONE) uses no TX signal, so on a real link it only delays the RX. |
| Reset while the GT is resetting | the controller is also held in reset while the reset helper's done is low | **Found in simulation:** the controller starts only from idle, so one hung waiting for SYNCDONE ignores the next reset-done edge and stays hung. AMD's example avoids it because its init state machine resets everything. A side effect: the controller's done and error are cleared at the start of every sequence (`gt_bp_gate` stays as the safeguard). |
| Timeout | the timer counts clocks while the controller is out of reset, the reset helper is done and this sequence's alignment has not finished; 4,833,984 TXUSRCLK2 clocks (30 ms) for TX, 20,947,266 RXUSRCLK2 clocks (130 ms) for RX at 161.1328125 MHz | AMD's example times its whole init (reset sequence included) with 30 ms and 130 ms. Here a slow GT reset (a late receive CDR, for instance) is **not** reported as an alignment failure: it has its own status bits (GT_STAT). |
| Retry | at the timeout the controller is held in reset for 8 clocks, then restarts by itself (it starts on the first clock after its reset is released while the reset helper's done is high); the timer restarts | AMD's example retries by resetting the whole GT (`reset_all`). Retrying the controller alone is cheaper but cannot recover a fault that needs the GT reset. |
| Bound and give-up | 3 retries (4 attempts); the next timeout sets **gave up**, which stays until the next GT reset sequence | AMD's retry counter saturates at 15 and never gives up. We choose 3 because a hang that survives three controller resets is not a start-up race; the host reads the flag and fails the run. |
| Alignment error | not retried: the controller's error (PHALIGNDONE not high at the end) keeps the direction in reset until the next GT reset sequence, as in 96F1 | AMD's example only shows it on a VIO. Stricter, deliberately. A retry-on-error variant is a follow-up if the board shows errors that clear. |
| Clock inactive | clears the timer, the retry count and the gave-up flag at once | |

**Status.** GT_BUF bits 29:16 (`docs/register_map.md`): retry counts (4 bits per direction), gave-up now, gave-up seen since the last clear, retried seen since the last clear; the host driver reads them after the receive-datapath restarts and at every full GT restart (`host/b96f1_bypass.py`). A gave-up flag is a FAIL in the pre-registration (amendment 2026-11-20, `results/b96f1/preregistration.md`); a retry that recovers is recorded, not judged. The retry counts clear when the reset helper's done drops, so read them after the link is up (the driver does); the seen bits survive until CMD bit 0.

**Simulated** (`results/b96f1b/bypass_ctl/`, xsim 2026.1, AMD's controllers from the generated sources against a stand-in transceiver whose alignment time is not a measured figure): reset assert and release timing; normal start; one hung attempt (the timeout fires at the programmed clock count, the reset lasts 8 clocks, the retry succeeds); two retries and the maximum of three; give-up (flags set, no further resets, cleared by the next sequence, which then works); error not retried; the clock going inactive mid-attempt; a GT reset during a retry pulse; and the real 30 ms and 130 ms values (one hang each, recovered by the retry). The whole core (`results/b96f1b/core_sim.sh`): link up with the registers showing no retry; link up after one retry with retries = 1 and gave-up = 0; never aligned: no link, gave-up set, retries = the limit. **Not simulated:** what the real GTHE4 does when an alignment hangs (whether a controller-only reset recovers it), and the real alignment time. The 30 ms and 130 ms limits are AMD's example values, not measured against this transceiver: a real alignment that is slower than the limit would be retried until it gave up (the board test would then show a gave-up flag, a FAIL, and the retry counts say how close).

**Build results** (`results/b96f1b/builds/rm_gp_bypass/`, built from commit c387a2e7 of branch `b96f1b-bypass-reset`, origin/main ddc62aa5 as its base, through the heavy slot, Vivado 2026.1, 1 thread), against the 96F1 build of the same variant:

| | 96F1 `rm_gp_bypass` | 96F1b `rm_gp_bypass` |
|---|---|---|
| Gates | 29 of 29 | 29 of 29 |
| WNS / WHS (ns) | +0.090 / +0.010 | +0.118 / +0.010 |
| LUT / FF / BRAM / DSP | 6,878 / 19,006 / 0 / 0 | 6,774 / 19,127 / 0 / 0 |
| Power (vectorless) | 0.933 W | 0.926 W |
| `report_cdc` | 0 critical (CDC-3 info 1,198; CDC-6 warning 6; CDC-9 info 4; CDC-15 warning 2,107); no waivers | 0 critical (CDC-3 info 1,200; CDC-6 warning 8; CDC-9 info 4; CDC-15 warning 2,107); no waivers |
| Methodology | 0 critical, 15 warnings (LUTAR-1 x5, XDCH-2 x10) | 0 critical, 15 warnings (as before) |
| Stamp | `b2a7aeea` | `86037ce1` |
| Wall, resident peak | 1,441 s, 4,413 MiB (0 scope cap hits) | 1,834 s, 4,405 MiB (209 scope cap hits, no OOM kill: other jobs shared the machine) |

The two extra CDC-6 warnings are the retry counts (4 bits each, `u_core/u_s_brt` and `u_s_brr`): they cross from the user clocks to the 100 MHz clock as a plain 4-bit value, not gray coded, because they change only at timeouts (milliseconds apart); **a read within a few clocks of a change, or of the clear at a new reset sequence, can return a transient value, so read the field after the link is up or twice** (the host driver reads it after link-up). The LUT count is 104 lower than 96F1's although logic was added: the placer and the tree differ (main moved), not a measured effect of the change. The reset synchronisers are the CDC-9 rows' kind of structure and raised no new finding.

