# Hough line accumulator architecture

## Block diagram

```text
 Host / USB-UART
       | UART_TXD_IN, UART_RXD_OUT
       v
 +----------------+
 |   fpga_shell   |<----> design register window
 +----------------+                 |
                                     v
                           +-------------------+
                           | Hough accumulator |
                           | 16 x 96 vote bins |
                           +-------------------+
                                     |
                                     +---- LED[0] busy; LED[15:1] low
```

## Clock plan

The sole clock domain is the Nexys A7 `CLK100MHZ` oscillator at 100 MHz. UART receive is asynchronous at the board input and is synchronized by the shell's `sync2` instance. The top-level synchronous active-high reset is derived from active-low `CPU_RESETN`.

## Pin list

- `CLK100MHZ`: board 100 MHz clock.
- `CPU_RESETN`: active-low CPU reset.
- `UART_TXD_IN`: USB-UART receive into the FPGA.
- `UART_RXD_OUT`: USB-UART transmit from the FPGA.
- `LED[15:0]`: board LED bus; bit 0 is busy and bits 15:1 are held low.

## Implementation plan

The datapath evaluates one projection direction at a time, then increments its selected distance bin. The 1536 11-bit counters form the accumulator. Reset returns control to idle; the CLEAR command initializes counts when the engine is idle. The design ID passed to the shell is `HOUG` (`32'h484F5547`); the build stamp is passed through the top-level parameter so the flow can supply its per-build value.
