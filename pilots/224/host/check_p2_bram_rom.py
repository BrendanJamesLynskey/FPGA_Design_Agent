"""P2 host check: ROM and RAM contents after configuration, then the on-chip March C- test. Criteria: pilots/209/p2_bram_rom/preregistration.md."""
from __future__ import annotations

from pathlib import Path

from report import Report, basics

ROM_FILE = Path(__file__).resolve().parents[1] / "p2_bram_rom" / "data" / "rom_init.hex"
N = 1024


def rom_words() -> list[int]:
    return [int(l, 16) for l in ROM_FILE.read_text().split()]


def read_all(bus, reg: int) -> list[int]:
    bus.wr(0x010, 0)
    bus.wr(0x01C, 1)                                   # AUTOINC
    out = [bus.rd(reg) for _ in range(N)]
    bus.wr(0x01C, 0)
    return out


def march(bus, clk, passes: int, inject: bool, timeout: float = 600.0) -> dict:
    bus.wr(0x024, passes)
    bus.wr(0x020, 0x1 | (0x2 if inject else 0))
    t0 = clk.now()
    while True:
        st = bus.rd(0x028)
        if st & 0x2 and not st & 0x1:
            break
        if clk.now() - t0 > timeout:
            raise TimeoutError(f"march test not done in {timeout} s (STATUS {st:#x})")
        clk.sleep(0.05)
    bus.wr(0x020, 0)
    return {"status": st, "passes_done": st >> 16, "errs": bus.rd(0x02C), "first": bus.rd(0x030)}


def run(bus, rep: Report, clk, **_) -> None:
    basics(bus, rep)
    # NB: basics wrote SCRATCH only. The RAM is read before any write to it: this is the power-up check.
    rom = read_all(bus, 0x014)
    want_rom = rom_words()
    bad = [i for i in range(N) if rom[i] != want_rom[i]]
    rep.crit("rom_matches_file", not bad, f"{len(bad)} words differ" + (f", first at {bad[0]}" if bad else ""), "0 differ of 1024")
    ram = read_all(bus, 0x018)
    bad = [i for i in range(N) if ram[i] != 0xC0DE0000 + i]
    rep.crit("ram_powerup_values", not bad, f"{len(bad)} words differ" + (f", first at {bad[0]}: {ram[bad[0]]:08x}" if bad else ""), "0xC0DE0000 + i, 0 differ of 1024")
    # random access, no auto-increment
    ok = True
    for a in (0, 1, 511, 512, 1023):
        bus.wr(0x010, a)
        ok &= bus.rd(0x014) == want_rom[a]
    rep.crit("rom_random_access", ok, ok, True)
    pats = [(0x00000000, 3), (0xFFFFFFFF, 700), (0x12345678, 1023), (0xDEADBEEF, 0)]
    ok = True
    for v, a in pats:
        bus.wr(0x010, a)
        bus.wr(0x018, v)
        bus.wr(0x010, a)
        ok &= bus.rd(0x018) == v
    rep.crit("ram_write_readback", ok, ok, True)
    r = march(bus, clk, 200, False)
    rep.data["march_clean"] = r
    rep.crit("march_200_passes_done", r["passes_done"] == 200, r["passes_done"], 200)
    rep.crit("march_200_passes_errors", r["errs"] == 0 and r["first"] == 0xFFFFFFFF, f"errs {r['errs']} first {r['first']:#x}", "0 errors, first = 0xFFFFFFFF")
    ram = read_all(bus, 0x018)
    rep.crit("ram_all_zero_after_march", all(v == 0 for v in ram), sum(1 for v in ram if v), "0 nonzero words")
    r = march(bus, clk, 3, True)
    rep.data["march_injected"] = r
    rep.crit("march_injected_fault_detected", r["errs"] >= 3 and r["first"] != 0xFFFFFFFF, f"errs {r['errs']} first {r['first']:#x}", ">= 3 errors (one per pass at least), first address set")
    r = march(bus, clk, 10, False)
    rep.crit("march_clean_again_after_fault", r["errs"] == 0, r["errs"], 0)
