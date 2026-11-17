#!/usr/bin/env python3
"""Draws docs/latency_budget.svg from results/b96/core_sim.json and latency_sim.json (every number in the picture is read from those files).
Sober style: two bars of clocks at 161.1328125 MHz (6.2058 ns), no gradients, no glow. Run from the repo root:
    python3 designs/b96_kr260_10g/scripts/make_figure.py"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
R = ROOT / "results" / "b96"
CLK_NS = 1000.0 / 161.1328125
core = json.loads((R / "core_sim.json").read_text())["tick_to_trade_digital_sim"]
lat = json.loads((R / "latency_sim.json").read_text())
segs = [
    ("GT RXDATA to MAC register", core["price_word_captured_at_gt_to_mac_register_clocks"], "#5b6b7a", "2 registers: block, decoded block"),
    ("rule decision", core["mac_register_to_fire_register_clocks"], "#8a97a3", "1 register"),
    ("receive to transmit clock", core["fire_register_to_go_pulse_in_tx_domain_clocks"], "#b7a27a", "pulse crossing: 2 flops + toggle + output"),
    ("frame source, MAC preamble", core["go_pulse_to_order_preamble_in_mac_register_clocks"], "#8a97a3", "start, preamble register"),
    ("MAC to GT TXDATA", 2, "#5b6b7a", "block spills into the next word (+1 on the pause clock)"),
]
total = sum(s[1] for s in segs)
assert lat["tx_mac_to_gt_last_bit_clocks_all_phases"] == [2, 3]
assert total == core["gt_rxdata_price_word_to_gt_txdata_order_start_clocks"], (total, core)
W, H, X0, SC = 880, 250, 40, 55
o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t d" font-family="system-ui,sans-serif" font-size="13">',
     '<title id="t">Digital tick-to-trade budget of the KR260 10G path</title>',
     f'<desc id="d">{total} clocks of 6.2058 ns (plus 0 or 1 for the pause, plus up to 1 for the crossing phase on the board), {total * CLK_NS:.1f} ns, from the GT word that completes the price to the GT word that completes the order start block; simulation, GT and optics not included.</desc>',
     '<style>text{fill:#1d2630}.l{fill:#fff;font-size:12px}@media (prefers-color-scheme:dark){text{fill:#e4e8ec}}</style>',
     f'<text x="{X0}" y="28" font-size="15" font-weight="600">Digital tick-to-trade: {total} clocks = {total * CLK_NS:.1f} ns (simulation; GT, optics and cable not included)</text>']
x = X0
for name, n, col, note in segs:
    w = n * SC
    o.append(f'<rect x="{x}" y="60" width="{w}" height="46" fill="{col}"/>')
    o.append(f'<text class="l" x="{x + w / 2}" y="88" text-anchor="middle">{n}</text>')
    o.append(f'<text x="{x + 2}" y="126" font-size="11">{name}</text>')
    o.append(f'<text x="{x + 2}" y="140" font-size="10" opacity="0.75">{note}</text>')
    x += w
o.append(f'<line x1="{X0}" y1="52" x2="{x}" y2="52" stroke="#1d2630" stroke-width="1"/>')
o.append(f'<text x="{X0}" y="178">One clock is 6.2058 ns (161.1328125 MHz). The same-clock bench shows the crossing\'s fixed part only; on the board it can be one clock longer or shorter.</text>')
o.append(f'<text x="{X0}" y="196">TX: MAC register to the last bit of the start block on TXDATA = 2 clocks, 3 when the 1-in-33 gearbox pause falls on that clock. RX: word captured to MAC start strobe = {lat["rx_start_strobe_clocks_after_last_bit_captured"][0]} clocks.</text>')
o.append(f'<text x="{X0}" y="214">Brief 58A at 1 Gb/s for comparison: 8 clocks of 8 ns = 64 ns, last price byte in to first preamble byte out (byte path, `results/b58a`).</text>')
o.append("</svg>")
(ROOT / "designs/b96_kr260_10g/docs/latency_budget.svg").write_text("\n".join(o) + "\n")
print("wrote latency_budget.svg", total, "clocks")
