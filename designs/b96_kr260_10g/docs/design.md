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
words long, so the verdict (1 to 2 clocks after the decision) arrives long before the order's last word (asserted in
simulation, and stated as a timing assumption). Configuration crosses by `xpm_cdc_handshake` per domain.

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

## 6. Loop measurement method (pre-registered; stage 3)

With one port the loop crosses the link twice for the trading loop.

- **Echo**: TX start of a probe frame (UDP port 5802) to RX start of the same frame: E = T_tx + fibre + T_rx.
- **Trading loop**: TX start of a feed frame to RX start of the order (port 5801): L = E1 + D + E2 where D is the time
  from RX-start of the feed to TX-start of the order. So **D = L - 2E, not L - E** (the brief's "trading loop minus one echo"
  counts one pass of the link; the loop has two). Stated here before any data; if the owner's meaning differs it is
  recomputed from the recorded L and E.
- **Counter**: one free-running 32-bit counter in TXUSRCLK2. The RX start event crosses by `xpm_cdc_pulse`; the
  timestamp is therefore known to one clock plus the fixed synchroniser delay (recorded, calibrated by the near-end PMA
  loopback where TX and RX run from the same reference). Uncertainty stated as +/- 1 clock (6.2 ns).
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

**Architecture now.** `pcs_rx` stays in the receive clock. Its decoded blocks (data, control, an ordered-set flag) are written into `rate_match` (a 16-block elastic buffer, one
distributed-RAM array, gray pointers through `xpm_cdc_gray`); everything after it, `mac64_rx`, `trade64` and the order path, runs in the transmit user clock (the core clock). The go
pulse, the order bus and the five event pulses of the old design are gone; the decision reaches the order logic in the same clock domain.

**Policy (rtl/rate_match.sv, model/ratematch.py):**
- every valid block is written; if the buffer is full as the write side sees it (it sees an old read pointer, so this is conservative) the block is dropped and counted (`rm_ovf`);
- the reader outputs at most one block a clock, in 32 of 33 clocks (the 33rd, the pause clock, is the transmit gearbox's cadence);
- in an output clock: a block visible -> pop and output it; none visible and the last output not inside a frame -> **insert one idle block** (`rm_ins`); none visible inside a frame -> output
  nothing for one clock (`rm_stall`; the MAC holds its state; nothing is lost);
- in the pause clock: visible fill above HI (4), last output not inside a frame, at least one pure idle block just output, head a pure idle block -> **delete it** (`rm_del`);
- *inside a frame* means the last block output was a start block (lane 0 or 4) or a data block. A *pure idle* block is an all-idle control block that is not an ordered set.
  **Ordered sets (the link-fault signalling), error blocks, terminate blocks and every block with data are never inserted, duplicated or deleted**, so no frame and no needed ordered set is touched (checked
  frame by frame against an independent parser in `tests/ratematch_cocotb.py`, with ordered sets and error blocks in the stream);
- while the synchronised block lock is low the reader discards the buffer, one block a clock, and outputs nothing.

**Limits, stated.** (1) A deletion needs a pure idle block after one already output: a partner at +ppm that sends frames with only the minimum gap and no second idle block for a long time cannot be
compensated; the buffer then fills and `rm_ovf` counts blocks lost (the frame is cut and fails its FCS: fail closed, never silent). (2) A deletion leaves at least one idle block between
frames, so the gap after a deletion can be as small as 8 bytes plus the terminate's own idles, below the usual 12; this design's MAC does not check it, a downstream consumer might.
(3) Inserted idles are plain `/I/` blocks; the idle-block checks of a real partner's PHY are not exercised. (4) Nothing here forwards frames to the transmitter: the buffer
exists for the receive path only.

**Latency cost.** Simulated, in-phase clocks, GT word of the price to GT word of the order's start block: **13 to 14 clocks** (80.7 to 86.9 ns) against 11 before (the receive
path through the buffer is 6 to 7 clocks; the 4-clock go crossing it replaces is gone). Table and the board's figure: the 96C report. The write-to-read latency is the gray
register (1) + two synchroniser flops + the decoded pointer register (`WP_REG`, 1) + the output register (1) plus the wait for the next output clock.

**Frequency counter.** A free-running 32-bit count of receive clocks crosses as a gray code; in the core clock a window of 2^24 clocks (104 ms) and the difference of the last two
samples give the receive clock's cycles per window (RXV27, RXV28): ppm = (count - 2^24) / 2^24 x 10^6, resolution about 0.1 ppm. The board run reports every point's offset from this
counter, not from the setting that was meant to cause it.

**Phase-interpolator ppm controller.** `TXPPM` (0x01C) drives the GT's TXPIPPMEN, TXPIPPMSEL and TXPIPPMSTEPSIZE. The Transceiver Wizard fixes `TXPI_PPM` to 0 and offers no setting for it;
the ppm_* builds set it on the primitive through `ppm.xdc` (confirmed settable on a synthesised netlist, `results/b96c/txpi_probe.log`). **Unconfirmed, because UG576 is not on this machine: whether
`TXPI_PPM` alone enables the controller, the encoding of the step code, and whether TXUSRCLK2 (taken from the PMA's output clock in this Wizard configuration,
`TXOUTCLKSEL = 3'b010`) follows the shifted serial clock.** If it does, the receive and core clocks move together and the counter will read 0 ppm at every code; the board run then reports "no relative offset
obtainable this way" (and the GT buffer status, `GT_BUF`, shows whether the TX buffer slipped). Nothing in the report claims an offset the counter did not measure.
