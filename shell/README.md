# shell/: the on-board test shell

A small block that every design embeds, so that a script can test the design on the board over the Nexys A7's
USB-UART: no debugger, no one watching LEDs. The protocol is specified in [PROTOCOL.md](PROTOCOL.md).

| Path | What |
|---|---|
| `rtl/fpga_shell.sv` | Top of the shell: UART RX + TX + `shell_core` |
| `rtl/shell_core.sv` | Frame parser, fixed registers, the design's register window |
| `rtl/uart_rx.sv`, `rtl/uart_tx.sv` | 8N1 UART, `CLKS_PER_BIT` clocks a bit (868 = 115200 baud at 100 MHz) |
| `rtl/sync2.sv`, `rtl/reset_sync.sv` | Two-flop synchroniser and reset bridge, shared with the designs |
| `host/protocol.py` | Frame encode/decode and constants |
| `host/fpga_shell.py` | Host driver (pyserial) and command line: `python -m shell.host.fpga_shell --port /dev/ttyUSB1 id` |
| `model/shell_model.py` | Pure-Python model of the shell, byte in, byte out |
| `tests/` | cocotb tests of the RTL against the model (`test_shell_rtl.py`), and pure-Python tests of the protocol, model and driver |

## Embedding it

```systemverilog
fpga_shell #(.DESIGN_ID(32'h5431_4443), .BUILD_STAMP(BUILD_STAMP)) u_shell (
    .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
    .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
    .win_wdata(win_wdata), .win_rdata(win_rdata));   // register win_rdata: due one cycle after win_rd
```

The design decodes `win_addr` (shell address - 0x80) for its own registers. See
`designs/t1_dimmer_counter/rtl/dimmer_counter.sv` for an example.

## What the tests check

- the worked bytes in PROTOCOL.md, every fixed register, every error status and its counter;
- sync hunting through junk bytes, the 1 ms frame timeout (and that a shorter gap does not drop a frame), and a
  framing error abandoning a frame;
- 150 random requests (5 % with a corrupted checksum) against the model, at 8 clocks a bit;
- at the real parameters (868 clocks a bit, 1 ms timeout): every bit the shell sends lasts exactly 868 clocks,
  and the receiver accepts requests sent 2 % slow and 2 % fast.
