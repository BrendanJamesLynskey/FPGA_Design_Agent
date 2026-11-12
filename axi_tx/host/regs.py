"""Register map of the brief 59A transactor, as the host sees it (window offsets: shell address = 0x80 + offset).

The RTL is the source (axi_tx/rtl/axi_tx_core.sv, axi_tx_sys.sv, designs/b59a_axi_tx/rtl/b59a_axi_tx_top.sv);
tests/test_59a_regs.py checks these names against the comments in that RTL.
"""
from __future__ import annotations

WINDOW = 0x80

# ---- axi_tx_core (0x00-0x1F)
CTRL, STATUS, PROG_ADDR, PROG_DATA, CYCLES, N_TXN, DIGEST = 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06
SB_CHECKED, SB_MISM, SB_UNCHECKED, EXP_MISM, RESP_MISM = 0x07, 0x08, 0x09, 0x0A, 0x0B
FM_ADDR, FM_EXP, FM_GOT, FM_TXN = 0x0C, 0x0D, 0x0E, 0x0F
LOG_ADDR, LOG_DATA = 0x10, 0x11
LMON_SEL, LMON_DATA, SMON_SEL, SMON_DATA = 0x12, 0x13, 0x14, 0x15
LCHK_SEL, LCHK_DATA, SCHK_SEL, SCHK_DATA = 0x16, 0x17, 0x18, 0x19
LCHK_EN, SCHK_EN, S_MAXLEN, SINK_SEL, SINK_DATA, VERSION = 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F
VERSION_VALUE = 0x59A0_0100

CTRL_START, CTRL_ABORT, CTRL_CLEAR = 1, 2, 4

STATUS_BITS = {0: "running", 1: "done", 2: "hang", 3: "error", 4: "lite_violation", 5: "stream_violation",
               6: "mismatch", 7: "sink_mismatch"}
HANG_BITS = {0: "AW", 1: "W", 2: "B", 3: "AR", 4: "R", 5: "stream source busy", 6: "stream expectations pending",
             7: "event timeout"}

# ---- axi_tx_sys (0x20-0x3F)
LA_BASE = 0x20                    # ip_lib/logic_analyser registers 0x20-0x28
SYS_CTRL, SYS_INFO = 0x30, 0x31
TARGETS = {"bram": 0, "periph": 1}
LITE_BUGS = {"none": 0, "b_early": 1, "r_live": 2, "r_glitch": 3, "no_strb": 4, "exokay": 5}
STREAM_BUGS = {"none": 0, "lose_last": 1, "keep_wire": 2}
TARGET_RESET = 1 << 12

# ---- board top (0x40-0x5F)
XADC_BASE = 0x40                  # 0x40-0x4B: codes (see XADC_CODES), 0x4C: alarm latch (write 1s to clear)
XADC_CODES = ["temp", "vccint", "vccaux", "vccbram", "max_temp", "max_vccint", "max_vccaux", "max_vccbram",
              "min_temp", "min_vccint", "min_vccaux", "min_vccbram"]
XADC_ALARMS = 0x4C
ALARM_BITS = {0: "temp", 1: "vccint", 2: "vccaux", 3: "vccbram", 4: "ot"}
AMD_PC_STATUS = 0x50              # the AMD AXI protocol checker's pc_asserted (bit 0, sticky) when built in

# ---- rules (axil_rules.sv, axis_rules.sv), cited to the AXI and AXI4-Stream specifications by section
LITE_RULES = [
    ("AW_HOLD", "AWVALID held, AWADDR/AWPROT stable until AWREADY", "IHI 0022H A3.2.1, A3.2.2"),
    ("W_HOLD", "WVALID held, WDATA/WSTRB stable until WREADY", "IHI 0022H A3.2.1, A3.2.2"),
    ("B_HOLD", "BVALID held, BRESP stable until BREADY", "IHI 0022H A3.2.1, A3.2.2"),
    ("AR_HOLD", "ARVALID held, ARADDR/ARPROT stable until ARREADY", "IHI 0022H A3.2.1, A3.2.2"),
    ("R_HOLD", "RVALID held, RDATA/RRESP stable until RREADY", "IHI 0022H A3.2.1, A3.2.2"),
    ("B_EARLY", "BVALID only after both the AW and the W handshake", "IHI 0022H A3.3.1"),
    ("R_EARLY", "RVALID only after the AR handshake", "IHI 0022H A3.3.1"),
    ("RESET", "every VALID low at the first edge out of reset", "IHI 0022H A3.1.2"),
    ("EXOKAY", "no EXOKAY response on AXI4-Lite", "IHI 0022H B1.1"),
]
STREAM_RULES = [
    ("HOLD", "TVALID held, TDATA/TKEEP/TSTRB/TLAST stable until TREADY", "IHI 0051B 2.2"),
    ("KEEP_STRB", "no byte with TKEEP low and TSTRB high (reserved)", "IHI 0051B 2.4"),
    ("RESET", "TVALID low at the first edge out of reset", "IHI 0051B 2.8"),
    ("MAXLEN", "profile: no packet longer than S_MAXLEN beats", "profile rule"),
    ("PACKED", "profile: TKEEP all ones but on the last beat, where it is a run of ones from byte 0", "profile rule"),
]

# ---- counter indices: axil_mon.sv, axis_mon.sv, axi_viol_log.sv, axis_tx_sink
CH = ["AW", "W", "B", "AR", "R"]
WAIT_BINS = ["0", "1", "2-3", "4-15", "16+"]
LAT_BINS = ["0-3", "4-7", "8-15", "16-31", "32-63", "64-127", "128-255", "256+"]
RESP = ["OKAY", "EXOKAY", "SLVERR", "DECERR"]


def lite_mon_names() -> list[str]:
    n = ["cycles"] + [f"hs_{c}" for c in CH] + [f"stall_{c}" for c in CH]
    n += [f"wait_{c}_{b}" for c in CH for b in WAIT_BINS]
    n += [f"bresp_{r}" for r in RESP] + [f"rresp_{r}" for r in RESP]
    n += ["wstrb_full", "wstrb_partial", "wstrb_zero", "order_aw_first", "order_w_first", "order_same"]
    n += ["wlat_n", "wlat_min", "wlat_max", "wlat_sum"] + [f"wlat_{b}" for b in LAT_BINS]
    n += ["rlat_n", "rlat_min", "rlat_max", "rlat_sum"] + [f"rlat_{b}" for b in LAT_BINS]
    n += ["max_out_w", "max_out_r"]
    assert len(n) == 76
    return n


def stream_mon_names(kw: int = 4) -> list[str]:
    n = ["cycles", "beats", "packets", "stall", "idle"] + [f"wait_{b}" for b in WAIT_BINS]
    n += [f"plen_{b}" for b in ["1", "2-3", "4-7", "8-15", "16+"]] + [f"lastkeep_{i}" for i in range(kw + 1)]
    n += ["max_plen"]
    return n


LOG_SEL = {"first": 32, "first_time": 33, "last": 34, "last_time": 35, "total": 36, "seen": 37}
SINK = ["beats", "packets", "data_mism", "keep_mism", "last_mism", "unexpected", "first_mism"]

# ---- capture sample (axi_tx_sys.sv)
CAPTURE_FIELDS = [("trig", 31, 31), ("lite_viol", 30, 22), ("awvalid", 21, 21), ("awready", 20, 20),
                  ("wvalid", 19, 19), ("wready", 18, 18), ("bvalid", 17, 17), ("bready", 16, 16),
                  ("arvalid", 15, 15), ("arready", 14, 14), ("rvalid", 13, 13), ("rready", 12, 12),
                  ("bresp", 11, 10), ("rresp", 9, 8), ("rdata7_0", 7, 0)]


def field(word: int, hi: int, lo: int) -> int:
    return (word >> lo) & ((1 << (hi - lo + 1)) - 1)
