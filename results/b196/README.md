# Results of brief 196

The `production_secure` switch measured on `designs/b196_secure_demo` (Vivado 2026.1, Basic tier, `xck26-sfvc784-2LV-c`, built only, never programmed). Datasheet:
[docs/security.md](../../docs/security.md).

## Records

| file | what | made by |
|---|---|---|
| `probe_xck26_properties.txt` | the BITSTREAM properties of an xck26 design and what `set_property` did with each security setting | a Vivado 2026.1 batch script on a one-register design (synthesis only) |
| `demo_builds.json` | the plain, production_secure and debug builds: gates, resources, slack, times, security findings | `designs/b196_secure_demo/tests/collect_records.py` from the three build directories |
| `{secure,debug}_security_design.txt`, `*_security_apply.txt`, `*_security_request.json` | what the flow wrote in the build directory and the check read | `flow/security.tcl`, `flow/prepare.py` |
| `sysmon_sim.json` | sixteen readings through the SYSMONE4 simulation model | `designs/b196_secure_demo/tests/run_sysmon_sim.py` |

No key, key file or path to one is in any record; the collector refuses a file with a 64-digit hex string.

## Reproduce

Run these from the repository root; the Vivado steps need Vivado 2026.1 and a heavy slot (`_handoff/take_heavy_slot.sh`), the simulation needs only xsim.

```
FDA_SECURITY='{"production_secure": true}' flow/run_vivado.sh designs/b196_secure_demo base        # Vivado 2026.1, a heavy slot, peak about 4 GB
flow/run_vivado.sh designs/b196_secure_demo base                                                      # the plain build (copy the build dir first)
FDA_SECURITY='{"production_secure": true}' FDA_VIVADO_THREADS=1 MEM_MAX=8G flow/run_vivado.sh designs/b196_secure_demo/dbg base   # the debug build, about 8 GB
python3 designs/b196_secure_demo/tests/run_sysmon_sim.py --out results/b196/sysmon_sim.json           # xsim only
python3 designs/b196_secure_demo/tests/collect_records.py <plain> <secure> <debug>
```

## Results

| build | gates | LUT | FF | block RAM tiles | worst setup slack | wall time | failed gates |
|---|---|---|---|---|---|---|---|
| plain | pass | 334 | 287 | 1 | 33.254 ns | 263.4 s | none |
| secure | pass | 334 | 287 | 1 | 33.254 ns | 263.4 s | none |
| debug | FAIL | 1357 | 2119 | 1.5 | 13.351 ns | 554.8 s | security_profile_met, security_strip_debug |

The production_secure build and the plain build have the same resources and slack: the switch sets bitstream properties and the other checks read the design, so
it costs no fabric. Their wall times agree to the tenth of a second (one run each, spread unknown). The debug build adds one ILA and its debug hub
(+1023 LUT, +1832 FF) and was built with one thread and an 8 GB cap, so its time is not comparable (the first two attempts at two threads hit a 4 GB and a 6 GB cap while generating the debug hub).

Encryption and authentication: `BITSTREAM.ENCRYPTION.*` and `BITSTREAM.AUTHENTICATION.*` are read-only on this part (`probe_xck26_properties.txt`), so the production
build lists them as handed to the owner (`handed_to_owner` in `demo_builds.json`) and no gate calls them done.

System monitor: all 16 readings behaved as expected in the vendor model (`all_ok: True`); the model's temperature transfer function is not the data sheet's, so readings were
converted (see `temperature_scale_note`).

## Known gaps and limits

- One small design, one run each; no board; no attacker; no certification or side-channel claim.
- The simulation model is the vendor's idealised model, not silicon, and has no ADC error.
- The differing configuration words of the plain and production bitstreams were not decoded.
- Kintex and Virtex UltraScale+ encryption was not measured (not licensed or not the part in use).
