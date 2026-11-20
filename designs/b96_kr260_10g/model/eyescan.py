"""Python twin of brief 96D's eye-scan point sequencer (rtl/es_ctrl.sv) and of the GT stand-in's error function (sim/gth_wiz_model96.sv).

`point_transactions` lists, access by access, what the sequencer does on the DRP for one point (UG576 v1.7.1 chapter 4 sequence at the appendix C addresses);
tests/eyescan_cocotb.py compares the RTL's DRP traffic with it and the RTL's result registers with `stand_in_error_count`. The stand-in's error count is a fixed
mixing function (a different prime weight per field), NOT a physical eye: it exists so a test can see every field land in the right bit of the right word."""

from __future__ import annotations

#: DRP addresses of GTHE4_CHANNEL (UG576 v1.7.1 appendix C, Table C-2, and chapter 4 Table 4-21), 10-bit.
A_ES_CONTROL = 0x03C        # [15:10] ES_CONTROL, [9] ES_ERRDET_EN, [8] ES_EYE_SCAN_EN, [4:0] ES_PRESCALE
#: The static eye-scan words, GTHE4 (UltraScale+): TEN 16-bit words each (160-bit ES_QUALIFIER, ES_QUAL_MASK, ES_SDATA_MASK; UG576 v1.7.1 Table 4-20 printed pp. 230-232, Table C-2
#: printed pp. 463 and 511). Words 0-4 are at 0x03F/0x044/0x049 (+0..+4), words 5-9 are in a different block at 0x0E7/0x0EC/0x0F1 (+0..+4). Brief 96D wrote only words 0-4 (the
#: UltraScale 80-bit layout): brief 96D2.
A_ES_QUALIFIER0, A_ES_QUAL_MASK0, A_ES_SDATA_MASK0 = 0x03F, 0x044, 0x049
A_ES_QUALIFIER5, A_ES_QUAL_MASK5, A_ES_SDATA_MASK5 = 0x0E7, 0x0EC, 0x0F1


def word_addrs(base_lo: int, base_hi: int) -> list[int]:
    """DRP addresses of words 0..9 of one 160-bit attribute (low block, then high block)."""
    return [base_lo + i for i in range(5)] + [base_hi + i for i in range(5)]


QUALIFIER_ADDRS = word_addrs(A_ES_QUALIFIER0, A_ES_QUALIFIER5)
QUAL_MASK_ADDRS = word_addrs(A_ES_QUAL_MASK0, A_ES_QUAL_MASK5)
SDATA_MASK_ADDRS = word_addrs(A_ES_SDATA_MASK0, A_ES_SDATA_MASK5)
A_ES_HORZ = 0x04F           # [15:4] ES_HORZ_OFFSET
A_VS = 0x097                # [10] NEG_DIR, [9] UT_SIGN, [8:2] CODE, [1:0] RANGE
A_ERR, A_SAMP, A_STATUS = 0x251, 0x252, 0x253
A_RXOUT_DIV = 0x063         # [2:0]
STATUS_END = 0b0101         # es_control_status: DONE (bit 0) with state END (010)


def stand_in_error_count(horz: int, code: int, neg: int, ut: int, rng: int, pre: int) -> int:
    """The GT stand-in's es_error_count (a test fixture, not physics)."""
    h = horz & 0xFFF
    if h & 0x800:
        h -= 0x1000
    return (h * h * 7 + code * 13 + neg * 101 + ut * 211 + rng * 307 + pre * 401) & 0xFFFF


def point_transactions(mem: dict[int, int], horz: int, code: int, neg: int, ut: int, rng: int, pre: int, polls: int = 1) -> list[tuple[str, int, int | None]]:
    """The DRP accesses of one point, as ("R"|"W", address, value written or None), given the DRP words `mem` read by the read-modify-writes.
    `polls` is how many times the status word is read before it shows END (at least 1; the RTL's count depends on timing, so the test passes what it saw)."""
    o4f, o97, o3c = mem[A_ES_HORZ], mem[A_VS], mem[A_ES_CONTROL]
    keep3c = (o3c >> 5) & 0x1F
    tx = [("R", A_ES_HORZ, None), ("W", A_ES_HORZ, ((horz & 0xFFF) << 4) | (o4f & 0xF)),
          ("R", A_VS, None), ("W", A_VS, (o97 & 0xF800) | (neg << 10) | (ut << 9) | ((code & 0x7F) << 2) | (rng & 3)),
          ("R", A_ES_CONTROL, None), ("W", A_ES_CONTROL, (keep3c << 5) | (pre & 0x1F)),
          ("W", A_ES_CONTROL, (1 << 10) | (keep3c << 5) | (pre & 0x1F))]
    tx += [("R", A_STATUS, None)] * polls
    tx += [("R", A_ERR, None), ("R", A_SAMP, None), ("W", A_ES_CONTROL, (keep3c << 5) | (pre & 0x1F))]
    return tx
