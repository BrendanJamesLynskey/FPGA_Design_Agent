#!/usr/bin/env python3
"""Which GT reference clocks give exactly 10.3125 Gb/s through the QPLL0 integer dividers (brief 96, stage 0).

Line rate = f_ref * N / M / D with M in 1..4, N in 16..160, D in {1,2,4,8,16} (UG576 ch. 2, as summarised in the knowledge bank's
gth-clocking-plls-and-line-rates), the VCO f_ref * N / M inside 9.8 to 16.375 GHz (QPLL0). For D = 1 and the K26's -2LV 12.5 Gb/s limit
the VCO is the line rate itself, 10312.5 MHz. Prints, for common reference frequencies, the (N, M) pairs that work (or none). The UltraScale+ QPLL's fractional-N divider
(UG576, SDM fields; not built in brief 56A or 96) could make N = 82.5 from 125 MHz exactly; this script covers the integer case only.

    python3 designs/b96_kr260_10g/scripts/refclk_options.py
"""

from fractions import Fraction as F

TARGET_MHZ = F(10312500, 1000)
COMMON = [25, 50, 100, 106.25, 125, 148.5, 150, 156.25, 161.1328125, 200, 250, 312.5, 322.265625]


def solutions(f_mhz: float) -> list[tuple[int, int]]:
    f = F(f_mhz).limit_denominator(1_000_000)
    return [(n, m) for m in range(1, 5) for n in range(16, 161) if f * n / m == TARGET_MHZ]


def main() -> None:
    print("reference MHz -> QPLL0 (N, M) giving a 10312.5 MHz VCO (line rate 10.3125 Gb/s at D = 1)")
    for f in COMMON:
        s = solutions(f)
        print(f"{f:>12}: {s[:3] if s else 'none with integer dividers (needs the QPLL's fractional-N divider)'}")


if __name__ == "__main__":
    main()
