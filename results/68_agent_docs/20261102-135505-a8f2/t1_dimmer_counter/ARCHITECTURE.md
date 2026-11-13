# T1 LED dimmer and push-button counter — implementation plan

Target: Nexys A7-100T (`xc7a100tcsg324-1`), top module `t1_led_dimmer_counter`.

## Block diagram

```text
                     +------------------------------+
 clk100 (100 MHz) -->| reset synchronizer / sys_clk |
 cpu_resetn -------->|                              |
                     +---------------+--------------+
                                     |
             +-----------------------+------------------------+
             |                       |                        |
   BTNU/BTND/BTNC              SW[7:0]                  USB-UART RX
 synchronizers + debounce         |                         |
             |                     |                   +-----v------+
             +----> counter /      +--> brightness      | fpga_shell|
                    press counts       selection       | UART regs |
                         |                 |             +-----+-----+
                         |                 |                   |
               +---------+-----------------+-------------------+
               |                           |                   |
        PWM-gated LED outputs       seven-segment scan   register window
        LED[15:0]                   AN[7:0], seg, dp      COUNTER through
                                                          DESIGN_ID
```

## Clock and reset plan

Use the board's 100 MHz oscillator on `clk` as the sole clock domain; no derived clocks. UART uses the shell's 868-clock bit divider (115200 baud) and 100,000-cycle frame timeout. Counter/debounce, PWM, and digit-scan timing are clock-enable/counter based on this clock. The CPU reset input `cpu_resetn` is active low and asynchronously asserts reset; synchronize its deassertion to `clk`, then drive the design reset and the shell's synchronous active-high `rst` input. The scan design uses the specified 100,000-cycle digit interval; the structured spec's separate resolution note also records a proposed 131,072-cycle interval, which should be reconciled during RTL/verification planning.

## Pin list

Pin assignments and LVCMOS33 I/O standards are generated in `design.xdc` from the Nexys A7 master constraints; no pin numbers are authored here.

| Design port | Board resource | Direction | Use |
|---|---|---:|---|
| `clk` | `clk100` | input | 100 MHz system clock |
| `cpu_resetn` | `cpu_resetn` | input | Active-low CPU reset |
| `btn_up` | `btnu` | input | Increment button |
| `btn_down` | `btnd` | input | Decrement button |
| `btn_center` | `btnc` | input | Clear button |
| `switches[7:0]` | `sw[7:0]` | input | Manual brightness source |
| `leds[15:0]` | `led[15:0]` | output | PWM-gated counter bits |
| `seg[6:0]` | `seg[6:0]` | output | Active-low a–g segments |
| `dp` | `dp` | output | Decimal point, inactive high |
| `an[7:0]` | `an[7:0]` | output | Active-low digit enables |
| `uart_rxd` | `uart_rx` | input | USB-UART receive into FPGA |
| `uart_txd` | `uart_tx` | output | USB-UART transmit from FPGA |
