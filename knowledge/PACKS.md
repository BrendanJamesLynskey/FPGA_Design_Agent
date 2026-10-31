# Knowledge packs: names and hashes

The knowledge bank lives in the **private** repository `BrendanJamesLynskey/FPGA_Design_Agent_Knowledge`. This
file records only each unit's and section's name, version, size and hash, so a scored run can prove which frozen
skills it loaded. **No pack content is published here.**

- Private repo commit: `a9c595dc73dc` (branch `sections`, PR #3 there; F1A2 was `6a677334d5c4`, PR #2).
- Generic source: the private repository `BrendanJamesLynskey/RTL_Knowledge_Pack`, annotated tag `v2.2`, commit
  `6f99fbdae4409e4f740ee17a61e4cdf797ac405f`. Its skill files are byte-identical to `v2.1`; `v2.2` adds the file
  that gives every skill a section. `techniques/` and `functions/` are that tag converted to Agent Skills by
  `tools/import_rtl_pack.py` in the knowledge repo (bodies byte-identical; a test re-imports and compares).
- AMD Ross: https://github.com/Xilinx/ross-ai-assistant, commit `dce0fb90611b144dd529490359b51cea5d0d5596`
  (release 2026.10.1, MIT, Copyright (C) 2026 Advanced Micro Devices, Inc.).
- Format: Agent Skills, filed by section: `<unit>/<section>/<skill>/SKILL.md` with YAML front matter `name`,
  `description`, `axis`, `section` and optional `also`; an `INDEX.md` and `MANIFEST.sha256` per section; a
  `PROVENANCE.md` and `MANIFEST.sha256` per unit; a root `SECTIONS.yaml` (the vocabulary) and root `INDEX.md`.
- **Hash** of a unit or a section = SHA-256 of its `MANIFEST.sha256` (`sha256sum <dir>/MANIFEST.sha256`
  reproduces it; `python3 tools/hash_layers.py` in the private repo re-checks every file). **Bundle `generic`** =
  `sha256sum techniques/MANIFEST.sha256 functions/MANIFEST.sha256 | sha256sum`.
- **Skill bytes** = every `SKILL.md` of the unit, front matter included (what an arm that preloads it reads); every
  sectioned `SKILL.md` and `INDEX.md` is at most 6,000 bytes. Index bytes are listed beside the budget, not in it
  (since 04d; see below). Tokens are approximated as characters / 4. Raw AMD PDFs are never committed to either
  repository.

## By axis

The axes are: techniques and functions (together the `generic` bundle), vendor, family, board, and procedures
(none yet).

| Unit | Name | Version | Skills | Files | Skill bytes (budget) | Index bytes | ~Tokens | Hash |
|---|---|---|---|---|---|---|---|---|
| `techniques/` | generic: techniques | RTL_Knowledge_Pack `v2.2` @ `6f99fbd` (2026-10-31) | 18 | 34 | 75,319 (none) | 7,002 | 18,830 | `e1efa47501d0ab50faadde202e9559caffb3ffdca96540a79dc96ff83e41a0c7` |
| `functions/` | generic: functional areas | RTL_Knowledge_Pack `v2.2` @ `6f99fbd` (2026-10-31) | 10 | 19 | 41,553 (none) | 3,659 | 10,388 | `b4f94998397c9e6a361547ad389f71ab10ce9c98e80915d9519751ded40ee69d` |
| **bundle `generic`** | techniques + functions | `v2.2` | 28 | - | 116,872 (<= 120,000) | 10,661 | 29,218 | `d854ada121b2089df380cb8ff92e1386fdd7d23f302a1b52926f91f32eba388a` |
| `vendor/ross_distilled/` | vendor: Ross distilled | 1 (2026-10-30; sectioned 2026-10-31) | 14 | 24 | 57,716 (<= 60,000) | 4,429 | 14,429 | `71b0be3612dd70311a092aaf9e108dbc68fe9efd324253a25eba2607ec9e3175` |
| `vendor/ross_shipped/` | vendor: Ross as shipped | Ross release 2026.10.1 | 50 | 1,195 | 918,458 (none) | 12,578 | 225,565 | `3d2cf1b50012d4676a3b432f0725b00848795059224f913935e37cc98846e773` |
| `family/artix7/` | family: Artix-7 device (xc7a100tcsg324-1) | 2 (2026-10-31; sectioned 2026-10-31) | 6 | 13 | 22,797 (<= 40,000) | 2,964 | 5,699 | `e6b8e0f3e635908573ade30320459581b1137835ca69175414140545ac21689f` |
| `board/nexys_a7_100t/` | board: Digilent Nexys A7-100T | 1 (2026-10-31; sectioned 2026-10-31) | 5 | 10 | 18,279 (<= 45,000) | 2,143 | 4,570 | `54667684c4623741ffed34001bbefa97dc9e71033caebcebb946cd381beecd70` |
| `library/` | library (search_docs corpus) | 1 (2026-10-30; chunk sections 2026-10-31) | - | 12 | 6,990,296 total (none) | - | - | `3ca68766b15c83fc5d04b8da0665b353ba5bc3e7e3daf627f0d2f82f9ff4dbfa` |

Root files: `SECTIONS.yaml` sha256 `193e70662662038b6a24d24f1e310089c827d2de196a3a51b93bf63833a9b70f`; `INDEX.md` sha256
`cf44ba937a8df24db360ce85a1c7ff22879d7ae266a665266c92d3ef576b741d`.

## The vocabulary

`SECTIONS.yaml` defines 55 section ids: 19 techniques and 21 functional areas (generic; their ids,
kinds and definitions come from RTL_Knowledge_Pack `v2.2` and must match it), 2 device, 12 tool-flow (vendor topics) and
1 procedure. One id means one thing on every axis. Sections with no skill yet (gaps):

- generic (17): `clocking`, `timing-concepts`, `low-power`, `synthesis-and-dft`, `ethernet`, `high-speed-serial`, `usb`, `user-io`, `processors`, `dram`, `flash`, `sd-card`, `audio`, `sensors`, `analog`, `expansion-io`, `power-config`.
- `vendor/ross_distilled` (4): `hls`, `vitis-ai`, `segmented-config`, `embedded-software`.
- `family/artix7` (9): `reset`, `arithmetic`, `fifo`, `cdc`, `low-power`, `high-speed-serial`, `dram`, `analog`, `power-config`.
- `board/nexys_a7_100t` (13): `reset`, `ethernet`, `usb`, `video`, `processors`, `dram`, `flash`, `sd-card`, `audio`, `sensors`, `analog`, `expansion-io`, `io-standards`.
- `procedures` (1): `board-onboarding`.

## By section

| Unit | Section | Kind | Skills | Skill bytes | Hash |
|---|---|---|---|---|---|
| `techniques/` | `arbitration-and-muxing` | technique | 1 | 3,922 | `a02dbb12426160a6cc68e2f63d4bfb2549b90803d5b6d2d7fba53eee1ecbcc2a` |
| `techniques/` | `arithmetic` | technique | 1 | 4,085 | `bf6c6ea120e886b8a2a42ec4d856de4db09560cbf1e9f3c6551f917f26548cd2` |
| `techniques/` | `cdc` | technique | 1 | 4,139 | `5dfd4b5cc4840d1f425855831b01bfbe124e0670b5a8e9d77afd6872f5edd69e` |
| `techniques/` | `counters-and-timers` | technique | 1 | 3,730 | `2f99ffd7e792441827c5902b886758ace3ef7fc6569f45b68f2a9083b25f9392` |
| `techniques/` | `debugging` | technique | 1 | 4,316 | `fe39950fd33f279b18ab6c2dcadd2713e70692dcb8056b543f00d1754ae4e707` |
| `techniques/` | `existing-code` | technique | 2 | 8,710 | `4b97ec4eefa051bee210505656ab5431420ebc31b6ca3464ae944e1cd742b6ac` |
| `techniques/` | `fifo` | technique | 1 | 4,208 | `5e99af63addc44f30463a7318b1fd7df08906a63bbb792bdb552d24bb8c1381f` |
| `techniques/` | `fsm` | technique | 1 | 4,112 | `b410766da6891f27afb6d6b65279ce53ed5ccf74f8853b821c4fae158cc7774d` |
| `techniques/` | `hardware-algorithms` | technique | 1 | 4,533 | `18674fe906047ee7b9f4d2c1131cf969757623ebcb784a1f14db951a89486e27` |
| `techniques/` | `integration` | technique | 1 | 4,506 | `19b6a002ec08cbc90613a32eb436cbbfe50388e5c1412cc9a16bf595753ba8d8` |
| `techniques/` | `pipelining-handshakes` | technique | 2 | 8,262 | `252474b332f3ecf7b5ff51c4f29e5a6e51fc8265129eeabcb7bd3d1805eeca79` |
| `techniques/` | `reset` | technique | 1 | 3,773 | `3b5a6ab4c15f24d8162068d1cc6c4c59ec2f823675718a3ecf2e378f66bca508` |
| `techniques/` | `rtl-coding` | technique | 2 | 8,341 | `914df5567223d8395c4547d6b4a23599fd7a564c2e416fe2659447a4a739780f` |
| `techniques/` | `spec-reading` | technique | 1 | 4,480 | `d03339fa8300f69cdb3e9498800a547ebf9e398845a78a169d4427e858f556ff` |
| `techniques/` | `verification` | technique | 1 | 4,202 | `0e1f14eadcf48fa66b1357fbedd9c5991daa18584b7c1f3ed13246c312a652f8` |
| `functions/` | `buses-axi` | function | 1 | 4,250 | `d00940b597d88f7df859b76a1d8446e2a2de54cda296ca6b6a5a139778e7a695` |
| `functions/` | `caches-and-dma` | function | 1 | 4,511 | `966294937adb7b877a6c793f830d3a278d0b47db370d231fbae2d741e2660b89` |
| `functions/` | `crc-and-line-codes` | function | 1 | 4,502 | `b0dbc8ee1924fe9ef3a335b0a531c61f026e08bf2c0bcd0589e547c6168a8b70` |
| `functions/` | `crypto` | function | 1 | 4,493 | `570ffd28b9f46568accae2fffede4e239ffd9e0d096779a203297a82e13bcfee` |
| `functions/` | `dsp` | function | 2 | 7,924 | `cf2af6c7904f2ffcd27aed526c64d382a1339273aaa116126e6f3240022cc133` |
| `functions/` | `on-chip-memory` | function | 1 | 4,144 | `26685c55da40e8ca094a30ff106a4df5bf5e03f97cca939cb2884a991bba463a` |
| `functions/` | `serial-buses` | function | 2 | 8,328 | `035238ea6a7f94ab7202c98c0d6e813a5c2c25066f7fb7d7a029d9d5dc49e15c` |
| `functions/` | `video` | function | 1 | 3,401 | `4a8f1d4d9b5b4414ad07a753e2aa7d8e37b58285478e14c2aeca8fd04739b069` |
| `vendor/ross_distilled/` | `clocking-ip` | tool-flow | 1 | 4,495 | `9cb66d5f9a42742c53be67e8270c1c81229132dc49ba1602986b9ecd4044e13f` |
| `vendor/ross_distilled/` | `constraints` | tool-flow | 1 | 4,495 | `2dfb95cff49e1da9a6edf6b2d4dc192306f6bffd1d363326b2655871979ecd57` |
| `vendor/ross_distilled/` | `debug-ila-vio` | tool-flow | 2 | 7,023 | `2be1ea67875613b39f7fa6cb9d7c0c4abd49a0c82599b7f1e69d992e72a717af` |
| `vendor/ross_distilled/` | `drc-and-cdc-reports` | tool-flow | 1 | 4,263 | `c3f669e75a9d18ffea52b27880868c26b28c37ebcea089faa66d9b40f987bd06` |
| `vendor/ross_distilled/` | `lint` | tool-flow | 2 | 8,310 | `95cc4d7d8a2fa6f590f9f5d503d1d2416766023ca448333029a2fb43475f6664` |
| `vendor/ross_distilled/` | `non-project-flow` | tool-flow | 2 | 6,907 | `665264ec5caf2df20fae50174c8b08ea02afb9a82b0b314676e0356fd58e4d0e` |
| `vendor/ross_distilled/` | `simulation` | tool-flow | 1 | 4,310 | `80dc14d75b047f67d705c3d891a3bd7c25bea8782da8f1bdc4363ba61661a648` |
| `vendor/ross_distilled/` | `timing-methodology` | tool-flow | 4 | 17,913 | `2fbc4f783120d8b4f77fafae89d1af6eac79ec81a2c9eceb71ac7dba78897347` |
| `family/artix7/` | `clocking` | technique | 1 | 3,913 | `0fad4f3d7344bab1e596247ea634943a2ec70758b84be79a6e073dbf42e18dff` |
| `family/artix7/` | `dsp` | function | 1 | 4,095 | `21d734a3b3a5aa882b083019918e7011d1d99f27225d5ff868f8bb37b2d70937` |
| `family/artix7/` | `io-standards` | device | 1 | 3,774 | `220c366a10ddf415dd838337a6fa1d44b1b52e792a7b347bb15999e9bf7f8202` |
| `family/artix7/` | `logic-fabric` | device | 1 | 3,641 | `5001c3c1b77035388db2fe3e6a4614579aba0f5e07a5861541804d0bbb37625f` |
| `family/artix7/` | `on-chip-memory` | function | 1 | 3,952 | `fa22d80ad468c9cb13065cf2b5f80d1436689bd4b39f6468673a47eb5b473813` |
| `family/artix7/` | `timing-concepts` | technique | 1 | 3,422 | `566f1f9f5374de1c8339c65d8044c6c04c6ab44a2a925bbe0808f5dd487f0105` |
| `board/nexys_a7_100t/` | `clocking` | technique | 1 | 3,678 | `cdfc9164dab9e6d708af0f9e3b53d6f2e430b7588c95840d28ac879eba0a9e48` |
| `board/nexys_a7_100t/` | `power-config` | function | 1 | 3,769 | `12a46077fa47ff3fb375994a23de895fbcefac48a3e91df6343f6f232afd9fd6` |
| `board/nexys_a7_100t/` | `serial-buses` | function | 1 | 3,141 | `634d673ecf3dc3eb474ac76736d77a226e292471316bed1b08454521386855a0` |
| `board/nexys_a7_100t/` | `user-io` | function | 2 | 7,691 | `d032b38fc6d90706c471346a56f44039cac5afa2c12623045a6ee2431e5dd6b9` |

## Sources, per unit

- `techniques/`, `functions/`: RTL_Knowledge_Pack `v2.2`: 28 vendor-neutral RTL skills (spec reading to caches, ciphers, DSP, serial links, display timing). Textbooks, IEEE 1800, AMBA, NIST FIPS, IEEE 802.3, NXP UM10204, ITU-T, VESA DMT.
- `vendor/ross_distilled/`: 9 skills mined from AMD Ross (MIT) at the commit above, rewritten for the batch non-project flow on Vivado 2025.2; 5 gap skills from AMD UG835, UG894, UG903, UG906, UG949 (v2025.2), UG901, UG474, UG479.
- `vendor/ross_shipped/`: AMD Ross `skills/` tree, unchanged, with its MIT LICENSE.
- `family/artix7/`: AMD UG474 v1.9, UG473 v1.14, UG479 v1.10, UG472 v1.14, UG471 v1.10, DS181 v1.27.1 (-1 speed grade), UG901/UG949 v2025.2.
- `board/nexys_a7_100t/`: Digilent Nexys A7 reference manual (rev. 2019-07-10) and master XDC.
- `library/`: 1,768 chunks: 34 of our summaries of the AMD/Digilent documents above, and the full Ross markdown text (1,734 chunks); each chunk carries its section ids. Offline BM25; used only by the skills-plus-library arm.

## How F3 uses them

Knowledge depth arms load by axis: no pack; `generic` (techniques + functions); `generic` + `vendor/ross_shipped`
or `vendor/ross_distilled`; and those plus `family/artix7` and `board/nexys_a7_100t`. A section can also be
loaded alone (its own hash above). An arm that preloads all of `generic` reads about 29,000 tokens; arms that load
skills on demand read the root `INDEX.md` or a section `INDEX.md` and the bodies they pick, and a task's skills
can be chosen deterministically by `tools/select_skills.py` (by family, board and section ids). The `library` is a
separate add-on (skills only against skills plus library). Each scored run records the hashes it loaded; a run
whose hashes differ from this table is not a scored run.

The human debug playbook ([docs/debug_playbook.md](../docs/debug_playbook.md)) is not a pack and is never given
to the agent in scored runs.

## Why the bank was sectioned (2026-10-31, 04d)

By owner decision the bank keeps separate sections for each design technique, functional area, device family and
board. The skills moved into section folders with no change to any skill body; only paths and front matter
changed (tests compare every body with the F1A2 commit). `generic/` became `techniques/` + `functions/`, so its
F1A2 hash (`eb2da1ef…`) is superseded by the `generic` bundle hash, and the moved units' hashes changed with their
paths. The budget now counts skill files only: with one index per section, the generic indexes come to about
10,700 bytes, and a selection loads skill files, not indexes. `vendor/ross_shipped/` is unchanged; the library's
chunk text and search index are unchanged, and its hash moved only because each chunk now records its sections.

## Why generic changed (2026-10-31, F1A2)

Until F1A2 there were two generic RTL packs: the private RTL_Knowledge_Pack (25 skills at `v2.0`) and this
project's `generic/` (19 skills). Three topics overlapped. By owner decision RTL_Knowledge_Pack is now the single
generic source: the generic RTL parts of the four skills F1A had written were moved into it (tag `v2.1`, three new
skills; CRC/LFSR was already covered), and `generic/` became a pinned, converted copy of that tag. The board facts
moved to a new `board/nexys_a7_100t/` layer, so `family/` is the device only. The generic budget went from 80,000
to 120,000 bytes, with each skill file capped at 6,000, because skills load on demand. The F1A hashes
(generic `9da7878f…`, family `ff0e0836…`) are superseded; the other three layers are unchanged.
