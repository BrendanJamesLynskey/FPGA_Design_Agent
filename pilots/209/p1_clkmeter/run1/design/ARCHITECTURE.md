# P1 clock frequency meter: architecture

Measures the 25 MHz clk_c3 (pin C3) against the 156.25 MHz SFP+ GT reference clock (MGTREFCLK0, IBUFDS_GTE4 + BUFG_GT, no GT channel). Host access is the JTAG register bus `jtag_bus` (data/jtag_bus.sv, unchanged, USER4) in the clk_c3 domain.

## Block diagram

```text
 JTAG --> jtag_bus (clk_c3) --h_we/h_re/h_addr/h_wdata/h_rdata--> freq_meter_core
 clk_c3 (C3) --BUFG-----------------------------------------------> core (reg port, edge counter, LED0 blink)
 mgtrefclk0_p/n --IBUFDS_GTE4--BUFG_GT--> clk_ref --> core (gate FSM, LED1 blink)
 rst (jtag_bus) --xpm_cdc_async_rst--> rst_ref (clk_ref)

 core internals:
  regs(c3) --START+GATE_LEN (xpm_cdc_handshake)--> gate FSM(ref)
  gate FSM(ref) --gate_open (xpm_cdc_single)--> edge counter(c3)
  gate FSM(ref) --done + GATE_ACTUAL (xpm_cdc_handshake)--> regs(c3)
  LED_EN(c3) --xpm_cdc_single--> LED1 gating(ref)
 sfp_tx_disable = 1 constant
```

## Clock plan
- clk_c3, 25 MHz: register port, jtag_bus, COUNT counter, LED[0] blink (12.5M half period).
- clk_ref, 156.25 MHz: gate counter (GATE_LEN cycles), LED[1] blink (78.125M half period).
- All crossings use XPM CDC primitives listed in architecture.yaml. COUNT is captured in clk_c3 after gate close is seen, and DONE is raised only after COUNT and GATE_ACTUAL are stable (result handshake). Error is at most 1 edge.
- Reset: rst active high, synchronous in clk_c3, synchronised into clk_ref with xpm_cdc_async_rst.

## Register map (byte offsets)
0x000 ID (0x20910001 per REQ-01), 0x004 BUILD (USR_ACCESSE2), 0x008 SCRATCH, 0x010 GATE_LEN, 0x014 CTRL (START, LED_EN), 0x018 STATUS (BUSY, DONE), 0x01C COUNT, 0x020 GATE_ACTUAL, 0x024 MEAS_DONE. Unmapped reads 0.

Spec inconsistencies for the owner: DESIGN_ID 546373633 = 0x20910001, consistent. GATE_LEN reset is listed as 156280480 in the map but 156250000 in the text, parameters and REQ-04; plan uses 156250000.

## Pin list
clk_c3 (C3), mgtrefclk0_p/n (SFP+ quad GT ref), led[1:0], sfp_tx_disable. Pins come from the board master XDC via board_constraints.

## Library entries considered
ip_lookup not needed: no CRC/filter/table function; XPM macros used for CDC.

## Resource prediction
jtag_bus ~90 LUT / 413 FF; core adds ~300-500 LUT, ~500-900 FF (32-bit counters, LED counters, CDC handshakes). Total LUT 350-900, FF 800-1600, no BRAM or DSP.
