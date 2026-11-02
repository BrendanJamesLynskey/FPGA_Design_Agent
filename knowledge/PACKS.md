# Knowledge packs: names and hashes

The knowledge bank lives in the **private** repository `BrendanJamesLynskey/FPGA_Design_Agent_Knowledge`. This
file records only each unit's and section's name, version, size and hash, so a scored run can prove which frozen
skills it loaded. **No pack content is published here.**

- Private repo commit: `d6679f5` (main; PR #8 `rtl-pack-v3`, generic layer re-pinned to RTL_Knowledge_Pack v3.0; PR #7
  `217c751` brief 04h, the Artix-7 family and device layers; earlier: `16696e6` PR #6 brief 04f, `6db99dd` PR #5 04e,
  `5fa656fb8312` PR #4 04c, `238fec497e24` PR #3 04d, `6a677334d5c4` PR #2 F1A2).
- Generic source: the private repository `BrendanJamesLynskey/RTL_Knowledge_Pack`, annotated tag `v3.0`, commit
  `b2ae875e0d7572fc16ff80a4576cac4de4b92efd` (33 skills; v3 adds five vendor-neutral RTL implementation skills from
  AMD UG949 chapter 3 and no sections). `v2.2` (`6f99fbdae4409e4f740ee17a61e4cdf797ac405f`, 28 skills) is superseded;
  its skill files are byte-identical to `v2.1`. `techniques/` and `functions/` are that tag converted to Agent Skills by
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

The axes are: techniques and functions (together the `generic` bundle), vendor, family, board, and procedures.

| Unit | Name | Version | Skills | Files | Skill bytes (budget) | Index bytes | ~Tokens | Hash |
|---|---|---|---|---|---|---|---|---|
| `techniques/` | generic: techniques | RTL_Knowledge_Pack `v3.0` @ `b2ae875` (2026-11-02) | 22 | 40 | 91,739 (none) | 8,287 | 22,935 | `c0f2ccf6f8a7156848c70979d2b250698c63d6daa4b24ddb2d866441e08d7361` |
| `functions/` | generic: functional areas | RTL_Knowledge_Pack `v3.0` @ `b2ae875` (2026-11-02) | 11 | 20 | 45,956 (none) | 3,826 | 11,489 | `daea2321a397f7e4dfcdca2f5741c8f421854ebe0e85ddfd6a5485309b21a540` |
| **bundle `generic`** | techniques + functions | `v3.0` | 33 | - | 137,695 (<= 152,000; was 116,872 <= 120,000 at v2.2) | 12,113 | 34,424 | `d5819522e0ff050785b2191b3bc333e9560da0924a2e8b796090783935e8b6b5` |
| `vendor/ross_distilled/` | vendor: Ross distilled | 1 (2026-10-30; sectioned 2026-10-31) | 14 | 24 | 57,716 (<= 60,000) | 4,429 | 14,429 | `71b0be3612dd70311a092aaf9e108dbc68fe9efd324253a25eba2607ec9e3175` |
| `vendor/free_simulators/` | vendor: free-simulator capabilities (ours, from the owner's matrix) | 1 (2026-11-01, 04f) | 1 | 3 | 3,835 (<= 8,000) | 481 | 959 | `3447bec8c927750cac559038f0529bd44614e699587253e66b2b0b2147020a09` |
| `vendor/ross_shipped/` | vendor: Ross as shipped | Ross release 2026.10.1 | 50 | 1,195 | 918,458 (none) | 12,578 | 225,565 | `3d2cf1b50012d4676a3b432f0725b00848795059224f913935e37cc98846e773` |
| `family/artix7/` | family: Artix-7 technology (04h added 4) | 3 (2026-11-02, 04h) | 10 | 20 | 39,453 (<= 40,000) | 4,741 | 9,863 | `28eead360c308381e27f3cceb5f25b1026ef209d19c3e3cc730ab18544cc8a67` |
| `device/xc7a100tcsg324-1/` | device: the part on the Nexys A7-100T (xc7a100tcsg324-1) | 1 (2026-11-02, 04h) | 3 | 7 | 9,444 (<= 12,000) | 1,652 | 2,361 | `fd1d6767130f728f0ad4efe345c38add57256c285d1a2fb937854ff110e01626` |
| `board/nexys_a7_100t/` | board: Digilent Nexys A7-100T | 2 (2026-10-31, 04c: v2) | 13 | 24 | 39,073 (<= 45,000) | 5,036 | 9,768 | `15c781ea57ce3c45ef22b945aac180d0a01b525c5d9c1432f6a06503a8baaccf` |
| `procedures/` | procedures: board onboarding; UltraFast stages; verification stages | 3 (2026-11-01, 04f: `verification-stages/`, 4 skills) | 14 | 17 | 50,864 (<= 65,000; verification-stages has its own 25,000) | 3,726 | 12,716 | `e70e7802763f6e101bf0dae330ffa6f48038a256e18295fc389a08ee82830e19` |
| `library/` | library (search_docs corpus: 1,783 chunks) | 2 (2026-11-02, 04h: +15 chunks) | - | 16 | see `library/MANIFEST.sha256` | - | - | `04ede99be370ae925d7596cc4a63af9c1a136500de661f6acfb8dfdf35c228d6` |

Root files: `SECTIONS.yaml` sha256 `08c8929d5e671078cc60fb1bd2a6f97d46cb6a15aa7cc3b98bdc5ad06502b35f`; `INDEX.md` sha256
`f24b139acf88282bebfbfe0777ddf5d1cc299a3e2634847440bc9fcf2b9995af`.

## The vocabulary

`SECTIONS.yaml` defines 57 section ids: 19 techniques and 21 functional areas (generic; their ids,
kinds and definitions come from RTL_Knowledge_Pack `v3.0` and must match it), 2 device, 12 tool-flow (vendor topics) and
3 procedures (`board-onboarding`, `ultrafast`, `verification-stages`). One id means one thing on every axis. Sections with no skill yet (gaps):

- generic (15): `low-power`, `synthesis-and-dft`, `ethernet`, `high-speed-serial`, `usb`, `user-io`, `processors`, `dram`, `flash`, `sd-card`, `audio`, `sensors`, `analog`, `expansion-io`, `power-config` (`clocking` and `timing-concepts` were filled by v3.0).
- `vendor/ross_distilled` (4): `hls`, `vitis-ai`, `segmented-config`, `embedded-software`.
- `family/artix7` (6): `reset`, `arithmetic`, `fifo`, `cdc`, `low-power`, `high-speed-serial` (04h filled `analog`, `dram`, `power-config`).
- `device/xc7a100tcsg324-1` (7): `clocking`, `timing-concepts`, `on-chip-memory`, `high-speed-serial`, `dsp`, `dram`, `power-config`.
- `board/nexys_a7_100t` (7): `reset`, `video`, `processors`, `dram`, `analog`, `expansion-io`, `io-standards` (04c filled `ethernet`, `usb`, `flash`, `sd-card`, `audio`, `sensors`).
- `procedures`: none (04c added `board-onboarding`, 04e `ultrafast`, 04f `verification-stages`).

## By section

| Unit | Section | Kind | Skills | Skill bytes | Hash |
|---|---|---|---|---|---|
| `techniques/` | `arbitration-and-muxing` | technique | 1 | 3,922 | `a02dbb12426160a6cc68e2f63d4bfb2549b90803d5b6d2d7fba53eee1ecbcc2a` |
| `techniques/` | `arithmetic` | technique | 1 | 4,085 | `bf6c6ea120e886b8a2a42ec4d856de4db09560cbf1e9f3c6551f917f26548cd2` |
| `techniques/` | `cdc` | technique | 1 | 4,139 | `5dfd4b5cc4840d1f425855831b01bfbe124e0670b5a8e9d77afd6872f5edd69e` |
| `techniques/` | `clocking` | technique | 1 | 3,779 | `f274c0b3b32d34085a740ce2d492f200b1d8bca493d6d12d7128ba49f060139f` |
| `techniques/` | `counters-and-timers` | technique | 1 | 3,730 | `2f99ffd7e792441827c5902b886758ace3ef7fc6569f45b68f2a9083b25f9392` |
| `techniques/` | `debugging` | technique | 1 | 4,316 | `fe39950fd33f279b18ab6c2dcadd2713e70692dcb8056b543f00d1754ae4e707` |
| `techniques/` | `existing-code` | technique | 2 | 8,710 | `4b97ec4eefa051bee210505656ab5431420ebc31b6ca3464ae944e1cd742b6ac` |
| `techniques/` | `fifo` | technique | 1 | 4,208 | `5e99af63addc44f30463a7318b1fd7df08906a63bbb792bdb552d24bb8c1381f` |
| `techniques/` | `fsm` | technique | 1 | 4,112 | `b410766da6891f27afb6d6b65279ce53ed5ccf74f8853b821c4fae158cc7774d` |
| `techniques/` | `hardware-algorithms` | technique | 1 | 4,533 | `18674fe906047ee7b9f4d2c1131cf969757623ebcb784a1f14db951a89486e27` |
| `techniques/` | `integration` | technique | 2 | 8,636 | `e861e04e0999ba8384c7f31493560f660781c3c44e6b411f8279e1b941925fa2` |
| `techniques/` | `pipelining-handshakes` | technique | 2 | 8,262 | `252474b332f3ecf7b5ff51c4f29e5a6e51fc8265129eeabcb7bd3d1805eeca79` |
| `techniques/` | `reset` | technique | 2 | 7,982 | `08c65a4c57aa101f2b8ec2aaf173d60deff401fbf13276d59e412f0a4a464ecb` |
| `techniques/` | `rtl-coding` | technique | 2 | 8,341 | `914df5567223d8395c4547d6b4a23599fd7a564c2e416fe2659447a4a739780f` |
| `techniques/` | `spec-reading` | technique | 1 | 4,480 | `d03339fa8300f69cdb3e9498800a547ebf9e398845a78a169d4427e858f556ff` |
| `techniques/` | `timing-concepts` | technique | 1 | 4,302 | `c2d22b0cf915c2a4d975f7ad1a254225c048181a09186685606a4574a20390b9` |
| `techniques/` | `verification` | technique | 1 | 4,202 | `0e1f14eadcf48fa66b1357fbedd9c5991daa18584b7c1f3ed13246c312a652f8` |
| `functions/` | `buses-axi` | function | 1 | 4,250 | `d00940b597d88f7df859b76a1d8446e2a2de54cda296ca6b6a5a139778e7a695` |
| `functions/` | `caches-and-dma` | function | 1 | 4,511 | `966294937adb7b877a6c793f830d3a278d0b47db370d231fbae2d741e2660b89` |
| `functions/` | `crc-and-line-codes` | function | 1 | 4,502 | `b0dbc8ee1924fe9ef3a335b0a531c61f026e08bf2c0bcd0589e547c6168a8b70` |
| `functions/` | `crypto` | function | 1 | 4,493 | `570ffd28b9f46568accae2fffede4e239ffd9e0d096779a203297a82e13bcfee` |
| `functions/` | `dsp` | function | 2 | 7,924 | `cf2af6c7904f2ffcd27aed526c64d382a1339273aaa116126e6f3240022cc133` |
| `functions/` | `on-chip-memory` | function | 2 | 8,547 | `794d37f27a48727da47794adfad43fe0b4a680682f7f939d02b825adfaa28f7b` |
| `functions/` | `serial-buses` | function | 2 | 8,328 | `035238ea6a7f94ab7202c98c0d6e813a5c2c25066f7fb7d7a029d9d5dc49e15c` |
| `functions/` | `video` | function | 1 | 3,401 | `4a8f1d4d9b5b4414ad07a753e2aa7d8e37b58285478e14c2aeca8fd04739b069` |
| `vendor/free_simulators/` | `simulation` | tool-flow | 1 | 3,835 | `305ceb14f3bbccfcb6746d50d0aed84d24787fdd1878403d0418fd39185ccc10` |
| `vendor/ross_distilled/` | `clocking-ip` | tool-flow | 1 | 4,495 | `9cb66d5f9a42742c53be67e8270c1c81229132dc49ba1602986b9ecd4044e13f` |
| `vendor/ross_distilled/` | `constraints` | tool-flow | 1 | 4,495 | `2dfb95cff49e1da9a6edf6b2d4dc192306f6bffd1d363326b2655871979ecd57` |
| `vendor/ross_distilled/` | `debug-ila-vio` | tool-flow | 2 | 7,023 | `2be1ea67875613b39f7fa6cb9d7c0c4abd49a0c82599b7f1e69d992e72a717af` |
| `vendor/ross_distilled/` | `drc-and-cdc-reports` | tool-flow | 1 | 4,263 | `c3f669e75a9d18ffea52b27880868c26b28c37ebcea089faa66d9b40f987bd06` |
| `vendor/ross_distilled/` | `lint` | tool-flow | 2 | 8,310 | `95cc4d7d8a2fa6f590f9f5d503d1d2416766023ca448333029a2fb43475f6664` |
| `vendor/ross_distilled/` | `non-project-flow` | tool-flow | 2 | 6,907 | `665264ec5caf2df20fae50174c8b08ea02afb9a82b0b314676e0356fd58e4d0e` |
| `vendor/ross_distilled/` | `simulation` | tool-flow | 1 | 4,310 | `80dc14d75b047f67d705c3d891a3bd7c25bea8782da8f1bdc4363ba61661a648` |
| `vendor/ross_distilled/` | `timing-methodology` | tool-flow | 4 | 17,913 | `2fbc4f783120d8b4f77fafae89d1af6eac79ec81a2c9eceb71ac7dba78897347` |
| `family/artix7/` | `analog` | function | 1 | 4,400 | `6286bf07dc3730025a1daf4b2505f77e2572156d11325312576be22e84dda01e` |
| `family/artix7/` | `clocking` | technique | 1 | 3,913 | `0fad4f3d7344bab1e596247ea634943a2ec70758b84be79a6e073dbf42e18dff` |
| `family/artix7/` | `dram` | function | 1 | 3,661 | `24cb37aa9fd9f7eb1e02b77ab24f121770abdeacb5d04a360b5b4344dfd1cef1` |
| `family/artix7/` | `dsp` | function | 1 | 4,095 | `21d734a3b3a5aa882b083019918e7011d1d99f27225d5ff868f8bb37b2d70937` |
| `family/artix7/` | `io-standards` | device | 1 | 3,774 | `220c366a10ddf415dd838337a6fa1d44b1b52e792a7b347bb15999e9bf7f8202` |
| `family/artix7/` | `logic-fabric` | device | 1 | 3,641 | `5001c3c1b77035388db2fe3e6a4614579aba0f5e07a5861541804d0bbb37625f` |
| `family/artix7/` | `on-chip-memory` | function | 1 | 3,952 | `fa22d80ad468c9cb13065cf2b5f80d1436689bd4b39f6468673a47eb5b473813` |
| `family/artix7/` | `power-config` | function | 2 | 8,595 | `dc1004cf4a70e20234b4b0278c1c244952045af9749ead7f6ab76ed98780f0be` |
| `family/artix7/` | `timing-concepts` | technique | 1 | 3,422 | `566f1f9f5374de1c8339c65d8044c6c04c6ab44a2a925bbe0808f5dd487f0105` |
| `device/xc7a100tcsg324-1/` | `analog` | function | 1 | 3,025 | `1e1fc1efc184db3a695597cf54135da60fbcf1ee33de981eb7c4ad1460f8e704` |
| `device/xc7a100tcsg324-1/` | `io-standards` | device | 1 | 3,438 | `caff21b59a60ba8561dedeedd8bf610479d8b20a35c2a6ece89ff4e3adf32d6f` |
| `device/xc7a100tcsg324-1/` | `logic-fabric` | device | 1 | 2,981 | `dd3e1d0913e54847ef47313f30d5ccb51fae16e7030d106637a1c6cdec835a47` |
| `board/nexys_a7_100t/` | `audio` | function | 2 | 4,684 | `04611adfe9cfacef48c52da63f781a321ecb7640d1e955a952efe8938ae52f7f` |
| `board/nexys_a7_100t/` | `clocking` | technique | 1 | 3,678 | `cdfc9164dab9e6d708af0f9e3b53d6f2e430b7588c95840d28ac879eba0a9e48` |
| `board/nexys_a7_100t/` | `ethernet` | function | 1 | 2,810 | `4d43a9efead8ce3cc2140fec81e31c97d2abc51d1290be81a03f14331e00df25` |
| `board/nexys_a7_100t/` | `flash` | function | 1 | 2,991 | `1246a646d92a41c079b0818c0b3e883ff131b89aa8c06992ba20c266d513ef4e` |
| `board/nexys_a7_100t/` | `power-config` | function | 1 | 4,395 | `0082d947bd859ef7b79e006cd63cd0e84b2fa53c85cc47bb43e42d370e5c131c` |
| `board/nexys_a7_100t/` | `sd-card` | function | 1 | 2,168 | `10d803cee86a9c6331e5abad26eab8882615868e245eb7ef83ce3d66453631a8` |
| `board/nexys_a7_100t/` | `sensors` | function | 2 | 4,899 | `859e60e28ade9ae7818981d8038f7729ad831877aea9cd8d5b0947aea747e373` |
| `board/nexys_a7_100t/` | `serial-buses` | function | 1 | 3,141 | `634d673ecf3dc3eb474ac76736d77a226e292471316bed1b08454521386855a0` |
| `board/nexys_a7_100t/` | `usb` | function | 1 | 2,616 | `08904a4de332fa07dfcda408b6193db43174f55f30b599a3250001576a168bc3` |
| `board/nexys_a7_100t/` | `user-io` | function | 2 | 7,691 | `d032b38fc6d90706c471346a56f44039cac5afa2c12623045a6ee2431e5dd6b9` |
| `procedures/` | `board-onboarding` | procedure | 1 | 5,285 | `6994af76389f07628736ade90381fe9cbaa272a4862bbb48c760966db50e59f4` |
| `procedures/` | `ultrafast` | procedure | 9 | 34,705 | `da81d4fb4f51ffaba2a5db4b222f5ed90a50feb6b8a79aa0576b331eab71d3ab` |
| `procedures/` | `verification-stages` | procedure | 4 | 10,874 | `8becc05bacbb043aea3d6fdf9d63f915b10b48d55d4c7eb295d5394d8824e40d` |

## Sources, per unit

- `techniques/`, `functions/`: RTL_Knowledge_Pack `v3.0`: 33 vendor-neutral RTL skills (spec reading to caches, ciphers, DSP, serial links, display timing; v3.0 adds RTL implementation skills from AMD UG949 chapter 3). Textbooks, IEEE 1800, AMBA, NIST FIPS, IEEE 802.3, NXP UM10204, ITU-T, VESA DMT.
- `vendor/ross_distilled/`: 9 skills mined from AMD Ross (MIT) at the commit above, rewritten for the batch non-project flow on Vivado 2025.2; 5 gap skills from AMD UG835, UG894, UG903, UG906, UG949 (v2025.2), UG901, UG474, UG479.
- `vendor/ross_shipped/`: AMD Ross `skills/` tree, unchanged, with its MIT LICENSE.
- `family/artix7/`: (04h adds the configuration, power-rail, XADC and DDR2 memory-interface skills from the 7-series documents downloaded for that brief) AMD UG474 v1.9, UG473 v1.14, UG479 v1.10, UG472 v1.14, UG471 v1.10, DS181 v1.27.1 (-1 speed grade), UG901/UG949 v2025.2.
- `device/xc7a100tcsg324-1/`: the xc7a100t resource counts and csg324 package, bank and clock-pin facts, and XADC and configuration pins (04h), from the AMD 7-series data sheets and package pin files, in our own words.
- `board/nexys_a7_100t/`: Digilent Nexys A7 reference manual (PDF rev. 2019-07-10 and the 2024 web page), schematic Rev D.0 (D.2, D.3 compared) and master XDC; data sheets of the ADT7420, ADXL362, SPK0833LM4H, AD8592, ADP121, ADP2118, ADP2138, LAN8720A, PIC24FJ256GB110 family, S25FL128S, S25FL127S, Micron 1Gb DDR2; AMD UG470 v1.17. Board facts confirmed on the owner's board by four self-check designs (`results/board_v2/`).
- `procedures/`: the board-onboarding procedure as carried out in brief 04c (this repo's `boards/nexys_a7_100t/`, `tools/inventory_check.py`, `flow/board_check.py`, `designs/b2_*`); the nine UltraFast stage procedures (04e) from AMD UG949 v2025.2 (with UG906 and UG835 v2025.2 for `report_qor_assessment` and rule ids), cited to chapter and section, with the thresholds `flow/gates.py` applies ([docs/methodology.md](../docs/methodology.md)).
- `library/`: 1,783 chunks (04h added 15): 34 of our summaries of the AMD/Digilent documents above, and the full Ross markdown text (1,734 chunks); each chunk carries its section ids. Offline BM25; used only by the skills-plus-library arm.

## How F3 uses them

Knowledge depth arms load by axis: no pack; `generic` (techniques + functions); `generic` + `vendor/ross_shipped`
or `vendor/ross_distilled`; and those plus `family/artix7`, `device/xc7a100tcsg324-1` and `board/nexys_a7_100t`. A section can also be
loaded alone (its own hash above). An arm that preloads all of `generic` reads about 34,000 tokens; arms that load
skills on demand read the root `INDEX.md` or a section `INDEX.md` and the bodies they pick, and a task's skills
can be chosen deterministically by `tools/select_skills.py` (by family, board and section ids). The `library` is a
separate add-on (skills only against skills plus library). Each scored run records the hashes it loaded; a run
whose hashes differ from this table is not a scored run.

The human debug playbook ([docs/debug_playbook.md](../docs/debug_playbook.md)) is not a pack and is never given
to the agent in scored runs.

## Re-pins of 2026-11-02 (04h family and device layers; generic v3.0)

Two private-bank PRs changed pins on 2026-11-02. PR #7 (brief 04h, `217c751`) added four skills to `family/artix7/`
(configuration, power rails and decoupling, XADC, DDR2 memory interface), a new `device` axis with
`device/xc7a100tcsg324-1/` (three skills) and 15 library chunks; `SECTIONS.yaml` and the root `INDEX.md` changed (no new
section ids). PR #8 (`d6679f5`) re-pinned the generic layer to RTL_Knowledge_Pack `v3.0` (`b2ae875`): 33 skills,
the `generic` budget raised from 120,000 to 152,000 bytes. Units whose hash did not change: `vendor/*`, `board/nexys_a7_100t/`
and `procedures/`. Every hash above was recomputed from the bank at `d6679f5` with `sha256sum` and
`python3 tools/hash_layers.py --json --sections`. Scored runs made before this date carry the older generic hashes
(`d854ada1…`, `SECTIONS.yaml` `764efbbe…`, `INDEX.md` `629b0ba2…`) and stay valid for the pins they recorded.

## The UltraFast stage procedures (2026-10-31, 04e)

The procedures unit gained a second section, `ultrafast`, with nine skills, one per stage of AMD's UltraFast
Design Methodology (UG949 v2025.2): board and device planning, RTL design creation, constraints, synthesis,
implementation, timing closure, power closure, DRC closure, configuration and debug. Each gives the stage's exit
checks as exact Tcl commands with thresholds (the same checks `flow/gates.py` applies, stage by stage; see
[docs/methodology.md](../docs/methodology.md) for the mapping and the deviations from UG949), common failures and
version notes, cited to UG949 chapter and section. A procedure section may now hold several skills
(`procedures/<section>/<skill>/SKILL.md`), and the procedures unit has a 40,000-byte skill budget. Only
`procedures/`, `SECTIONS.yaml` (one new id) and the root `INDEX.md` changed; every other unit's hash is as in 04c.

## Board layer v2 and procedures (2026-10-31, 04c)

The board layer gained one skill per reachable peripheral (sensors, audio, Ethernet, USB HID, microSD, the
configuration flash read-only), filed under the existing section ids, and the bank gained its first procedure,
`board-onboarding`, written so the KV260 (F6) and third-party boards (D1) can be onboarded the same way. One
existing board skill (`nexys-a7-power-config-and-ddr2`) was edited because the board moved to wall power and the
power gate changed. Only `board/nexys_a7_100t/`, the new `procedures/` and the root `INDEX.md` changed; every
other unit's hash and `SECTIONS.yaml` are as in 04d. The board-layer facts are checked in this repo:
[boards/nexys_a7_100t/inventory.yaml](../boards/nexys_a7_100t/inventory.yaml) (by `tools/inventory_check.py` in
CI) and on the board ([results/board_v2](../results/board_v2/README.md)).

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
