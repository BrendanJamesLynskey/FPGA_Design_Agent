# Reproducible builds, build identity and release bundles

Three things a hardware team expects of a build flow, and how this repository provides them:

1. **The same sources and tools give the same configuration data.** Measured on Vivado 2026.1: two clean builds of
   the same commit in different directories have identical configuration data; their `.bit` files differ only in 3 to 4
   bytes of the file header (the time of day the bitstream was written). See [Measured](#measured).
2. **A bitstream on a board can be traced back to its exact sources.** Every build writes a manifest; a short hash of
   it, the build ID, is written into the bitstream and read back over JTAG before any board test.
3. **Every release is a complete, checked bundle.** `flow/release.py make` collects one build into a folder with
   `RELEASE.md` and `SHA256SUMS`; `flow/release.py check` verifies a bundle using nothing but the bundle.

Try it, no Vivado needed:

```
python3 flow/manifest.py show designs/t1_dimmer_counter        # the manifest and build ID this design would get now
python3 flow/release.py check results/54_reproducible/sample_bundle/t1_dimmer_counter_base_89315dac
python3 flow/bitstream.py info results/54_reproducible/sample_bundle/t1_dimmer_counter_base_89315dac/t1_dimmer_counter_top.bit
```

## Terms

- **Manifest**: a JSON record of everything that went into one build (input file hashes, settings, tool version,
  commit), written to `build/<variant>/manifest.json`.
- **Build ID**: the first 8 hex digits of a SHA-256 over the part of the manifest that can change the bitstream. It is
  written into the bitstream, not into the design.
- **Build stamp** (`BUILD_STAMP`): an older 8-digit hash of the source and constraint files only, compiled into the
  design as a constant (so it is part of the netlist) and readable over the UART at shell register 0x02. The build ID
  covers more (the flow scripts, the settings and the tool) and does not touch the netlist.
- **USR_ACCESS**: a 32-bit register in the configuration logic of 7 series and UltraScale devices. `write_bitstream`
  can fill it with any value; it is loaded with the bitstream and readable over JTAG without touching the design (AMD
  XAPP1232).
- **CRC**: the configuration checksum the device checks while it loads a bitstream; it covers every register write,
  including USR_ACCESS.
- **Sync word**: the fixed pattern `AA995566` that starts the configuration data after the file header.
- **Bundle**: one folder with a bitstream and the evidence for it (manifest, gate results, reports), plus a checksum
  file over all of it.

## The manifest

`flow/run_vivado.sh` writes it before Vivado starts (`flow/manifest.py pre`) and completes it afterwards
(`flow/manifest.py post`). `python3 flow/manifest.py show designs/<name>` prints the manifest a build would get now.

**Hashed into the build ID** (the keys listed in `build_id_covers`):

| Key | Content |
|---|---|
| `schema`, `design`, `variant`, `top`, `part` | what was built |
| `inputs` | repo-relative path to SHA-256 for every RTL, XDC, data and IP file, `build.yaml`, `probes.yaml` (debug variant), `flow/build.tcl` and every script it sources, and the flow Python that writes the Tcl (`prepare.py`, `srcorder.py`, `vhdl.py`, `ltx_fix.py`) |
| `inputs_tcl` | the Tcl settings file Vivado reads (`inputs.tcl`), with absolute paths replaced by `$ROOT` and `$OUT`: source order, generics, part, top, power environment, timing margin. Not the stop stage: a build stopped after synthesis has no bitstream, and the build cache resumes a longer build from it |
| `settings` | thread count; the directive of each implementation command as `build.tcl` passes it (today all `Default`); seeds (none are set); `FDA_INCREMENTAL` and `FDA_ILA_INSERT` at their effective values (unset and the default value give the same ID); the SHA-256 of the incremental reference checkpoint, when the build is incremental; the build stamp |
| `tools.vivado` | the Vivado version, from the install path (`.../2026.1/Vivado/bin/vivado`); for any other layout, a hash of the binary, never its path |

**Recorded only** (they cannot change the bitstream, or they would make the ID depend on where the build ran):

| Key | Content, and why it is not hashed |
|---|---|
| `input_roles` | each input's role (`rtl`, `xdc`, `data`, `ip`, `probes`, `build_yaml`, `tcl`, `flow_py`): derived from the paths |
| `tools` (the rest) | the version Vivado reported, its SW build number and licence tier, Python and PyYAML: read after the run |
| `kb_pin` | the knowledge-bank commit in `knowledge/PACKS.md`: it guides the agent, not the tool |
| `flow` | `commit`, `dirty` (a tracked file changed, or an input is not tracked), the changed files: a commit that touches no input must not change the ID |
| `settings_recorded` | each implementation command as written in `build.tcl`, the report-only switches (`FDA_XPROBE`, `FDA_RESULT_HASH`, `FDA_BUILD_CACHE`), the stop stage, the incremental reference's location: they add reports or name places |
| `cache`, `incremental` | the build cache's keys and decision, and the incremental reference the build actually used: the keys contain absolute paths; `post` checks that the reference used is the one hashed |
| `outputs` | the bitstream's SHA-256, the USR_ACCESS value read back from the file, the `.ltx` hash: results, not inputs |
| `build_id`, `build_id_sha256`, `build_id_covers` | the ID, the full hash and the list of keys it covers |

**Build ID** = the first 8 hex digits of the SHA-256 of the covered keys as canonical JSON (sorted keys, no spaces).
A commit that only edits a README does not change it; a changed comment in an RTL file does (the file's hash changes,
and so does the build stamp). The thread count is hashed because it is a setting given to the placer and router (the
Vivado implementation user guide, UG904, lists placement, routing and physical optimisation among the multithreaded
tasks), so a flow that did not hash it could not show that it is harmless; [Measured](#measured) shows it was.

The `inputs`, `tools`, `kb_pin` and `flow` keys have the shapes the traceability record reads: `inputs` a
path-to-hash map, `tools` a name-to-version map, `kb_pin` a commit, `flow` with `commit` and `dirty`.

**The build cache.** The manifest reuses the cache's ingredients (the sources hash, the flow Tcl hashes, the switches)
but normalises paths, because the cache's own key contains absolute paths. In the other direction, the build ID is
appended to `inputs.tcl` (`set build_id ...`) before the cache decides, so the cache key covers the build ID: a build
whose identity changed is never served from the cache.

**Incremental builds and the cache.** With `FDA_INCREMENTAL=1` the build ID includes the SHA-256 of the previous
build's routed checkpoint, the reference the new build is placed and routed against. Every build therefore has a
different identity from the one before it, so an incremental build is never a cache hit and never resumes from a cached
checkpoint: it always runs, against the previous result. If the cache does resume anyway (the debug variant can start
from the base build's synthesised checkpoint), the manifest records "reference hashed, not used" and `RELEASE.md` does
not call the build incremental. Sign-off builds should be fresh (`FDA_INCREMENTAL` unset).

## The build ID in the bitstream

- `flow/build.tcl` sets `BITSTREAM.CONFIG.USR_ACCESS 0x<build ID>` just before `write_bitstream`. The value is one
  configuration register write (register AXSS, XAPP1232 appendix B); the routed checkpoint does not depend on it.
- `flow/manifest.py post` reads that write back out of the `.bit` (`flow/bitstream.py`) and the runner fails the build if
  it is not the manifest's build ID.
- **JTAG:** `flow/program.tcl` reads `REGISTER.USR_ACCESS` of the configured device after programming;
  `flow/program.py` compares it with the manifest and stops before any test if they differ.
- **UART:** `flow/board_check.py` and `flow/bringup.py` read the build stamp (shell register 0x02) right after
  programming and compare it with the stamp in the manifest (`settings.build_stamp`, which the build ID covers). A change
  only to settings or flow scripts is therefore caught over JTAG, not over the UART.
- **Why the shell has no build-ID register.** The shell has free addresses, and a register fed by the `USR_ACCESSE2`
  primitive would let the design report the configuration word itself. Such a register was built and passed the shell's
  tests and a full Vivado build, then withdrawn: the test shell is fixed (the benchmark records its fingerprint), so
  changing it is a deliberate, dated change to the benchmark, not part of this work.
- A build made before manifests existed has none: it is programmed with a note and nothing is compared.

## Release bundles

```
python3 flow/release.py make designs/<name> [--variant base|ila] [--trace <trace.json>] [--out <dir>] [--force]
python3 flow/release.py check <bundle>
```

A bundle holds the bitstream (and `.ltx`), `manifest.json`, `gates.json`, `run.json`, the key reports (`reports/`:
timing summary, check_timing, utilisation, power, DRC, methodology, CDC, the routed QoR assessment or the note that the
licence tier did not allow it), the traceability matrix when one exists (`trace.json`, `trace.md`), the review pages
(`review/*.html`), `RELEASE.md` and `SHA256SUMS`. Text files are copied with the machine's details replaced (`$ROOT`,
`$BUILD`, `$HOME`, `<host>`).

`make` refuses a build whose gates failed, whose bitstream does not carry its build ID, whose tree state is unknown, or
that was built from a dirty tree (unless `--allow-dirty`, which the checker then reports). An incremental build is
marked as such in `RELEASE.md`. `--out` must be a new or empty folder, or a previous bundle with `--force`; the checkout,
its parents and the build directory are refused.

`check` verifies: every file in `SHA256SUMS` with that hash and nothing unlisted; the gates passed; the build ID and its
full hash are the hash of the manifest; the bitstream's USR_ACCESS word is the build ID and its hash is the manifest's;
the configuration CRC recomputed from the bitstream matches its CRC words; `RELEASE.md` names the build ID; the tree was
clean.

**Integrity, not authenticity.** `SHA256SUMS` lives inside the bundle. Someone who edits a file and recomputes the sums
gets a bundle that passes, as long as the edit avoids the fields the build ID covers: the commit, the gate results or the
dirty flag can be changed that way. The check shows that a bundle is complete and self-consistent and that the
bitstream is the one its manifest identifies; it does not show who made it. A signature over `SHA256SUMS`, kept outside
the bundle, would add that (not done yet).

A sample bundle (T1, a real Vivado 2026.1 build) is committed under
[results/54_reproducible/sample_bundle](../results/54_reproducible/sample_bundle); CI checks it and recomputes the
manifest of every committed design (Vivado never runs in CI).

## Measured

Vivado 2026.1, T1 (487 LUT) and a course reference design, c13 (11,281 LUT), fresh builds from clean checkouts of one
commit in different directories ([results/54_reproducible](../results/54_reproducible/README.md)):

- **Same inputs, different directories:** same build ID, same placement and routing, identical configuration data. The
  `.bit` files differ in 4 (T1) and 3 (c13) bytes, all in the header's time-of-day field. No field was masked; those
  are the only differences.
- **Thread count 1, 2, 4:** the same placement, routing, reports and configuration frames. The bitstreams differ only
  in the words that carry the build ID (which includes the thread count): the USR_ACCESS word, the CRC that covers it
  (recomputed and checked), two digests Vivado writes into the header (`SW_CRC`, `SW_HDR_SHA256`) and the time.
- **One comment line changed:** the input hash, the build stamp, the build ID and the bitstream all changed; because the
  stamp is a netlist constant, so did placement, routing, LUT count and WNS.
- **Board:** the T1 bitstream's USR_ACCESS read back over JTAG equalled its manifest's build ID, and the build stamp
  over the UART equalled the manifest's stamp. Temperature and supply voltages from the on-chip sensor were inside the
  data-sheet operating range.
