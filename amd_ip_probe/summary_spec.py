"""The summary of brief 69 as data: for each datasheet point and each IP, what was measured, whether it is the same as our
house convention (docs/hwsw.md, "House conventions") or differs, and the probe lines that show it. summarise.py renders
the table from this and tests/test_records.py checks every `needle` against the committed records, so a cell cannot
say what its record does not.

A cell is (status, text, checks):
  status  "S" same as house, "D" differs, "N" not applicable, "P" not probed (the text says why)
  checks  a list of (probe, needle) or (probe, needle, False); the needle (whitespace collapsed) must occur in the probe's
          text in the IP's record, or, with False, must not occur
"""
from __future__ import annotations

IPS = ["gpio", "uartlite", "timer", "intc", "iic", "qspi", "dma", "smartconnect", "axi_interconnect"]
TITLES = {
    "gpio": "AXI GPIO 2.0", "uartlite": "AXI UART Lite 2.0", "timer": "AXI Timer 2.0", "intc": "AXI Interrupt Controller 4.1",
    "iic": "AXI IIC 2.1", "qspi": "AXI Quad SPI 3.2", "dma": "AXI DMA 7.1 (register port)", "smartconnect": "SmartConnect 1.0",
    "axi_interconnect": "AXI Interconnect 2.1",
}
# product guide held locally, as the edition printed on its title page (None: no guide for this IP is held, so no comparison)
GUIDES = {
    "gpio": "PG144 v2.0, January 30, 2026", "uartlite": "PG142 v2.0, April 5, 2017", "timer": "PG079 v2.0, August 15, 2025",
    "intc": "PG099 v4.1, July 15, 2021", "iic": None, "qspi": None, "dma": "PG021 v7.1, June 24, 2025",
    "smartconnect": "PG247 v1.0, June 24, 2026", "axi_interconnect": "PG059 v2.1, December 19, 2025",
}

# (key, row title, what the house convention says)
POINTS = [
    ("hole_read", "Read of a hole inside the IP's window", "SLVERR, data 0 (`unmapped: split`)"),
    ("hole_write", "Write to a hole", "OKAY, ignored (and recorded by the error capture)"),
    ("alias", "Address aliasing (partial decode)", "none: a hole is a hole; address bits [1:0] are not decoded"),
    ("reserved", "Reserved bits", "read 0, writes ignored"),
    ("read_effect", "Read side effects", "none; a pop or an acknowledge is a W1P write"),
    ("clear", "How a status bit is cleared", "write 1 to clear (W1C), or a W1P command"),
    ("race", "Hardware set against a software clear in the same clock", "the hardware set wins; the event is not lost"),
    ("wstrb", "Byte strobes (WSTRB)", "honoured bit by bit"),
    ("unaligned", "Address bits [1:0] of a word access", "not decoded: any byte address in the word reaches it"),
    ("outstanding", "Second address before the first response", "one transaction outstanding per direction"),
    ("alone", "AW without W, W without AW", "each channel accepted independently, in either order"),
    ("wide", "Values wider than 32 bits", "snapshot group: a W1P trigger copies the whole value"),
    ("reset", "Reset", "`aresetn`, synchronous, every register to its reset value"),
    ("irq", "Interrupt output", "level, from a register, one clock after the cause"),
    ("latency", "Latency, minimum, no back-pressure (AXI clocks)", "not a convention: for planning"),
    ("outside", "Address outside every slave (interconnects)", "DECERR from the interconnect (`axil_xbar`)"),
    ("passerr", "A slave's SLVERR through the interconnect", "passed to the master unchanged"),
    ("order", "Responses across two slaves, one unmapped (interconnects)", "in the order of the requests"),
]

C = {}


def cell(point, ip, status, text, *checks):
    C[(point, ip)] = (status, text, list(checks))


# ---- hole_read
cell("hole_read", "gpio", "D", "OKAY, data 0 (112 of 128 words)", ("window_read_scan", "zero_okay_words=112"))
cell("hole_read", "uartlite", "N", "no hole: four registers fill the 16-byte window", ("reset_values", "STAT=0x00000004"))
cell("hole_read", "timer", "D", "OKAY, 0 (words 0x0C and 0x1C)", ("reserved_words_write", "o0c=0x00000000"))
cell("hole_read", "intc", "D", "OKAY, 0 (126 of 128 words are 0 at reset; IVAR and IMR read 0 in basic mode)",
     ("window_read_scan_reset", "zero_okay_words=126"))
cell("hole_read", "iic", "D", "OKAY, 0 (every word of the window answers OKAY)", ("window_responses", "read_resp_mask=0x00000001"))
cell("hole_read", "qspi", "D", "OKAY, 0; SLVERR only for the empty receive FIFO (0x6C)",
     ("window_responses", "read_resp_mask=0x00000005"), ("window_reset_nonzero", "o6c=0x00000000/SLVERR"))
cell("hole_read", "dma", "D", "OKAY, 0 (every word of the 1 KB window answers OKAY)", ("window_responses", "read_resp_mask=0x00000001"))
cell("hole_read", "smartconnect", "N", "a slave's hole is the slave's answer (OKAY, 0)", ("hole_inside_slave_through_ic", "read_GPIO+0x10=0x00000000/OKAY"))
cell("hole_read", "axi_interconnect", "N", "a slave's hole is the slave's answer (OKAY, 0)", ("hole_inside_slave_through_ic", "read_GPIO+0x10=0x00000000/OKAY"))
# ---- hole_write
cell("hole_write", "gpio", "S", "OKAY, ignored (apart from the aliases)", ("window_write_scan", "baseline=all_zero"), ("window_write_scan", "SLVERR", False))
cell("hole_write", "uartlite", "S", "OKAY, ignored (writes to the read-only FIFO and status words)", ("write_stat_ro", "resp=OKAY"), ("write_rxf_ro", "resp=OKAY"))
cell("hole_write", "timer", "S", "OKAY, ignored (words 0x0C and 0x1C)", ("reserved_words_write", "write_0x0C=OKAY write_0x1C=OKAY"))
cell("hole_write", "intc", "S", "OKAY, ignored", ("window_write_scan", "changed_or_non_okay:"), ("window_write_scan", "->", False))
cell("hole_write", "iic", "S", "OKAY, ignored; SLVERR only for 0xFFFFFFFF written to the soft-reset word (0x40; the documented value was not tried)",
     ("window_responses", "write_resp_mask=0x00000005"), ("window_responses", "o40=SLVERR"))
cell("hole_write", "qspi", "S", "OKAY, ignored; SLVERR only for 0xFFFFFFFF written to the soft-reset word (0x40; the documented value was not tried)",
     ("window_responses", "write_resp_mask=0x00000005"), ("window_responses", "o40=SLVERR"))
cell("hole_write", "dma", "S", "OKAY, ignored", ("window_responses", "write_resp_mask=0x00000001"))
cell("hole_write", "smartconnect", "N", "a slave's own answer", ("map_edges_write", "0x00002ffc=OKAY"))
cell("hole_write", "axi_interconnect", "N", "a slave's own answer", ("map_edges_write", "0x00002ffc=OKAY"))
# ---- alias
cell("alias", "gpio", "D", "yes: in 0x100-0x1FF address bits [7:6] are ignored, so GIER, ISR and IER repeat at +0x40, +0x80, +0xC0",
     ("window_write_scan", "o15c->GIER"), ("window_write_scan", "o1e0->ISR"), ("window_read_scan", "o19c=0x80000000/OKAY"))
cell("alias", "uartlite", "N", "no hole to alias; the byte offsets alias the word (see address bits [1:0])", ("unaligned_rx_read", "read_0x1=0x0000005a"))
cell("alias", "timer", "S", "none in the 32-byte window", ("reserved_words_write", "after: o00=0x00000000"))
cell("alias", "intc", "S", "none in the 512-byte window", ("window_write_scan", "->", False), ("window_read_scan_nonzero", "zero_okay_words=123"))
cell("alias", "iic", "D", "yes: a write at 0x180-0x1FF acts on 0x100-0x17F (address bit 7 ignored above 0x100)",
     ("window_write_links", "o1a0->o120"), ("window_write_links", "o1a4->o124"))
cell("alias", "qspi", "S", "none in the 128-byte window", ("window_write_links", "other_word_changed: chk=0x000"))
cell("alias", "dma", "D", "yes: the 128-byte register block repeats eight times in the 1 KB window (address bits [9:7] ignored)",
     ("window_write_links", "o80->o0"), ("window_write_links", "o398->o18"))
cell("alias", "smartconnect", "S", "the address reaches the slave unmodified: the slave's own alias appears through it", ("alias_through_ic", "read_+0x15C=0x80000000"))
cell("alias", "axi_interconnect", "S", "the address reaches the slave unmodified: the slave's own alias appears through it", ("alias_through_ic", "read_+0x15C=0x80000000"))
# ---- reserved
cell("reserved", "gpio", "S", "read 0; writes ignored (GIER bit 31 only, IER 2 bits, TRI to the channel width)",
     ("reserved_bits", "GIER=0x80000000 IER=0x00000003"), ("reserved_bits", "TRI1=0x000000ff"))
cell("reserved", "uartlite", "S", "write-only CTRL: only the interrupt enable bit shows in STAT", ("ctrl_ones_then_zero", "stat_after_ones=0x00000014"))
cell("reserved", "timer", "S", "TCSR0 bits 31:12 never read back set when written", ("tcsr0_single_bit_writes", "bits31_12_that_read_back_nonzero=0"))
cell("reserved", "intc", "S", "IER 4 bits, MER 2 bits, the rest read 0", ("reserved_bits", "IER=0x0000000f MER=0x00000003"))
cell("reserved", "iic", "S", "the interrupt enable word stores 8 bits", ("window_write_readback", "o28=0x000000ff"))
cell("reserved", "qspi", "S", "the interrupt enable word stores 9 bits", ("window_write_readback", "o28=0x000001ff"))
cell("reserved", "dma", "P", "write-all-ones read-back is in the record; reserved bits of the control words were not probed bit by bit", ("window_write_readback", "o0=0xffff701e"))
# ---- read_effect
cell("read_effect", "gpio", "S", "none: ISR and data reads repeat", ("read_side_effect", "read2=0x00000001"))
cell("read_effect", "uartlite", "D", "the RX FIFO read pops it; a STAT read clears the overrun and frame error bits (parity not exercised: the bench has none)",
     ("rx_pop_on_read", "stat_after_read=0x00000004"), ("frame_error", "stat_again=0x00000004"), ("rx_overrun", "stat_again=0x00000007"))
cell("read_effect", "timer", "P", "not isolated: the auto-reload bench re-sets T0INT every 64 clocks, so a surviving flag does not prove a read leaves it alone", ("irq_level", "after_read=1"))
cell("read_effect", "intc", "S", "none seen: IVR reads the same twice", ("ivr", "inputs_0_and_3=0x00000000 again=0x00000000"))
cell("read_effect", "iic", "P", "no word read differently twice at reset, but the receive FIFO pop needs a transfer", ("window_responses", "volatile_reads: chk"))
cell("read_effect", "qspi", "P", "no word read differently twice at reset, but the receive FIFO pop needs a transfer", ("window_responses", "volatile_reads: chk"))
cell("read_effect", "dma", "P", "no word read differently twice at reset (weak: a status or FIFO effect needs a transfer)", ("window_responses", "volatile_reads: chk"))
# ---- clear
cell("clear", "gpio", "D", "toggle on write: writing 1 flips the ISR bit, so 1 to a clear bit sets it", ("isr_write1_again", "isr=0x00000001"), ("isr_write1_to_set_bit", "isr=0x00000000"))
cell("clear", "uartlite", "D", "clear on read of STAT (error bits); FIFO resets are write-only CTRL bits", ("frame_error", "stat=0x00000044"), ("ctrl_reset_rx", "stat_after_rst_rx=0x00000004"))
cell("clear", "timer", "S", "W1C: write 1 clears T0INT, write 0 changes nothing", ("t0int_write1_clears", "TCSR0=0x000000d0"), ("t0int_write0_no_change", "TCSR0=0x000001d0"))
cell("clear", "intc", "D", "a separate write-1-to-acknowledge register (IAR); a level input stays latched after it drops, until acknowledged",
     ("iar_clears", "after_IAR_1=0x00000002 IAR_0_nochange=0x00000002"), ("level_input_released", "ISR=0x00000004"), ("level_input_released_then_ack", "ISR=0x00000000"))
for ip in ("iic", "qspi", "dma"):
    cell("clear", ip, "P", "needs a transfer or an error to set a status bit", ("window_responses", "hangs=0"))
# ---- race
cell("race", "gpio", "S", "the event is kept: the estimate of the coincident clock (-9, from two measured delays) equals the first clock giving 1; exact to +-1 clock",
     ("race_scenarioA_clear_vs_event", "rel-10=0x00000000 rel-9=0x00000001"), ("irq_delays", "coincident_rel=-9"))
cell("race", "timer", "D", "consistent with the clear winning (event lost) at the coincident clock, if the estimate is exact to +-1 clock; the source shows a flag flop whose reset beats its set",
     ("race_clear_vs_rollover", "D52= set D53=clear"), ("race_clear_irq_fall_lag", "coincident_D=53"))
cell("race", "intc", "D", "the acknowledge wins at the estimated coincident clock (-3) and the next one (-2); edges sampled at -1 or later are kept (the source shows a registered acknowledge pulse with priority over the set); estimate, exact to +-1 clock",
     ("race_iar_clear_vs_edge", "rel-3=lost rel-2=lost rel-1=kept"), ("irq_lags", "coincident_rel=-3"))
cell("race", "uartlite", "P", "a received character cannot be timed against a status read from outside")
for ip in ("iic", "qspi", "dma"):
    cell("race", ip, "P", "needs a transfer to create the hardware event")
# ---- wstrb
cell("wstrb", "gpio", "D", "ignored (a write with strobe 0000 takes effect)", ("wstrb_TRI1", "write_0xFF_strb0000=0x000000ff"))
cell("wstrb", "uartlite", "D", "ignored (a write with strobe 0000 transmits)", ("wstrb_zero_tx_data", "rx=0x00000055"))
cell("wstrb", "timer", "D", "ignored", ("wstrb_TLR0", "strb0000=0xffffffff"))
cell("wstrb", "intc", "D", "ignored", ("wstrb_IER", "write_0xF_strb0000=0x0000000f"))
cell("wstrb", "iic", "D", "ignored", ("wstrb", "write_3_strb0000=0x00000003"))
cell("wstrb", "qspi", "D", "ignored", ("wstrb", "write_3_strb0000=0x00000003"))
cell("wstrb", "dma", "D", "the lite port has no WSTRB input", ("wstrb", "no_wstrb_port=1"))
cell("wstrb", "smartconnect", "P", "not observable: both slaves ignore WSTRB", ("wstrb", "not_observable=1"))
cell("wstrb", "axi_interconnect", "P", "not observable: both slaves ignore WSTRB", ("wstrb", "not_observable=1"))
# ---- unaligned
cell("unaligned", "gpio", "S", "bits [1:0] ignored, writes and reads", ("unaligned", "read_0x005=0x00000055 read_0x007=0x00000055"))
cell("unaligned", "uartlite", "S", "bits [1:0] ignored (a read at byte 1 of the RX FIFO word pops it)", ("unaligned_rx_read", "read_0x1=0x0000005a stat_after=0x00000004"), ("unaligned_tx_write", "rx=0x00000044"))
cell("unaligned", "timer", "S", "bits [1:0] ignored", ("unaligned", "read_0x07=0x12345678"))
cell("unaligned", "intc", "S", "bits [1:0] ignored", ("unaligned", "read_0x0B=0x00000003"))
cell("unaligned", "iic", "S", "bits [1:0] ignored", ("unaligned_read", "read_wa+3=0x00000003"), ("unaligned_write", "write_at_wa+3_reads_wa=0x00000003"))
cell("unaligned", "qspi", "S", "bits [1:0] ignored", ("unaligned_read", "read_wa+3=0x00000003"), ("unaligned_write", "write_at_wa+3_reads_wa=0x00000003"))
cell("unaligned", "dma", "D", "writes ignore bits [1:0]; a read at +1, +2 or +3 returns 0", ("unaligned_write", "write_at_wa+1_reads_wa=0x00000003"), ("unaligned_read", "read_wa+1=0x00000000 read_wa+2=0x00000000 read_wa+3=0x00000000"))
cell("unaligned", "smartconnect", "S", "bits [1:0] reach the slave, which ignores them", ("unaligned_read", "read_wa+3=0x00000003"))
cell("unaligned", "axi_interconnect", "S", "bits [1:0] reach the slave, which ignores them", ("unaligned_read", "read_wa+3=0x00000003"))
# ---- outstanding
for ip in ("gpio", "uartlite", "timer", "intc", "iic", "qspi", "smartconnect", "axi_interconnect"):
    cell("outstanding", ip, "S", "one address (and one data word) accepted before the first response, then it waits (a second write not shown to land for IIC, Quad SPI and the interconnects)",
         ("outstanding_rd", "ar_accepted_while_rready_low=1"), ("outstanding_wr", "aw_accepted_while_bready_low=1"))
cell("outstanding", "dma", "D", "reads: one. Writes: a second AW and W are accepted while the first B waits, and only one B comes back for the two writes",
     ("outstanding_rd", "ar_accepted_while_rready_low=1"), ("outstanding_wr_pair_same_register", "aw_accepted_while_bready_low=2 w_accepted_while_bready_low=2 b_total=1"),
     ("after_missing_b", "ordinary_write: resp=OKAY hung=0"))
# ---- alone
for ip in ("gpio", "uartlite", "timer", "intc", "iic", "qspi", "dma", "smartconnect"):
    cell("alone", ip, "D", "waits for both: AW alone or W alone is not accepted in 20 clocks", ("aw_alone", "aw_accepted=0"), ("w_alone", "w_accepted=0"))
cell("alone", "axi_interconnect", "D", "accepts AW alone; W alone is not accepted until AW is present", ("aw_alone", "aw_accepted=1"), ("w_alone", "w_accepted=0"))
# ---- wide
cell("wide", "timer", "D", "no snapshot: the 64-bit cascade reads as TCR0 and TCR1 separately and a read across the carry tears (4 of 12 low-first trials and 7 of 12 high-first trials showed an out-of-order value)",
     ("cascade_read_tear", "non_monotonic_samples=4"), ("cascade_read_tear_hi_first", "non_monotonic_samples=7"))
# ---- reset
cell("reset", "gpio", "S", "IER, GIER, TRI1, DATA1 back to reset (TRI2, DATA2 never written)", ("reset_after_writes", "GIER=0x00000000 ISR=0x00000000 IER=0x00000000"))
cell("reset", "uartlite", "S", "both FIFOs empty (STAT back to its reset value)", ("reset_after_activity", "stat=0x00000004 irq=0"))
cell("reset", "timer", "S", "TCSR and TLR back to 0 (no counter running)", ("reset_after_writes", "o10=0x00000000 o14=0x00000000 o18=0x00000000"))
cell("reset", "intc", "S", "IER and MER back to reset after writes (IVR and ILR read all ones; ISR and IVAR not exercised)", ("reset_after_writes", "IVR=0xffffffff MER=0x00000000"))
cell("reset", "smartconnect", "S", "the slave behind it resets with it", ("reset_through_ic", "GPIO_TRI_after_reset=0x000000f0"))
cell("reset", "axi_interconnect", "S", "the slave behind it resets with it", ("reset_through_ic", "GPIO_TRI_after_reset=0x000000f0"))
for ip in ("iic", "qspi", "dma"):
    cell("reset", ip, "P", "each write in the scan was followed by a reset; the baseline words came back, not checked word by word", ("window_responses", "hangs=0"))
# ---- irq
cell("irq", "gpio", "S", "level, from registers; cleared through ISR; 9 clocks from an input edge (information, not one clock)",
     ("irq_level_hold", "after_20_clocks=1 after_isr_read=1"), ("irq_delays", "pin_edge_to_irq=9"))
cell("irq", "uartlite", "D", "two one-clock pulses per character, not a level (the guide says RX non-empty and TX empty; which pulse is which was not timed)",
     ("irq_after_char", "rises=2 high_clocks=2"), ("irq_with_rx_data_waiting", "rises=0"))
cell("irq", "timer", "S", "level, from a flag register (the guide agrees)", ("irq_level", "irq_with_T0INT=1 after_read=1"))
cell("irq", "intc", "S", "level, from the latched ISR, IER and MER; nothing out while MER is 0 (ISR was also 0 then)", ("irq_mer_off", "irq=0"), ("irq_mer_on", "irq=1 after_read=1 20_later=1"))
for ip in ("iic", "qspi", "dma"):
    cell("irq", ip, "P", "needs a transfer or an error to raise it", ("window_responses", "hangs=0"))
# ---- latency (information only)
LAT = {"gpio": (7, 7), "uartlite": (5, 5), "timer": (5, 5), "intc": (6, 6), "iic": (6, 6), "qspi": (7, 7), "dma": (7, 6),
       "smartconnect": (10, 10), "axi_interconnect": (9, 10)}
for ip, (w, r) in LAT.items():
    cell("latency", ip, "N", "write %d, read %d" % (w, r), ("latency", "write=%d" % w), ("latency", "read=%d" % r))
# ---- interconnect rows
cell("outside", "smartconnect", "S", "DECERR for read and write at 0x0, 0xFFC, 0x3000, 0x8000, 0x80000000 and 0xFFFFFFFC; read data 0xDEC0DEE3; the write data is consumed",
     ("map_edges_read", "0x80000000=0xdec0dee3/DECERR"), ("map_edges_write", "0xfffffffc=DECERR"), ("map_edges_write", "GPIO_DATA_after=0x000000a5"))
cell("outside", "axi_interconnect", "S", "DECERR for read and write at the same addresses; read data 0xDEC0DE1C; the write data is consumed",
     ("map_edges_read", "0x80000000=0xdec0de1c/DECERR"), ("map_edges_write", "0xfffffffc=DECERR"), ("map_edges_write", "GPIO_DATA_after=0x000000a5"))
for ip in ("smartconnect", "axi_interconnect"):
    cell("passerr", ip, "S", "the UART Lite's SLVERR for an empty receive FIFO reaches the master as SLVERR", ("slave_error_passthrough", "uart_rx_empty_read=SLVERR"))
cell("order", "smartconnect", "S", "responses DECERR then OKAY; the interconnect took one request at a time, so ordering was not exercised",
     ("outstanding_rd_unmapped_then_mapped", "first=0xdec0dee3/DECERR second=0x000000a5/OKAY"), ("outstanding_wr_unmapped_then_mapped", "b0=DECERR b1=OKAY"))
cell("order", "axi_interconnect", "S", "responses DECERR then OKAY; the interconnect took one request at a time, so ordering was not exercised",
     ("outstanding_rd_unmapped_then_mapped", "first=0xdec0de1c/DECERR second=0x000000a5/OKAY"), ("outstanding_wr_unmapped_then_mapped", "b0=DECERR b1=OKAY"))

# ---- facts for the agent's note (flow/amd_ip_notes.py): IP catalogue name -> the differences that bite, checked above
NOTES = {
    "axi_gpio": ["holes read 0 and answer OKAY (house: SLVERR)", "registers repeat at +0x40, +0x80, +0xC0 in the upper half of the window (GIER, ISR, IER)",
                 "the ISR toggles on write: writing 1 to a clear bit sets it", "byte strobes are ignored", "AW and W must both be present"],
    "axi_uartlite": ["a read of the RX FIFO pops it, and a read at byte offset 1-3 of that word pops it too", "a STAT read clears the error bits",
                     "a read of an empty RX FIFO and a write to a full TX FIFO answer SLVERR", "the interrupt is a one-clock pulse, not a level", "byte strobes are ignored"],
    "axi_timer": ["holes answer OKAY with 0", "T0INT/T1INT are W1C, but a clear in the same clock as the rollover wins and the event is lost",
                  "the 64-bit cascade has no snapshot: read TCR1, TCR0, TCR1 again until TCR1 repeats", "byte strobes are ignored"],
    "axi_intc": ["IAR is a separate write-1-to-acknowledge register; an edge arriving within about two clocks of the acknowledge is lost",
                 "a level input stays latched in ISR after it drops, until acknowledged", "IVAR and IMR read 0 in basic mode", "byte strobes are ignored"],
    "axi_iic": ["a write at 0x180-0x1FF acts on 0x100-0x17F", "0xFFFFFFFF written to the soft-reset word (0x40) answers SLVERR (the documented value was not tried)", "byte strobes are ignored"],
    "axi_quad_spi": ["a read of the empty RX FIFO word (0x6C) answers SLVERR", "0xFFFFFFFF written to the soft-reset word (0x40) answers SLVERR (the documented value was not tried)", "byte strobes are ignored"],
    "axi_dma": ["the 128-byte register block repeats eight times in the 1 KB window", "no WSTRB input", "a read at byte offset 1-3 returns 0 while a write at those offsets writes the word",
                "a second write accepted while the first B waits gets no B of its own: issue one write at a time", "AW and W must both be present"],
    "smartconnect": ["DECERR with read data 0xDEC0DEE3 outside every slave; the write data is consumed", "a slave's SLVERR passes through", "waits for both AW and W"],
    "axi_interconnect": ["DECERR with read data 0xDEC0DE1C outside every slave; the write data is consumed", "a slave's SLVERR passes through", "accepts AW alone"],
}
IP_NAME = {"gpio": "axi_gpio", "uartlite": "axi_uartlite", "timer": "axi_timer", "intc": "axi_intc", "iic": "axi_iic", "qspi": "axi_quad_spi",
           "dma": "axi_dma", "smartconnect": "smartconnect", "axi_interconnect": "axi_interconnect"}
