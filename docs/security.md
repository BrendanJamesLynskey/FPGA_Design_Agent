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
| `sec_encrypt` | nothing on a Zynq MPSoC (see "What the family allows") | handed to the owner: listed in the record, no gate |
| `sec_authenticate` | nothing on a Zynq MPSoC | likewise |
| `sec_readback_off` | `BITSTREAM.READBACK.SECURITY` Level1, `BITSTREAM.GENERAL.JTAG_SYSMON` Disable, `BITSTREAM.GENERAL.DISABLE_JTAG` Yes | the three properties read back after `write_bitstream`, and the `write_bitstream -verbose` log that prints them |
| `sec_strip_debug` | nothing: it is a property of the design | `get_debug_cores`, the cells of a debug hub, ILA, VIO or bridge, the BSCAN primitives, `MARK_DEBUG` nets, debug-class port names, and the absence of a `.ltx` probe file, all from the implemented design |
| `sec_sysmon_shutdown` | nothing: the thresholds are the SYSMONE4 `INIT_xx` attributes in the RTL, generated from the board file | the `INIT_xx` attributes of the SYSMONE4 cell in the implemented design against the values recomputed from `boards/<board>/board.yaml` `operating_limits`, and that each alarm output drives a register |

**How to ask.** `agent run ... --set production_secure=on` (and `--set sec_strip_debug=off` to leave one out), or answer the interview question
("Is this a production build that must be hard to copy, read back or debug?", default from the spec's words, with the measured cost). By hand, a
`security:` mapping in `build.yaml` or `FDA_SECURITY='{"production_secure": true}'` in the environment. The agent's harness passes the pin to every
build as `FDA_SECURITY`; a `security:` key in `build.yaml` that disagrees with the pin does not change the build and fails the gate
`security_policy_pin`. The question is asked with the interview on (or the oracle) when no `--verif-profile` was given, like the profile question; with `--interview off`, or with a profile given on the command line, nothing asks and the switch stays off unless `--set` turned it on.

**Keys.** The flow never makes, reads, names, stores or programs a key; there is no key variable or key option in it. On a family where Vivado encrypts the
bitstream it writes an `.nky` beside it: that file is a secret, it is git-ignored (`*.nky`), it is never copied into a record, and a test fails if a key-like file is tracked. The result collector refuses
any file with a 64-digit hex string. A test key would be acceptable only as a throw-away file for a build that is never programmed; this demonstration needed none.

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
thresholds are rounded up and the lower ones down, so a reading inside the limits never fires. The vendor simulation model uses a slightly different temperature function (about 0.9 C higher at 85 C), so the simulation feeds it the matching code. Alarms used: temperature (ALM0), VCCINT (ALM1), VCCAUX (ALM2),
VCCBRAM (ALM3) and the device's over-temperature output. **The user over-temperature limit is not set**: the model, and the data sheet's register, ignore it
unless its low four bits are 0011, which also enables the automatic device shutdown (the part de-configures itself); this design keeps the device's own
default limit as the last backstop and makes the shutdown a latch in the fabric.

**The default sequencer mode has no alarms.** In the model, mode 0000 (the attribute default) leaves every alarm off except over-temperature; this design
sets the continuous sequence mode (bits 15:12 of `INIT_41`) and lists the channels it visits (`INIT_48`). A SYSMONE4 instance without these never raises ALM0 to ALM3.

JTAG access to the system monitor could change its thresholds, so `sec_readback_off` also sets `BITSTREAM.GENERAL.JTAG_SYSMON` to `Disable` (UG1085 ch. 9 and
UG908 table of Zynq UltraScale+ MPSoC bitstream settings). With it set, nothing outside the bitstream can lower the alarm limits after configuration.

## What the family allows (measured on Vivado 2026.1, xck26)

The K26 is a **Zynq UltraScale+ MPSoC** part. On a design for it `BITSTREAM.ENCRYPTION.*` and `BITSTREAM.AUTHENTICATION.*` are **read-only**: `set_property` gives
`Cannot change read-only property` ([results/b196/probe_xck26_properties.txt](../results/b196/probe_xck26_properties.txt)); the same session accepted
`BITSTREAM.READBACK.SECURITY`, `BITSTREAM.GENERAL.JTAG_SYSMON` and `BITSTREAM.GENERAL.DISABLE_JTAG`. This agrees with the documents: the settings table for
the MPSoC (UG908 table 43) has no encryption or authentication row, whereas the Kintex and Virtex UltraScale+ table (UG908 table 40) has them, and UG1085 ch. 12
puts the encryption and authentication of the PL partition in the boot image and the CSU. So for this family:

- `sec_encrypt` and `sec_authenticate` are **handed to the owner**: the build record lists them under `handed_to_owner` with the reason, no gate calls them met, and
  `security_profile_met` means "every gate that applies passed", not "encrypted". The boot image (bootgen), its key and the eFUSE or BBRAM choice are the PS
  secure-boot chain and the key, which are the owner's.
- `BITSTREAM.CONFIG.SECURITY` is not a property (a wrong name; the right one is `BITSTREAM.READBACK.SECURITY`).
- Kintex and Virtex UltraScale+ would set encryption and RSA authentication with `write_bitstream` (UG908 table 40, XAPP1267 as UG908 cites it, not read here); a part
  of another family is refused by `prepare.py` (`production_secure has been measured on UltraScale+ (Zynq MPSoC) only`) until it is measured.

## Results

Records in [results/b196](../results/b196/README.md). Three builds of the same part, Vivado 2026.1, one run each:

| build | security gates | what the check found |
|---|---|---|
| plain (no request) | none | no `security_*` gate exists for a build with no request |
| `production_secure` | all that apply pass; encryption and authentication handed to the owner | the three properties read back (`LEVEL1`, `DISABLE`, `YES`); no debug core, cell, BSCAN, marked net or probe file; SYSMONE4 attributes equal the board-file values; every alarm output reaches the shutdown register |
| `production_secure`, debug variant (one ILA) | `security_strip_debug` and `security_profile_met` FAIL | two debug cores (the hub and the ILA), a BSCAN primitive, sixteen marked nets |

Cost: the production build has the same LUT, FF, block RAM and slack as the plain build (the switch sets bitstream properties and the checks read the design) and the
same build time to the tenth of a second (one run each). The debug build adds 1023 LUT and 1832 FF, and needs about 8 GB to build (the debug hub generation hit a
4 GB and then a 6 GB cap).

The system-monitor thresholds were also run through the vendor's simulation model, sixteen readings (inside and outside each limit): see
[results/b196/sysmon_sim.json](../results/b196/sysmon_sim.json).

## What a user could get wrong

- **A passed gate is a statement about Vivado's output, not about an attacker.** Nothing here was measured against one. No certification (FIPS, Common Criteria) and no side-channel resistance is claimed.
- **`security_profile_met` is not "encrypted".** On a Zynq MPSoC encryption and authentication are not done by this build; the record says so under `handed_to_owner`.
- **The request is not the evidence.** The gates read the property back after `write_bitstream`, and the debug inventory from the implemented design; a setting that was asked for and not applied fails.
- **`security:` in `build.yaml` does not beat the pin.** A disagreement fails `security_policy_pin`; with `--interview off` the switch is off unless `--set` turned it on.
- **Disabling JTAG access to the system monitor and the BSCAN block has a price.** The hardware manager cannot read the monitor or reach a BSCAN user register after configuration; a power cycle restores it before the next configuration.
- **The shutdown is a latch.** After one alarm the design stays in reset until power or a new configuration clears it. A noisy supply at the edge of a limit will stop it; the thresholds sit exactly at the data-sheet limits with no margin for the monitor's own error (about 3 C on the temperature, DS925 note 16).
- **The limits are an assumption for this grade.** The K26 `-2LV-c` grade is not named in DS925's table; the board file marks them `assumption`.
- **An unmodelled primitive stays unproved.** The check follows each alarm output through up to three combinational cells to a register and to that register's fanout; it does not prove that the register's output resets everything that matters (the simulation bench of the top does that for this design).
- **A debug core inside a block the agent did not write** (an AMD IP with its own debug option, a vendor netlist) is found only if it appears as a debug core, hub, BSCAN primitive or marked net in the implemented design.
- **Keys.** Nothing here makes or programs one. Vivado's `.nky` (on a family where encryption is a Vivado setting) is a secret and git-ignored. Key files the owner supplies are theirs.

## What the owner does (the agent writes no command for any of it)

1. Decide the boot-image secure-boot approach for the K26 (UG1085 ch. 12, bootgen) and who holds the keys.
2. Generate and store the keys; program eFUSE or BBRAM, if at all, with the AMD tools and the board's rules. These steps are irreversible.
3. Review the boot image's encryption and authentication settings, since this build only lists them as handed over.

