# Reproducible builds, build identity and release bundles (brief 54)

Three things a hardware team expects of a build flow, and how this repository provides them:

1. **The same sources and tools give the same bitstream.** Measured on Vivado 2026.1: see
   [Measured](#measured) and [results/54_reproducible](../results/54_reproducible/results.md).
2. **A bitstream on a board can be traced back to its exact sources.** Every build writes a manifest; a short hash of
   it, the build ID, is in the bitstream's USR_ACCESS register and is read back over JTAG and over the UART shell
   before any board test.
3. **Every release is a complete, checked bundle.** `flow/release.py make` collects one build into a folder with
   `RELEASE.md` and `SHA256SUMS`; `flow/release.py check` verifies a bundle using nothing but the bundle.

## The manifest (`build/<variant>/manifest.json`)

`flow/run_vivado.sh` writes it before Vivado starts (`flow/manifest.py pre`) and completes it afterwards
(`flow/manifest.py post`). `python3 flow/manifest.py show designs/<name>` prints the manifest a build would get now,
without Vivado.

| Key | Content | In the build ID |
|---|---|---|
| `schema`, `design`, `variant`, `top`, `part` | what was built | yes |
| `inputs` | repo-relative path to SHA-256, for every RTL, XDC, data and IP file, `build.yaml`, `probes.yaml` (ILA variant), `flow/build.tcl` and every flow script it sources, and the flow Python that writes the Tcl (`prepare.py`, `srcorder.py`, `vhdl.py`, `ltx_fix.py`) | yes |
| `input_roles` | each input's role (`rtl`, `xdc`, `data`, `ip`, `probes`, `build_yaml`, `tcl`, `flow_py`) | no (derived) |
| `inputs_tcl` | `inputs.tcl` as Vivado reads it, with absolute paths replaced by `$ROOT` and `$OUT`: source order, generics, part, top, power environment, timing margin (not the stop stage: a build stopped after synthesis has no bitstream, and the cache resumes a longer build from it) | yes |
| `settings` | thread count, the directive of each implementation command (as `build.tcl` passes it; today all `Default`), seeds (none are set), the result-changing switches (`FDA_INCREMENTAL`, `FDA_ILA_INSERT`), the build stamp | yes |
| `tools.vivado` | the Vivado version of the install that runs (from its path) | yes |
| `tools` (the rest) | Vivado's version as it reported itself, its SW build number and licence tier (from the run), Python and PyYAML | no |
| `kb_pin` | the knowledge-bank commit in `knowledge/PACKS.md` | no |
| `flow` | `commit`, `dirty` (a tracked file changed, or an input is not tracked), the changed files | no |
| `settings_recorded` | each implementation command as written in `build.tcl`, the report-only switches (`FDA_XPROBE`, `FDA_RESULT_HASH`, `FDA_BUILD_CACHE`) | no |
| `cache` | the build cache's flow and synth keys (brief 33) and its decision | no (the keys contain absolute paths) |
| `outputs` | the bitstream's SHA-256 and the USR_ACCESS value read back from the file; the `.ltx` hash | no (results) |
| `build_id`, `build_id_sha256`, `build_id_covers` | the ID, the full hash and the list of keys it covers | |

**Build ID** = the first 8 hex digits of the SHA-256 of the covered keys as canonical JSON (sorted keys, no spaces).
What is hashed is everything that can change the bitstream and nothing that cannot: a commit that only edits a README
does not change the build ID, while a changed comment in an RTL file does (the file's hash changes, and so does
`BUILD_STAMP`, a constant in the netlist). The thread count is hashed because it is a setting given to the placer and
router (UG904 v2025.2 lists placement, routing and physical optimisation among the multithreaded tasks), so a flow that
did not hash it could not show that it is harmless; [Measured](#measured) says whether it changed anything here.

The `inputs`, `tools`, `kb_pin` and `flow` keys are the ones brief 53's traceability record reads
(`flow/change_record.py read_manifest`); their shapes match what it expects (`inputs` a path-to-hash map, `tools` a
name-to-version map, `flow` with `commit` and `dirty`).

**Reuse of the build-cache key.** The manifest reuses the cache's ingredients (the sources hash from `prepare.py`, the
flow Tcl hashes, the switches) but normalises paths, because the cache's flow key contains the absolute paths of
`inputs.tcl` and the Vivado binary and so differs between two checkouts. In the other direction, the build ID is
appended to `inputs.tcl` (`set build_id ...`) before the cache decides, so the flow key covers the build ID: a build
whose identity changed is never served from the cache.

## The build ID in the bitstream

- `flow/build.tcl` sets `BITSTREAM.CONFIG.USR_ACCESS 0x<build ID>` just before `write_bitstream`. The value is a
  configuration register write in the bitstream (register AXSS, AMD XAPP1232 appendix B); the routed checkpoint does not
  depend on it, so two builds that differ only in their build ID have the same placement and routing.
- `flow/manifest.py post` reads the USR_ACCESS write back out of the `.bit` (`flow/bitstream.py`) and the runner fails
  the build if it is not the manifest's build ID.
- **JTAG:** `flow/program.tcl` reads `REGISTER.USR_ACCESS` of the configured device after programming;
  `flow/program.py` compares it with the manifest and raises before any test if they differ.
- **UART:** `flow/board_check.py` and `flow/bringup.py` read the shell's `BUILD_STAMP` (register 0x02) right after
  programming and compare it with the stamp the manifest recorded (`settings.build_stamp`, which the build ID covers); a
  mismatch stops the run.
- **Why the shell has no build-ID register.** The shell's address map has free addresses (0x05-0x7F), and a register
  fed by the `USR_ACCESSE2` primitive would let the fabric report the configuration word itself. It was built and
  passed the shell's cocotb tests, then withdrawn: the shell is frozen with the benchmark (`benchmark/GRADER_DEPS.json`
  holds its fingerprint, and the v1 and course splits and the eval-1 golden requests depend on it), so changing it
  needs a dated benchmark amendment, which is the planner's decision. Until then the UART check is the stamp, and the
  build ID is checked over JTAG.
- A build made before brief 54 has no manifest: it is programmed with a note and nothing is compared.

`BUILD_STAMP` (register 0x02) stays: it identifies the sources and is a netlist constant; the build ID identifies the
whole build and is in the configuration data.

## Release bundles

```
python3 flow/release.py make designs/<name> [--variant base|ila] [--trace <trace.json>] [--out <dir>]
python3 flow/release.py check <bundle>
```

A bundle holds the bitstream (and `.ltx`), `manifest.json`, `gates.json`, `run.json`, the key reports (`reports/`:
timing summary, check_timing, utilisation, power, DRC, methodology, CDC, the routed QoR assessment or the note that the
licence tier did not allow it), the traceability matrix when one exists (brief 53's `trace.json` and `trace.md`), the
review pages (`review/*.html`), `RELEASE.md` and `SHA256SUMS`. `make` refuses a build whose gates failed, whose
bitstream does not carry its build ID, or that was built from a dirty tree (unless `--allow-dirty`, which the checker
then reports). `check` verifies: every file in `SHA256SUMS` with that hash and nothing unlisted; the gates passed; the
build ID is the hash of the manifest; the bitstream's USR_ACCESS word is the build ID and its hash is the manifest's;
`RELEASE.md` names the build ID; the tree was clean.

A sample bundle (T1, a real Vivado 2026.1 build) is committed under
[results/54_reproducible/sample_bundle](../results/54_reproducible/sample_bundle); CI checks it and recomputes the
manifest of every committed design (Vivado never runs in CI).

## Measured

Vivado 2026.1, T1 (487 LUT) and the c13 course reference (11,281 LUT), fresh builds from clean checkouts of one commit
in different directories ([results/54_reproducible](../results/54_reproducible/README.md)):

- **Same inputs, different directories:** same build ID, same placement and routing, identical configuration data. The
  bitstreams differ in 4 (T1) and 3 (c13) bytes, all in the `.bit` header's time field. Nothing else was masked.
- **Thread count 1, 2, 4:** the same placement, routing, reports and frame data. The bitstreams differ only in the
  USR_ACCESS word (the build ID includes the thread count), the configuration CRC that covers it (recomputed and
  checked), two digests Vivado 2026.1 writes into the header (`SW_CRC`, `SW_HDR_SHA256`) and the time.
- **One comment line changed:** the input hash, the build stamp, the build ID and the bitstream all changed; because the
  stamp is a netlist constant, so did placement, routing, LUT count and WNS.
- **Board:** the T1 bitstream's USR_ACCESS read back over JTAG equalled its manifest's build ID; the shell's stamp over
  the UART equalled the manifest's stamp; conditions inside the recommended operating range.
