#!/usr/bin/env python3
"""Writes the timing XDC of every I/O-timing fixture (brief 20 part B) into xdc/<name>.xdc. One fault per fixture; the
data-sheet numbers are invented for the fixtures (round values typical of a 100 MHz converter), stated in each file."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
SYS = "create_clock -period 10.000 -name sys_clk [get_ports CLK100MHZ]\n"
SLOW = """# BTNC: a push button, asynchronous to sys_clk; it enters the two-flop synchroniser btn_sync (ASYNC_REG), so the pin
# has no timing relationship: a 0 ns placeholder delay (check_timing) and a false path
set_input_delay -clock sys_clk 0.000 [get_ports BTNC]
set_false_path -from [get_ports BTNC]
# LED[0] (read by a person) and UART_RXD_OUT (115200 baud): slow outputs, no timing relationship
set_output_delay -clock sys_clk 0.000 [get_ports {LED[0] UART_RXD_OUT}]
set_false_path -to [get_ports {LED[0] UART_RXD_OUT}]
"""
SLOW_PLACEHOLDER = """# BTNC (push button, into the two-flop synchroniser btn_sync), LED[0] and UART_RXD_OUT (115200 baud): asynchronous or
# slow, no timing relationship: 0 ns placeholder delays only (check_timing), no false path
set_input_delay -clock sys_clk 0.000 [get_ports BTNC]
set_output_delay -clock sys_clk 0.000 [get_ports {LED[0] UART_RXD_OUT}]
"""
SLOW_INVENTED = """# button and UART inputs
set_input_delay -clock sys_clk -max 2.000 [get_ports BTNC]
set_input_delay -clock sys_clk -min 0.000 [get_ports BTNC]
# LED and UART outputs
set_output_delay -clock sys_clk -max -1.500 [get_ports {LED[0] UART_RXD_OUT}]
set_output_delay -clock sys_clk -min -2.000 [get_ports {LED[0] UART_RXD_OUT}]
"""
ADC_HEAD = """# ADC (system-synchronous: the board's oscillator clocks the ADC and CLK100MHZ). Data sheet: tCO 1.0 ns min, 5.0 ns max;
# board: data trace 0.5 ns, clock traces to the ADC and the FPGA matched.
"""
ADC_OK = ADC_HEAD + """# -max = tCO_max + trace = 5.0 + 0.5 = 5.5 ns; -min = tCO_min + trace = 1.0 + 0.5 = 1.5 ns
set_input_delay -clock {clk} -max 5.500 [get_ports {{adc_d[*]}}]
set_input_delay -clock {clk} -min 1.500 [get_ports {{adc_d[*]}}]
"""
DAC_HEAD = """# DAC (system-synchronous: clocked by the board's oscillator, fanned out on the board). Data sheet: tSU 1.5 ns,
# tH 0.5 ns; board: data trace 0.4 ns, clock traces matched.
"""
DAC_OK = DAC_HEAD + """# -max = tSU + trace = 1.5 + 0.4 = 1.9 ns; -min = -tH + trace = -0.5 + 0.4 = -0.1 ns
set_output_delay -clock {clk} -max 1.900 [get_ports {{dac_d[*]}}]
set_output_delay -clock {clk} -min -0.100 [get_ports {{dac_d[*]}}]
"""
FWD = """create_clock -period 10.000 -name sys_clk [get_ports CLK100MHZ]
# dac_clk: sys_clk forwarded by the ODDR fwd_oddr with D1=0, D2=1, so it is sys_clk inverted
{gen}
# DAC data sheet: tSU 1.5 ns, tH 0.5 ns; board: dac_clk and dac_d traces matched (skew 0), so
# -max = tSU = 1.5 ns; -min = -tH = -0.5 ns, relative to the forwarded clock
set_output_delay -clock {clk} -max 1.500 [get_ports {{dac_d[*]}}]
set_output_delay -clock {clk} -min -0.500 [get_ports {{dac_d[*]}}]
"""
GEN_INV = "create_generated_clock -name dac_clk -source [get_pins fwd_oddr/C] -divide_by 1 -invert [get_ports dac_clk]"
GEN_EDGES = "create_generated_clock -name dac_clk -source [get_pins fwd_oddr/C] -edges {2 3 4} [get_ports dac_clk]"
DDR = """create_clock -period 10.000 -name rx_clk [get_ports rx_clk]
# source-synchronous DDR, centre-aligned: the source's data sheet gives the data valid 2.0 ns before and 2.0 ns after
# each rx_clk edge (dv_bre = dv_are = dv_bfe = dv_afe = 2.0 ns); traces matched. Per edge (AMD's centre-aligned DDR
# template): -max = T/2 - dv_before = 5.0 - 2.0 = 3.0 ns; -min = dv_after = 2.0 ns
set_input_delay -clock rx_clk -max 3.000 [get_ports {{rx_d[*]}}]
set_input_delay -clock rx_clk -min 2.000 [get_ports {{rx_d[*]}}]
set_input_delay -clock rx_clk -max 3.000 [get_ports {{rx_d[*]}}] -clock_fall{add}
set_input_delay -clock rx_clk -min 2.000 [get_ports {{rx_d[*]}}] -clock_fall{add}
# LED[0]: read by a person, no timing relationship
set_output_delay -clock rx_clk 0.000 [get_ports {{LED[0]}}]
set_false_path -to [get_ports {{LED[0]}}]
"""
EDGE = """create_clock -period 10.000 -name rx_clk [get_ports rx_clk]
create_clock -period 10.000 -name sys_clk [get_ports CLK100MHZ]
# rx_clk and sys_clk come from different oscillators (the IDELAY reference only uses sys_clk)
set_clock_groups -asynchronous -group [get_clocks rx_clk] -group [get_clocks -include_generated_clocks sys_clk]
# source-synchronous DDR, edge-aligned: data change with each rx_clk edge, skew 0.5 ns before and after
# (skew_bre = skew_are = skew_bfe = skew_afe = 0.5 ns); per edge: -max = skew_after = 0.5 ns; -min = -skew_before = -0.5 ns
set_input_delay -clock rx_clk -max 0.500 [get_ports {rx_d[*]}]
set_input_delay -clock rx_clk -min -0.500 [get_ports {rx_d[*]}]
set_input_delay -clock rx_clk -max 0.500 [get_ports {rx_d[*]}] -clock_fall -add_delay
set_input_delay -clock rx_clk -min -0.500 [get_ports {rx_d[*]}] -clock_fall -add_delay
# LED[0]: read by a person, no timing relationship
set_output_delay -clock rx_clk 0.000 [get_ports {LED[0]}]
set_false_path -to [get_ports {LED[0]}]
"""
MMCM = """create_clock -period 10.000 -name sys_clk [get_ports CLK100MHZ]
{vclk}# din: an external device clocked at 125 MHz by a clock from the same oscillator (phase-aligned on the board) that the
# FPGA does not receive; din is captured by clk125 (MMCM CLKOUT0, 1000 MHz VCO / 8). Device: tCO 0.5 ns min, 2.5 ns max;
# data trace 0.5 ns: -max = 2.5 + 0.5 = 3.0 ns; -min = 0.5 + 0.5 = 1.0 ns
set_input_delay -clock {clk} -max 3.000 [get_ports {{din[*]}}]
set_input_delay -clock {clk} -min 1.000 [get_ports {{din[*]}}]
# LED[0]: read by a person, no timing relationship
set_output_delay -clock sys_clk 0.000 [get_ports {{LED[0]}}]
set_false_path -to [get_ports {{LED[0]}}]
"""
VCLK125 = "# vclk125: the device's 125 MHz clock, not a design clock: a virtual clock at the period of clk125\ncreate_clock -period 8.000 -name vclk125\n"

def dac_v(period="10.000", order="before", extra=""):
    v = f"# dac_vclk: the copy of the board oscillator at the DAC, not a design clock: a virtual clock\ncreate_clock -period {period} -name dac_vclk\n"
    body = DAC_OK.format(clk="dac_vclk")
    return SYS + (v + extra + body if order == "before" else body + v + extra)

X = {
    "io_i1": SYS + ADC_OK.format(clk="sys_clk") + SLOW,
    "io_i2": SYS + ADC_HEAD + "# -max = tCO_max + trace = 5.0 + 0.5 = 5.5 ns\n"
             "set_input_delay -clock sys_clk -max 5.500 [get_ports {adc_d[*]}]\n" + SLOW,
    "io_i3": SYS + ADC_HEAD + "# fault: min and max swapped\nset_input_delay -clock sys_clk -max 1.500 [get_ports {adc_d[*]}]\n"
             "set_input_delay -clock sys_clk -min 5.500 [get_ports {adc_d[*]}]\n" + SLOW,
    "io_i3b": SYS + ADC_HEAD + "# -max = tCO_max + trace = 5.0 + 0.5 = 5.5 ns; fault: -min written as -(tCO_min + trace)\n"
              "set_input_delay -clock sys_clk -max 5.500 [get_ports {adc_d[*]}]\n"
              "set_input_delay -clock sys_clk -min -1.500 [get_ports {adc_d[*]}]\n" + SLOW,
    "io_i8": SYS + "# ADC data: placeholder (no data sheet numbers yet)\nset_input_delay -clock sys_clk 0.000 [get_ports {adc_d[*]}]\n" + SLOW,
    "io_i9": SYS + ADC_OK.format(clk="sys_clk") + SLOW_PLACEHOLDER,
    "io_i10": SYS + ADC_OK.format(clk="sys_clk") + SLOW_INVENTED,
    "io_v6": SYS + "# adc_osc: the ADC module's own 100 MHz oscillator (not the board's): a virtual clock\n"
             "create_clock -period 10.000 -name adc_osc\n" + ADC_OK.format(clk="adc_osc") + SLOW,
    "io_i4": SYS + DAC_OK.format(clk="sys_clk"),
    "io_i4b": SYS + DAC_HEAD + "# -max = tSU + trace = 1.9 ns; fault: -min written as +tH + trace = 0.5 + 0.4 = 0.9 ns\n"
              "set_output_delay -clock sys_clk -max 1.900 [get_ports {dac_d[*]}]\n"
              "set_output_delay -clock sys_clk -min 0.900 [get_ports {dac_d[*]}]\n",
    "io_v1": dac_v(),
    "io_v3": dac_v(extra="# board: the oscillator's copy reaches the DAC 0.3 ns after the FPGA's (source latency), and a 0.1 ns\n"
                         "# I/O-only uncertainty for the fan-out buffer's jitter\n"
                         "set_clock_latency -source 0.300 [get_clocks dac_vclk]\n"
                         "set_clock_uncertainty 0.100 [get_clocks dac_vclk]\n"),
    "io_v4": dac_v(order="after"),
    "io_v5": dac_v(period="12.000"),
    "io_i7": FWD.format(gen=GEN_INV, clk="dac_clk"),
    "io_i7c": FWD.format(gen=GEN_EDGES, clk="dac_clk"),
    "io_i7b": FWD.format(gen=GEN_INV, clk="sys_clk").replace("relative to the forwarded clock", "fault: relative to sys_clk"),
    "io_i5": DDR.format(add=" -add_delay"),
    "io_i5b": DDR.format(add=""),
    "io_i6": EDGE,
    "io_i6b": EDGE,
    "io_v2a": MMCM.format(vclk="", clk="sys_clk"),
    "io_v2": MMCM.format(vclk=VCLK125, clk="vclk125"),
}

if __name__ == "__main__":
    for n, t in X.items():
        (HERE / "xdc" / f"{n}.xdc").write_text(t)
    print(len(X), "files")
