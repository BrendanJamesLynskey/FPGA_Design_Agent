# Design security of a production build: the `production_secure` switch (brief 196)

Owner, 2026-11-23: asked whether design security (bitstream encryption) is in a design agent's remit, agreed with the planner's split and said "queue it".
This page is the datasheet of that switch. It says what the agent sets, what the build proves and from which Vivado output, what stays with the
owner, and what a user could get wrong. Every number names its record under [results/b196](../results/b196/).

## The remit, as agreed

| In scope: set and verified by the agent, at design time | Out of scope: human |
|---|---|
| bitstream encryption and authentication settings for the part family; readback security; JTAG and configuration-port settings | key generation, storage and provisioning |
| production hygiene: no ILA, VIO, debug bridge or other debug core and no debug port in the built design | **any eFUSE or BBRAM programming**: irreversible; the agent never does it, never runs a command that could, and only writes instructions for the owner |
| the system monitor's alarm thresholds, set from the board's operating limits and wired to a latched safe shutdown | the PS secure-boot chain (FSBL, PMU firmware, Linux) |
| a security section in the design's datasheet | side-channel or certification claims: no DPA-resistance, no FIPS-style claim, anywhere |

The area is the *Security* attribute of Dependability (the taxonomy of Avizienis, Laprie, Randell and Landwehr, IEEE TDSC 2004; see
[assurance.md](assurance.md)): the same vocabulary as the structures of brief 194, and the system-monitor shutdown is shared with its *Safety* attribute.

## The switch

`production_secure` is a variable lever of the verification profile (a switch of [agent/graph/profiles.py](../agent/graph/profiles.py); see
[agent_levers.md](agent_levers.md)): the user's, pinned for the run, not changeable by the model. It has five sub-switches that act when the master is on.

| Switch | What the build sets | What proves it (all read from files Vivado or the flow wrote in the build directory) |
|---|---|---|
| `sec_encrypt` | see "What the family allows" | the property read back from the design after `write_bitstream`, the `write_bitstream -verbose` log, the bitstream file |
| `sec_authenticate` | likewise | likewise |
| `sec_readback_off` | `BITSTREAM.READBACK.SECURITY`, `BITSTREAM.GENERAL.JTAG_SYSMON`, `BITSTREAM.GENERAL.DISABLE_JTAG` | the three properties read back after `write_bitstream` |
| `sec_strip_debug` | nothing: it is a property of the design | `get_debug_cores`, the cells of a debug hub, ILA, VIO or bridge, the BSCAN primitives, `MARK_DEBUG` nets, debug-class port names, and the absence of a `.ltx` probe file, all from the implemented design |
| `sec_sysmon_shutdown` | nothing: the thresholds are the SYSMONE4 `INIT_xx` attributes in the RTL, generated from the board file | the `INIT_xx` attributes of the SYSMONE4 cell in the implemented design against the values recomputed from `boards/<board>/board.yaml` `operating_limits`, and that each alarm output drives a register |

**How to ask.** `agent run ... --set production_secure=on` (and `--set sec_strip_debug=off` to leave one out), or answer the interview question
("Is this a production build that must be hard to copy, read back or debug?", default from the spec's words, with the measured cost). By hand, a
`security:` mapping in `build.yaml` or `FDA_SECURITY='{"production_secure": true}'` in the environment. The agent's harness passes the pin to every
build as `FDA_SECURITY`; a `security:` key in `build.yaml` that disagrees with the pin does not change the build and fails the gate
`security_policy_pin`. With `--interview off` nothing asks and the switch stays off unless set.

**Keys.** The flow never makes, reads, stores or programs a key. Vivado writes an `.nky` beside an encrypted bitstream: that file is a secret, it is
git-ignored (`*.nky`), it is never copied into a record, and a test fails if a key-like file is tracked. Key files the owner supplies are named by
environment variables (`FDA_SECURITY_KEYFILE`, `FDA_SECURITY_RSAKEYFILE`), never recorded by path. The harness's scrubbed environment forwards only what the
owner lists in `~/.config/fpga_design_agent/tools.yaml`. A test key is acceptable only as a throw-away file for a build that is never programmed.

## The system monitor and the safe shutdown

The PL system monitor (SYSMONE4, 10-bit) is configured by `INIT_xx` attributes, and its alarm outputs feed `b196_shutdown`, a latch that, once set, holds
the design in reset and drives the outputs inactive until power or a new configuration clears it. The thresholds are not typed in the RTL: `python3 -m
flow.security sysmon-init kr260 --write designs/b196_secure_demo/rtl/b196_sysmon_pkg.sv` generates them from `boards/kr260/board.yaml` `operating_limits`,
and the build check recomputes them from the same file and compares them with the attributes of the SYSMONE4 cell in the implemented design.

| Limit | Value | Source |
|---|---|---|
| junction temperature alarm | 85 C on the reading | the board's own rule (house rules, owner, 2026-10-31); the device range is 0 to 100 C (DS925 recommended operating conditions) |
| VCCINT | 0.698 to 0.742 V | DS925, the 0.72 V rows; the K26 `-2LV-c` grade is not named in that table, so the board file marks the limits `assumption` |
| VCCAUX | 1.746 to 1.854 V | DS925 |
| VCCBRAM | 0.825 to 0.876 V | DS925 |

How the codes are made (our reading of the vendor model `unisims/SYSMONE4.v` of Vivado 2026.1 and of the transfer functions the repository already used
on the owner's board in `designs/b96_kr260_10g/host/b96c_ppm.py`): temperature = code x 501.3743 / 1024 - 273.6777 C, a supply = code / 1024 x 3 V; the upper
thresholds are rounded up and the lower ones down, so a reading inside the limits never fires. Alarms used: temperature (ALM0), VCCINT (ALM1), VCCAUX (ALM2),
VCCBRAM (ALM3) and the device's over-temperature output. **The user over-temperature limit is not set**: the model, and the data sheet's register, ignore it
unless its low four bits are 0011, which also enables the automatic device shutdown (the part de-configures itself); this design keeps the device's own
default limit as the last backstop and makes the shutdown a latch in the fabric.

**The default sequencer mode has no alarms.** In the model, mode 0000 (the attribute default) leaves every alarm off except over-temperature; this design
sets the continuous sequence mode (bits 15:12 of `INIT_41`) and lists the channels it visits (`INIT_48`). A SYSMONE4 instance without these never raises ALM0 to ALM3.

JTAG access to the system monitor could change its thresholds, so `sec_readback_off` also sets `BITSTREAM.GENERAL.JTAG_SYSMON` to `Disable` (UG1085 ch. 9 and
UG908 table of Zynq UltraScale+ MPSoC bitstream settings). With it set, nothing outside the bitstream can lower the alarm limits after configuration.

RESULTS_PLACEHOLDER
