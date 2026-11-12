"""Brief 58A: the showcase page's data, in the shapes of the site's graphics kit (docs/showcase_pages.md on brief 61's
branch), from the committed simulation records in this folder. Re-run after any result changes:

    python3 results/b58a/export.py

Writes showcase_sim.json. Simulation only: the published page waits for the board run, whose export writes the same
shapes from the board's histograms (registers 0x400.., 0x500..), so the page code does not change."""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
NS = 8                                                   # one 125 MHz clock


def load(name: str) -> dict:
    return json.loads((HERE / name).read_text())


def main() -> int:
    lat, asm = load("latency_sim.json"), load("latency_sim_assemble.json")
    loop, stale = load("loop_sim.json"), load("stale_parameters_sim.json")
    spec = lat["modes"]["speculative_1msg"]
    # hero 1 (kit "wave"-like timeline, as a list of stages with clock counts): one trigger through the path
    stages = [{"stage": k, "clocks": v, "ns": v * NS} for k, v in spec["stages_cycles"].items()]
    # hero 2 (kit "hist"): the loop simulation's histogram A samples, re-expanded from its bins (order not kept)
    samples = [int(b) * NS for b, n in sorted(loop["bins_a_nonzero"].items(), key=lambda kv: int(kv[0]))
               for _ in range(n)]
    out = {
        "source": "simulation (Icarus Verilog 12, cocotb 2.0.1); not a board measurement",
        "stages": {"trigger": "one ADD on the ask side below the rule's threshold, first message of its frame",
                   "rows": stages, "price_complete_in_clocks": spec["price_complete_in"],
                   "decision_to_first_byte_clocks": spec["decision_to_first_byte"],
                   "sfd_to_first_byte_clocks": spec["tick_to_trade_sfd_to_first_byte"]},
        "modes": {m: {"decision_to_first_byte_clocks": v["decision_to_first_byte"],
                      "sfd_to_first_byte_clocks": v["tick_to_trade_sfd_to_first_byte"]}
                  for m, v in lat["modes"].items()},
        "assemble_then_send": {m: {"decision_to_first_byte_clocks": v["decision_to_first_byte"]}
                               for m, v in asm["modes"].items()},
        "hist": {"unit": "ns", "label": "tick-to-trade in simulation (receive SFD to first byte out), port B loop",
                 "bins": 8, "samples": samples},
        "stale": stale,
    }
    (HERE / "showcase_sim.json").write_text(json.dumps(out, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
