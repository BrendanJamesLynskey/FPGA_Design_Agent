# axi_reg_slice datasheet (version 0.1.0, brief 151)

AXI4-Lite (`axil_reg_slice`) and AXI4 (`axi4_reg_slice`) register slices for the five channels (AW, W, B, AR, R). Each channel is
an independent `pipe_reg_core` chain with its own `MODE_*` and the shared `N`, so the channels are registered independently as in AMD's
AXI Register Slice. Measured in simulation only (`ip_lib/axi_reg_slice/tb`, five channels at once, each against the `pipe_reg` model).

* Per channel: latency `N`, ready and throughput as `pipe_reg` for the mode (see `ip_lib/pipe_reg/DATASHEET.md`).
* Channels are not coupled: the slice never delays one channel for another, so any ordering rule between channels (write data
  before address, response after data) is the endpoints' and is kept exactly as it was without the slice.
* AXI4-Lite carries awaddr, awprot, wdata, wstrb, bresp, araddr, arprot, rdata, rresp. AXI4 adds id, len, size, burst, lock, cache, qos,
  wlast, rlast. **Not carried:** awregion, arregion, all user signals, AXI3 wid. A design that needs them cannot use this block.
* Reset `aresetn` active low, synchronous, as AXI requires; a master holds `valid` low during reset and for one clock after.
* This is a register slice, not an interconnect: no outstanding-transaction logic, no reordering, no ID handling.
* Against AMD's AXI Register Slice: the comparison (latency, bubbles, area, Fmax) is queued with the sweep; see
  `docs/partitioning_study.md` section 3.
