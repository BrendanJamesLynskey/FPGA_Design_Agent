# Transceiver links in the agent (brief 56A)

How a design that uses a gigabit transceiver (GT) is specified, planned, built and checked. The device facts are in the knowledge bank
(`high-speed-serial`, named and hashed in `knowledge/PACKS.md`); this page is the agent side. The worked design is
[designs/b56a_gth_serdes](../designs/b56a_gth_serdes/README.md).

## The `link:` section of spec.yaml

```yaml
link:
  protocol: raw           # raw | aurora_64b66b | aurora_8b10b | ethernet_10g
  line_rate_gbps: 10.3125
  lanes: 1
  refclk_mhz: 156.25      # optional; must be what the board provides
  pll: auto               # optional: auto | cpll | qpll0 | qpll1
  port: sfp               # optional: the board.yaml gt: entry (default sfp)
```

`agent.graph.spec_schema.validate` checks the shape (protocol name, a rate between 0.5 and 16.375 Gb/s, an integer number of lanes, a
reference between 60 and 820 MHz, a PLL choice); a spec with no `link:` is unchanged. A board describes its transceiver ports under `gt:` in
`boards/<board>/board.yaml` (KR260: the SFP+ lane on `GTHE4_CHANNEL_X0Y6` with its pins, reference clock and control pins, each marked
confirmed or not).

## The planner and the tool

`flow/gt_plan.py` turns the `link:` section and the board's `gt:` entry into: the GT Wizard configuration (`CONFIG.*` values), the PLL and
output divider for the part's speed grade, the user-clock frequency, the reference-clock and lane constraints, the 2026.1 licence status of the
IP, and **every reason the link cannot be built** (a rate outside the speed grade's window, more lanes than the board has, a reference the board
does not provide, a user clock above the limit). The agent's `gt_plan` tool (`agent/core/tools.py`, MCP schema 1.11.0) returns it for the design in hand. **The tool is registered but no stage or
role is offered it yet**: adding it to the Designer's stage tool lists changes every recorded request hash, so it needs its own golden
(`agent/tests/request_golden.py`) and is left to the planner as a follow-up. The planner never creates IP.

## How the IP gets into a build

AMD IP Tcl is the maintainers' reviewed file, listed with its SHA-256 in `flow/ip_tcl_allow.yaml` (the agent cannot write Tcl of its own). The
b56a design's Wizard is `designs/b56a_gth_serdes/ip/amd_ip.tcl`; the planner's `wizard` output equals its `CONFIG.*` list (a test checks that).
A new link needs a reviewed Tcl entry; the planner's output is the configuration to review.

## The GT gates (`flow/gt_gates.py`, after synthesis)

Run by `flow/gates.py` when the build has a `gtwizard_ultrascale` core; each is a `post_synth_gt_*` gate in the build's `gates.json`:
`refclk_pin_quad`, `lane_pins`, `rate_in_window`, `user_clock_limit`, `reset_sequence`, `user_clocks_timed`, `drc_clean`. What each checks and the usual fix
is in the knowledge-bank skill `gth-design-gates-for-the-agent`. A part or speed grade with no data is reported as not applicable, never as a pass.
Data: `flow/gt_data.py` (DS925 v1.30 tables 99 and 104) and `flow/gt_parts/<device>.json` (Vivado 2026.1 pin and site queries; xck26 only so far).
CDC between the GT clocks and the fabric uses the existing CDC gates; the Wizard's own reset synchronisers are waived in the design's
`architecture.yaml` with the reason, and its one invalid scoped exception is classified (`EXC-IGNORED-GT-WIZARD`).

## Simulation limits

The free Vivado Simulator refuses the Wizard's simulation model (54,716 instances; the limit is 50,000): `results/56a_serdes/licences.md`. The
fabric around a GT is simulated against a behavioural stand-in (`designs/b56a_gth_serdes/sim/gth_wiz_model.sv`, clearly not the transceiver),
and the transceiver is tested on the board. Anything that needs the real model needs a licence above Basic.

## Not covered

Multi-lane links (one lane on the KR260: bonding and deskew are simulation-only), other boards' transceivers (the planner needs a `gt:` entry and
a pin table), PAM4, PCIe and JESD204 as built designs (the licence and build probe records what the tool allows).
