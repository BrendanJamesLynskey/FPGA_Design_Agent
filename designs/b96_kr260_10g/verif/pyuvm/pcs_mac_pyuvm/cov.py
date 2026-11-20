"""Functional coverage of the pyuvm bench (brief 123), written with cocotb-coverage: CoverPoint and CoverCross decorators on small sampling functions.
The points and bins are the same 213 as brief 112's (names kept, so the two reports line up); two helper bins (`rxf.slane (non-aborted)`) are extra because a
cocotb-coverage cross can only combine points sampled by the same function. Coverage is merged across seeds with cocotb-coverage's own `merge_coverage` on the
YAML each run exports."""
from __future__ import annotations

from cocotb_coverage.coverage import CoverCross, CoverPoint, coverage_db

from . import refmodels as ref
from .items import PATTERNS

LEN_BINS = ["LEN_60", "LEN_61_64", "LEN_65_127", "LEN_128_255", "LEN_256_511", "LEN_512_1023", "LEN_1024_1500", "LEN_JUMBO"]
GAP_BINS = ["GAP_0", "GAP_1_3", "GAP_4_15", "GAP_16_63", "GAP_64_255", "GAP_256P"]
IFG_BINS = ["IFG_12", "IFG_13_15", "IFG_16_23", "IFG_24_63", "IFG_64_511", "IFG_512P"]
FCS_BINS = ["FS_GOOD", "FS_BAD"]
SL_BINS = ["SL_0", "SL_4"]
OC_BINS = ["OC_GOOD", "OC_BAD_FCS", "OC_ABORT"]
BL_BINS = ["BL_HUNTING", "BL_LOCKED"]
EK_BINS = ["EK_SH_ERR", "EK_TYPE_ERR", "EK_ORDERED_SET", "EK_BAD_FCS_TX", "EK_ABORT", "EK_BIT_FLIP", "EK_HDR_BURST", "EK_SLIP_INS", "EK_SLIP_DEL", "EK_ERR_CHAR_XGMII",
           "EK_RX_RESET"]
LK_BINS = ["LK_ACQUIRE", "LK_LOSS_IDLE", "LK_LOSS_IN_FRAME", "LK_SLIP_HUNT", "LK_RELOCK"]
HS_BINS = ["HS_0", "HS_1_3", "HS_4_10", "HS_11P"]
LT_BINS = ["LT_HUNT_TO_LOCK", "LT_LOCK_TO_HUNT", "LT_HUNT_TO_HUNT"]
LANES = list(range(8))


def _cls(n, edges, names):
    for e, nm in zip(edges, names):
        if n <= e:
            return nm
    return names[-1]


def classify_len(n): return _cls(n, [60, 64, 127, 255, 511, 1023, 1500], LEN_BINS)
def classify_gap(n): return _cls(n, [0, 3, 15, 63, 255], GAP_BINS)
def classify_ifg(n): return _cls(n, [12, 15, 23, 63, 511], IFG_BINS)


def classify_pat(payload: bytes) -> str:
    """The payload pattern, recovered from the bytes the monitor saw (the monitor does not know the sequence's choice)."""
    if not any(payload):
        return "PAT_ZEROS"
    if all(b == 0xFF for b in payload):
        return "PAT_ONES"
    if all(b == (i & 0xFF) for i, b in enumerate(payload)):
        return "PAT_COUNT"
    if all(b == (0x55 if i % 2 else 0xAA) for i, b in enumerate(payload)):
        return "PAT_ALT"
    return "PAT_RANDOM"


@CoverPoint("frame.len", xf=lambda n, m, f, p, g: classify_len(n), bins=LEN_BINS)
@CoverPoint("frame.mod8", xf=lambda n, m, f, p, g: m, bins=LANES)
@CoverPoint("frame.fcs", xf=lambda n, m, f, p, g: f, bins=FCS_BINS)
@CoverPoint("frame.pat", xf=lambda n, m, f, p, g: p, bins=PATTERNS)
@CoverPoint("frame.gap", xf=lambda n, m, f, p, g: classify_gap(g), bins=GAP_BINS)
@CoverCross("frame.len x fcs", items=["frame.len", "frame.fcs"])
@CoverCross("frame.len x gap", items=["frame.len", "frame.gap"])
def _frame(n, m, f, p, g): pass


def sample_frame(payload: bytes, poison: bool, gap: int) -> None:
    _frame(len(payload), len(payload) % 8, "FS_BAD" if poison else "FS_GOOD", classify_pat(payload), gap)
    if poison:
        sample_err("EK_BAD_FCS_TX")


@CoverPoint("ifg.bytes", xf=lambda b, t: classify_ifg(b), bins=IFG_BINS)
@CoverPoint("ifg.tlane", xf=lambda b, t: t, bins=LANES)
def sample_ifg(b, t): pass


@CoverPoint("rxf.outcome", xf=lambda o, s: o, bins=OC_BINS)
@CoverPoint("rxf.slane", xf=lambda o, s: s, bins=SL_BINS)
@CoverCross("rxf.outcome x slane", items=["rxf.outcome", "rxf.slane"])
def _rxf_all(o, s): pass


@CoverPoint("rxf.slane (non-aborted)", xf=lambda s, t: s, bins=SL_BINS)
@CoverPoint("rxf.tlane", xf=lambda s, t: t, bins=LANES)
@CoverCross("rxf.slane x tlane", items=["rxf.slane (non-aborted)", "rxf.tlane"])
def _rxf_ok(s, t): pass


def sample_rxf(lane4: bool, tlane: int, fcs_ok: bool, aborted: bool) -> None:
    s = "SL_4" if lane4 else "SL_0"
    _rxf_all("OC_ABORT" if aborted else ("OC_GOOD" if fcs_ok else "OC_BAD_FCS"), s)
    if aborted:
        sample_err("EK_ABORT")
    else:
        _rxf_ok(s, tlane)


@CoverPoint("block.kind", xf=lambda k, l: k, bins=ref.BLOCK_KINDS)
@CoverPoint("block.lock", xf=lambda k, l: l, bins=BL_BINS)
@CoverCross("block.kind x lock", items=["block.kind", "block.lock"])
def _blk(k, l): pass


def sample_blk(kind: str, locked: bool) -> None:
    _blk(kind, "BL_LOCKED" if locked else "BL_HUNTING")
    if locked:
        if kind == "BK_BADSH": sample_err("EK_SH_ERR")
        if kind == "BK_BADTYPE": sample_err("EK_TYPE_ERR")
        if kind == "BK_OS": sample_err("EK_ORDERED_SET")


@CoverPoint("error.kind", xf=lambda k: k, bins=EK_BINS)
def sample_err(k): pass


@CoverPoint("lock.event", xf=lambda k, h, t: k, bins=LK_BINS)
@CoverPoint("lock.transition", xf=lambda k, h, t: t, bins=LT_BINS)
def _lock(k, h, t): pass


@CoverPoint("lock.hunt_slips_before_first_lock", xf=lambda h: h, bins=HS_BINS)
def _hunt(h): pass


def sample_lock(kind: str, slips_before: int = 0) -> None:
    tr = "LT_HUNT_TO_LOCK" if kind in ("LK_ACQUIRE", "LK_RELOCK") else ("LT_HUNT_TO_HUNT" if kind == "LK_SLIP_HUNT" else "LT_LOCK_TO_HUNT")
    _lock(kind, None, tr)
    if kind == "LK_ACQUIRE":
        _hunt("HS_0" if slips_before == 0 else "HS_1_3" if slips_before <= 3 else "HS_4_10" if slips_before <= 10 else "HS_11P")


def summary() -> dict:
    """{point: (bins, hit)} over every CoverPoint and CoverCross, plus the totals."""
    from cocotb_coverage.coverage import CoverCross as CC, CoverPoint as CP
    out = {}
    for name, item in coverage_db.items():
        if isinstance(item, (CP, CC)):
            out[name] = (item.size, item.coverage)
    return out


def holes() -> list[str]:
    from cocotb_coverage.coverage import CoverCross as CC, CoverPoint as CP
    out = []
    for name, item in coverage_db.items():
        if isinstance(item, (CP, CC)):
            out += [f"{name}|{b}" for b, h in item.detailed_coverage.items() if h < item.at_least]
    return out
