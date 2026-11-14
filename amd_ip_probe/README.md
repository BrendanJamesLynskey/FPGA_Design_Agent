# amd_ip_probe: black-box probes of AMD AXI4-Lite IP, in simulation (brief 69)

This folder holds the benches that measure how AMD's AXI4-Lite IP behaves at its register port, so that our own
register blocks can say where they differ and so that a design that mixes the two is warned. The method (house rule
"Choosing a house convention: measure the vendor first") is: drive the generated IP through our AXI transactor
(`axi_tx/rtl/axil_tx_master.sv`, brief 59A) while our AXI4-Lite protocol checker (`axi_tx/rtl/axil_checker.sv`) watches
every wire, in the Vivado Simulator (xsim) of Vivado 2026.1 (Basic tier). The results are in
[results/69_amd_ip_conventions](../results/69_amd_ip_conventions/README.md) with the summary table.

Nothing here is implemented or run on a board. The IP is simulated as delivered; its source in the Vivado install was
read only to explain a measured result, and none of it is copied.

## What is probed, per IP

Each bench prints one line per probe (`PROBE|name|key=value ...`, then the protocol checker's rule mask since the
previous line) and `run_probe.py` turns them into a JSON record. The probes follow the checklist of our own register
datasheets (docs/hwsw.md, "House conventions"):

| Datasheet point | How it is probed |
|---|---|
| Hole inside the IP's window: response and read data | a read of every word of the window; a write of 0xFFFFFFFF to every word, then a read of every register for a change |
| Aliasing (partial address decode) | the same write scan: a write to a hole that changes a real register is an alias; a read of a hole that returns a register's value is one too |
| Reserved bits | write ones to each register, read back; write each single bit of a control register from reset |
| Read side effects | repeated reads (a status read, a FIFO read), the status afterwards |
| Clear and set, and their same-clock priority | write-1-to-clear or toggle registers; a hardware event timed to the clear in a sweep of one-clock steps; the delay from event and from clear to the interrupt output places the coincident clock (an estimate, stated as one) |
| Byte strobes | a write with strobe 0000, and with one byte lane, from a cleared register |
| Narrow and unaligned accesses | writes and reads at word + 1, + 2, + 3 |
| Outstanding transactions | two reads (or two writes) back to back with RREADY (BREADY) held low; how many addresses and data the IP takes before the first response |
| AW alone, W alone | the lone channel driven for 20 clocks; accepted or not, any response |
| Wide values | the Timer's 64-bit cascade read across a carry, 12 alignments each way |
| Reset | every register read after a reset that follows writes to all of them |
| Interrupts | level or pulse, how cleared, masks |
| Interconnects | the response and read data for an address outside every slave, a slave's own SLVERR through the interconnect, ordering and outstanding across two slaves |

## Files

| File | What |
|---|---|
| [`run_probe.py`](run_probe.py) | generates the IP (or a block design for the interconnects), compiles the bench with our transactor and checker, runs xsim, writes the record. `python3 amd_ip_probe/run_probe.py gpio --record results/69_amd_ip_conventions/gpio.json` |
| [`ips.py`](ips.py) | the IP configuration each bench runs against |
| [`tb/probe_common.svh`](tb/probe_common.svh) | clock, reset, transactor, protocol checker, raw channel drive, the shared probes |
| `tb/tb_<ip>.sv` | one bench per IP (`tb_ic.sv` serves both interconnects) |
| [`summary_spec.py`](summary_spec.py), [`summarise.py`](summarise.py) | the summary table, written from the records and checked against them |
| [`tests/test_records.py`](tests/test_records.py) | checks the records, the table and the notes against each other (runs in CI, no simulator) |
| [`../flow/amd_ip_notes.py`](../flow/amd_ip_notes.py) | the agent's note: which of these IP a design instantiates and what to watch for |

## How to re-run

Needs a local Vivado 2026.1 and a heavy slot (`_handoff/take_heavy_slot.sh`; each run is a small Vivado batch plus a
short simulation, about 1 to 3 minutes, under 2 GB). Run under `systemd-run --user --scope -p MemoryMax=4G`. xsim is not
available in CI, so CI checks the committed records, not a fresh simulation.

## Gotchas found while writing the benches

- A string-valued conditional operator in a task argument crashes the Vivado simulator kernel; use `if`/`else`.
- A `while (int'(cyc) + 4 < ...) @(posedge aclk);` loop hung xsim in a bench (cause not found); wait a counted number of clocks instead.
- Raw drive code must sample every handshake AT the clock edge before it waits to change a signal; a `#1` inside a
  sequence of `if` statements shifts the later samples past the edge (this gave wrong handshake counts in a first version).
- An IP created from the IP catalogue is simulated through the project flow (`launch_simulation`); `axi_interconnect`
  cannot be created outside IP Integrator ("only supported in IP Integrator"), so both interconnects run in a block design.
