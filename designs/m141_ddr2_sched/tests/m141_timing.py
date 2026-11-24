"""timing.py (brief 141): the DDR2 timing parameters of ddr2_sched in command clocks, from the Micron MT47H64M16 data sheet (Rev. AB 09/18, -25 speed grade, x16) in picoseconds and a clock period.

Each value is the data sheet's, rounded up to whole clocks (the refresh interval rounded down). The bench (tb/tb_ddr2.sv) derives its own copy from the same picoseconds in SystemVerilog and the two are compared by the simulation:
a wrong constant on one side shows as a timing violation. Table and note numbers are those of the data sheet; docs/memory_controller_plan.md section 2 lists them with the page of each.
"""
from __future__ import annotations

# data sheet values, picoseconds (Table 12 AC operating specifications; -25 grade: the slower of -25 and -25E, so both parts' markings are safe)
DS_PS = dict(T_RCD=15000, T_RP=15000, T_RPA=17500, T_RAS=40000, T_RC=55000, T_RRD=10000, T_FAW=50000, T_WR=15000, T_WTR=7500, T_RTP=7500, T_RFC=127500)
TREFI_PS = 7_800_000          # average periodic refresh interval, below 85 C case temperature (the data sheet says 7.8 microseconds; 3.9 above 85 C)

# profiles: the clock period and the read latency. ddr2_800 is the part's fastest grade (not reachable on the Nexys A7: its clocking limits the MIG to 3000 ps, RM Table 3.1.1); nexys_650 is Digilent's
# recommended clock period of 3077 ps (650 Mb/s) with CL 5.
PROFILES = {
    "ddr2_800": dict(TCK_PS=2500, RL=6),
    "nexys_650": dict(TCK_PS=3077, RL=5),
}


def ceil_div(a: int, b: int) -> int:
    return -(-a // b)


def params(profile: str) -> dict:
    p = PROFILES[profile]
    tck = p["TCK_PS"]
    d = {k: ceil_div(v, tck) for k, v in DS_PS.items()}
    d["T_REFI"] = TREFI_PS // tck
    d["RL"] = p["RL"]
    d["WL"] = p["RL"] - 1
    d["BL2"] = 4
    d["TCK_PS"] = tck
    return d


def plusP(profile: str, top: str = "tb_ddr2") -> list[str]:
    """iverilog -P arguments that set the bench's (and so the scheduler's) parameters to the profile."""
    return [f"-P{top}.{k}={v}" for k, v in params(profile).items()]


if __name__ == "__main__":
    for n in PROFILES:
        print(n, params(n))
