# axil_xbar 0.1.0

AXI4-Lite crossbar, N_M masters to N_S slaves: a write and a read arbiter per slave (round robin), so transfers to different slaves overlap; one write and one read in flight per master; DECERR from the crossbar for unmapped addresses.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated (with the AXI4-Lite protocol checker axi_tx/rtl/axil_checker.sv on every link); built inside designs/b65a_axil_soc.

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `N_M` | 1 | 1..16 | masters |
| `N_S` | 1 | 1..32 | slaves; S_BASE (N_S x ADDR_W bits) and S_BITS (N_S x 8 bits) give the map, set by the block-design generator |
| `ADDR_W` | 32 | 12..64 | address bits on every port |

Out-of-space values fail at elaboration with `$error` (tested: `N_M=17`, `N_S=33`, `ADDR_W=8`).

## Interfaces

- `s_axil`: axi4-lite (dir slave). one port per master, packed (master m at bits [m*W +: W] of every signal); 32-bit data
- `m_axil`: axi4-lite (dir master). one port per slave, packed (slave s at bits [s*W +: W]); slave s owns 2**S_BITS[s] bytes from S_BASE[s]

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- write: 4 clocks from AWVALID and WVALID to BVALID at the master when the slave is free and answers at once (accept, forward, slave B, hand back)
- read: 4 clocks from ARVALID to RVALID at the master on the same terms
- throughput: one write and one read per master in flight; transfers to different slaves proceed at the same time; per slave, one write and one read at a time

## Evidence

Python masters and slaves with random VALID gaps and READY stalls drive the crossbar at five parameter points; every write must reach exactly the owning slave with the same address, data, strobes and protection, every read must return the data and response the owning slave produced for it, unmapped addresses must get DECERR from the crossbar, and the AXI4-Lite protocol checker (axi_tx/rtl/axil_checker.sv) watches every master and slave link for rule violations. Round-robin fairness of reads and of writes under full contention, a reset with a write and a read in flight (nothing stale after it), and the parameter guards (misaligned or overlapping map; simulation only, synthesis ignores them) are tested too. Tests: `ip_lib/axil_xbar/tb/test_axil_xbar_rtl.py`.

Try it: `python3 -m pytest ip_lib/axil_xbar/tb/test_axil_xbar_rtl.py`.

Parameter points simulated: `N_M=1, N_S=1, ADDR_W=32`; `N_M=2, N_S=3, ADDR_W=32`; `N_M=3, N_S=4, ADDR_W=32`; `N_M=4, N_S=2, ADDR_W=16`; `N_M=2, N_S=5, ADDR_W=12`.

Seeded faults (`faults.yaml`, run by `hil/ip_faults.py --blocks axil_xbar`):

| Fault | What it breaks | Result |
|---|---|---|
| `decode_double_range` | every slave decodes twice its range, so part of a hole (or a neighbour) is sent to it | caught |
| `round_robin_stuck` | the read arbiter never moves on, so the lowest-numbered master wins every contest | caught |
| `bresp_dropped` | a slave's SLVERR is passed back as OKAY | caught |
| `rdata_from_slave0` | every read returns slave 0's data | caught |
| `decerr_stale_data` | a read of an unmapped address returns the previous read's data with DECERR | caught |
| `awvalid_waits_for_wready` | AWVALID depends on the slave's WREADY and drops when it falls (IHI 0022H A3.2.1, A3.3.1) | caught |
| `b_before_slave_response` | the master sees BVALID while the write is still being forwarded | caught |
| `wstrb_forced` | byte strobes are lost, so a partial write becomes a full-word write | caught |
| `write_round_robin_stuck` | the write arbiter never moves on, so the lowest-numbered master wins every write contest (from the review) | caught |
| `busy_not_reset` | the slaves' busy flags start at 0 at power-up but a reset does not clear them, so a reset with a transfer in flight leaves a stale request (from the review) | caught |

## Boundary and reuse

- Registered outputs: every VALID and payload, to either side, comes from a register; AWREADY, WREADY and ARREADY towards a master are combinational from its request (the grant), which IHI 0022H allows.
- Clock crossings: none (one clock; put a clock converter on a link that crosses domains).
- Part, board or pin: none.
- Depends on: nothing.
- Limits: AXI4-Lite only (no bursts or IDs); 32-bit data; waits for both AWVALID and WVALID before it accepts a write; no register slices or timeouts (a slave that never answers stalls its master); fixed round robin, no priorities or QoS.

## Cost table

in-context cost inside designs/b65a_axil_soc (one master, three slaves): see results/65a_blockdesign; the OOC sweep is still to do.

Licence: MIT (this repository).
