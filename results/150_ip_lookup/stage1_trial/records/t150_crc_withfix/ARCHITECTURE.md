# CRC-32 checker (t150_crc_withfix), architecture

Status: proposed for owner approval. ARCHITECTURE.md and architecture.yaml are frozen once approved; no RTL before that.

## Summary

Board top `crc32_checker_top` on the Nexys A7-100T. The host sends 32-bit words over the UART test shell
(`fpga_shell`, 115200 8N1). `crc32_engine` folds one word per clock into a 32-bit reflected CRC-32 register
(polynomial 0xEDB88320, init 0xFFFFFFFF, readback = state XOR 0xFFFFFFFF). The 16 LEDs show readback bits 15:0.
The design ID is "CRC3" (0x43524333).

## Block diagram

```text
 host (USB-UART)
      |  UART_TXD_IN / UART_RXD_OUT
      v
 +----------------------------- crc32_checker_top ------------------------------+
 |                                                                              |
 |  CPU_RESETN --> reset_sync (xpm_cdc_async_rst) --> rst (active high)         |
 |                                                       |                      |
 |  CLK100MHZ ----------------------------------+        v                      |
 |                                              |   +-----------+               |
 |   UART_TXD_IN ----------------------------> +-->| fpga_shell|               |
 |   UART_RXD_OUT <----------------------------+---|  (test    |               |
 |                                                  |   shell)  |               |
 |                                                  +-----+-----+               |
 |                                  win_addr/win_wr/win_rd/win_wdata/win_rdata  |
 |                                                  v                           |
 |                                           +-------------+                    |
 |                                           | crc32_engine|--> LED[15:0]       |
 |                                           | CRC datapath|                    |
 |                                           | reg decode  |                    |
 |                                           +-------------+                    |
 +------------------------------------------------------------------------------+
```

## Blocks

| Block | Function |
|---|---|
| crc32_checker_top | Board top: reset synchroniser, fpga_shell, crc32_engine, LED pins |
| fpga_shell | Provided test shell (protocol in shell/PROTOCOL.md). Design window at shell ADDR 0x80-0xFF, `win_addr` = ADDR - 0x80 |
| crc32_engine | CRC-32 datapath (32 bits per clock), register decode, readback, LED output |
| reset_sync | xpm_cdc_async_rst, two flops, asynchronous assert and synchronous release |

Register map inside the window (design offsets, `win_addr`):

| Offset | Name | Access | Reset | Function |
|---|---|---|---|---|
| 0x00 | ID | RO | 0x43524333 | ASCII "CRC3" |
| 0x04 | DATA | WO | 0x00000000 | write folds the word into crc_state; reads return 0 |
| 0x08 | CRC | RO | 0x00000000 | crc_state XOR 0xFFFFFFFF |
| 0x0C | CTRL | WO | 0x00000000 | bit 0 CLEAR sets crc_state to 0xFFFFFFFF, self-clears; bits 31:1 ignored |

Priority: a CTRL clear and a DATA write in the same clock: clear wins, the word is discarded (spec default).

## Reset

- `CPU_RESETN` (active low button, pin C12, asynchronous to clk) enters once through `xpm_cdc_async_rst` with
  RST_ACTIVE_HIGH = 1, fed by `~CPU_RESETN`. Inside the design reset is active high only.
- The synchronised reset drives `fpga_shell.rst` and the control registers of `crc32_engine`
  (crc_state reset to 0xFFFFFFFF, which is a control-style state). No asynchronous reset in datapath logic.
- Synchronous reset throughout (UG949 default). The DSP/BRAM rule does not apply: the design uses neither.

## Clock plan

| Clock | Pin | Frequency | Domains |
|---|---|---|---|
| clk (CLK100MHZ) | oscillator | 100 MHz (10 ns) | single domain: fpga_shell, crc32_engine, reset_sync |

There is one clock domain and no clock-domain crossing. The CPU reset is the only asynchronous input, handled by the
reset synchroniser above. No derived or gated clocks.

## Pin list

Pins are written only by `board_constraints` from the master XDC. No pin numbers are typed here.

| Top port | Direction | Width | Role |
|---|---|---|---|
| CLK100MHZ | in | 1 | 100 MHz oscillator (clk) |
| CPU_RESETN | in | 1 | reset button, active low (spec rst_n) |
| LED | out | 16 | LED[15:0] = spec leds[15:0], active high |
| UART_TXD_IN | in | 1 | FPGA receive from host (fpga_shell uart_rx) |
| UART_RXD_OUT | out | 1 | FPGA transmit to host (fpga_shell uart_tx) |

I/O timing: CPU_RESETN and UART_TXD_IN (inputs) and LED and UART_RXD_OUT (outputs) have no timing relationship
to clk at the board pins. They are cut with set_false_path in design.xdc. No delay is invented on the board ports
(FDA-CON-11 rejects invented delays on asynchronous or slow ports).

The spec also lists bus_wr_en, bus_addr[7:0], bus_wdata[31:0], bus_rd_en, bus_rdata[31:0] as ports. They are the
internal window between the shell and the engine (win_* in fpga_shell, bus_* in crc32_engine); they are not board pins.
See open questions.

## Predicted resources

| Resource | Predicted | Basis |
|---|---|---|
| LUT | 150-600 | CRC XOR tree for 32 bits per clock, register decode, LED output, plus fpga_shell (UART, frame parser, counters) |
| FF | 150-500 | crc_state 32, decode and LED registers, plus fpga_shell frame and response buffers |
| BRAM tiles | 0 | no memory |
| DSP | 0 | no multiply |

The spec's 200 LUT / 100 FF estimate covers only the CRC block; the shell adds its own cost.

## Library entries considered

ip_lookup was run with "CRC-32 reflected 32-bit word per clock" on xc7a100tcsg324-1 at 10 ns:

- `crc32_step`, variant `word` (95 LUT, 33 FF, 0 BRAM, 0 DSP measured): NOT taken. Its result register is one
  clock after in_valid (latency 1), so crc_state would lag the DATA write by one clock; spec REQ-03 and REQ-10
  require the update on the accepting edge and a clear to win over a same-clock write. Its Fmax is unmeasured.
- `crc32_step`, variant `byte` (96 LUT, 92 FF, Fmax 289.9 MHz): NOT taken. Latency 4 and II 4 cannot take one word
  per clock, which the spec requires.
- `frame_crc`: NOT taken. It is a video frame CRC with pixel count and sum; the spec needs a word-serial register
  block.

Decision: crc32_engine is written fresh. It is a small XOR network (one 32-bit word per clock, combinational into
crc_state) with the clear priority the spec defines.

## Open questions for the owner

1. The spec lists bus_* as top-level ports, but the board top must also own the shell. Confirm whether the top keeps
   bus_* as internal test-visible ports (no pins) or whether they live only in crc32_engine.
2. The spec's clk and rst_n are mapped to the master XDC names CLK100MHZ and CPU_RESETN (pin C12, not BTNC).
3. design.xdc is written (board pins, clock, and the false paths above). check_constraints cannot yet run its
   source-file check because rtl/ holds no RTL; that is expected before the RTL stage.
