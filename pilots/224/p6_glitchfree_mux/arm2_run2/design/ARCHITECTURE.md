# p6_clkmux architecture

Glitch-free clock mux (BUFGCTRL) between clock A (25 MHz clk) and clock B (156.25 MHz GT ref / B_DIV via BUFG_GT), a self-checking counter in the muxed domain, frequency gate, JTAG register bus.

## Block diagram

```text
 clk --> [rst_gen] --rst--> [jtag_bus (BSCANE2 USER4)] --h_*--> [clkmux_core]
 gtref_p/n -> IBUFDS_GTE4 -> BUFG_GT(div B_DIV-1) -> clk_b --+
 clk (A) ------------------------------------------------> BUFGCTRL -> clk_mux
 clkmux_core: regs(ID,BUILD,SCRATCH,SEL..SNAPSHOT), switch FSM, gate timer,
   freq counter (clk_mux) , muxed domain {bin counter, gray twin, checkers, err sat counter}
   CDC: active_sel, errs, snapshot, freq_count, rst via xpm_cdc
 led[0]=ACTIVE_SEL, led[1]=MUX_ERRS!=0, sfp_tx_disable=1
```

## Clock plan
- clk 25 MHz: register bus, clock A, gate timer (domain clk).
- clk_b_ref 156.25 MHz (GT ref, internal to the IBUFDS_GTE4/BUFG_GT): clock B, only feeds BUFGCTRL.
- clk_mux: BUFGCTRL output, asynchronous to clk (set_clock_groups). Crossings use xpm_cdc primitives.

## Pin list
clk C3 (clk_25); led[0] F8; led[1] E8; sfp_tx_disable Y10; gtref_p/gtref_n SFP+ MGTREFCLK0 (not in board resource list; pins to be resolved).

## Library entries considered
None: no standard IP block covers a clock mux or checker.
