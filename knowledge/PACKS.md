# Knowledge packs: names and hashes

The knowledge bank lives in the **private** repository `BrendanJamesLynskey/FPGA_Design_Agent_Knowledge`. This
file records only each unit's and section's name, version, size and hash, so a scored run can prove which frozen
skills it loaded. **No pack content is published here.**

- Private repo commit: `e3cf892` (main, 2026-11-11; merges PR #41 (brief 20 part B: measured I/O timing, virtual clocks, uncertainty; family-matrix rows), and earlier at `a598197`: PR #40 (index and test fixes), PR #39 (brief 41: fanout/replication skill from the 2014 training cross-check), PR #37 (brief 20 part A: measured multicycle and slow-FSM skill), and earlier at `af81c89`: PR #38 (brief 31: family-difference matrix `family_matrix/`, family notes in 10 skills, new skill `zynqmp-porting-from-7-series`, part-aware selection), PR #36 (brief 21: version claims sidecar and probe), and earlier at `68673cb`: PR #35 (brief 19: four ipgen adapter notes in `vendor/amd_ip_cores`, budget 46,000), PR #34 (AVAL-46 measured in the MMCM skill), and earlier at `ab7fc4c`: PR #33 (brief 17: AMBA and AXI, new unit `vendor/amba_axi`), PR #32 (brief 16: CDC check skill), PR #29 `qr-area1-xpm`, PR #30 `qr-area3-kb` and PR #31 (XPM skill back under the 6,000-byte cap), after the briefs 10 B0, 13 and 13b layers: Zynq-7000, Zynq UltraScale+, ZedBoard, KR260, `vendor/amd_constraints`, `vendor/amd_ip_cores`; earlier: `1e589ea` PR #9 `kb-device-knowhow` brief 04j: device primitives, MMCM/PLL configuration,
  LUT6 fabric design, Vivado synthesis attributes and inference templates, STA report interpretation; earlier: `d6679f5`
  PR #8 `rtl-pack-v3`, generic layer re-pinned to RTL_Knowledge_Pack v3.0; PR #7
  `217c751` brief 04h, the Artix-7 family and device layers; earlier: `16696e6` PR #6 brief 04f, `6db99dd` PR #5 04e,
  `5fa656fb8312` PR #4 04c, `238fec497e24` PR #3 04d, `6a677334d5c4` PR #2 F1A2).
- **Vivado version the bank was measured on: 2025.2** (brief 21, 2026-11-10). Every version-bound fact (rule severities, command
  options, IP versions, measured numbers, cited guide versions) is indexed with the version it was verified on in the private
  repo's `claims/`; its `docs/VERSION_UPGRADE.md` is the procedure for a new version (probe, diff, review, re-pin here, regression,
  switch). `flow/version_pin.py` holds this version; each build's `gates.json` carries `vivado_version`, `kb_measured_version` and
  `kb_version_match`. Re-pinning for a new version updates this line, the hashes below and `KB_MEASURED_VERSION`.
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
| `vendor/free_simulators/` | vendor: free-simulator capabilities and cocotb_coverage usage (ours, from the owner's matrix and the cocotb-coverage 2.0 source) | 2 (2026-11-07, 07a2 fix 3) | 3 | 5 | 9,878 (<= 10,000) | 887 | 2,470 | `c347615e5d85ed66890b9a6e6167e4ea1466783c19979de3b53d8cbcfddf857d` |
| `vendor/vivado_synthesis/` | vendor: Vivado synthesis attributes and inference templates (ours, from UG901/UG912/UG949) | 1 (2026-11-03, 04j) | 4 | 7 | 20,965 (<= 22,000) | 1,845 | 5,241 | `469e9d29c156f2ef8dfdff723e8a80a254e3ff805b7ac4b7d0667098213eef61` |
| `vendor/ross_shipped/` | vendor: Ross as shipped | Ross release 2026.10.1 | 50 | 1,195 | 918,458 (none) | 12,578 | 225,565 | `3d2cf1b50012d4676a3b432f0725b00848795059224f913935e37cc98846e773` |
| `family/artix7/` | family: Artix-7 technology (04h added 4; 04j added 10: primitives catalogue, clocking configuration, LUT6 fabric) | 4 (2026-11-03, 04j) | 43 | 58 | 217,990 (<= 222,000) | 16,135 | 54,498 | `5835708f3dfe1ba71be4ac86d1baed38637f774345afca4a2eb4fe719fa7574d` |
| `device/xc7a100tcsg324-1/` | device: the part on the Nexys A7-100T (xc7a100tcsg324-1) | 2 (2026-11-03, 04j: +1 primitives) | 5 | 11 | 16,295 (<= 18,000) | 2,992 | 4,074 | `a92427e0c7a38d2a6c4409c265cfdf19b5fbc37636d53234bac16e5d5b7ffad7` |
| `board/nexys_a7_100t/` | board: Digilent Nexys A7-100T | 2 (2026-10-31, 04c: v2) | 13 | 24 | 39,073 (<= 45,000) | 5,036 | 9,768 | `15c781ea57ce3c45ef22b945aac180d0a01b525c5d9c1432f6a06503a8baaccf` |
| `procedures/` | procedures: board onboarding; UltraFast stages; verification stages | 5 (2026-11-04: the V2 skill names the `V_*` checker macros) | 15 | 19 | 58,749 (<= 72,000) | 4,048 | 14,687 | `7f1d3c10d7b25589ea75b99e15f036d3ad0b528bc9f26ef415358f53efb1fa80` |
| `vendor/amd_constraints/` | vendor: AMD constraints (ours; clocks, I/O delays, exceptions; brief 13b) | 1 (2026-11-10, 13b) | 9 | 11 | 48,653 (<= 52,000) | 3,771 | 12,163 | `74691c9011cd252b2c4ec85af9a64367f870ea8dafa31f44801c4bce2160c8b4` |
| `vendor/amd_ip_cores/` | vendor: free AMD IP cores (ours; FIR, DDS, FFT, memory, DSP; brief 13; brief 19: four ipgen adapter notes) | 2 (2026-11-10, 19) | 10 | 12 | 43,982 (<= 46,000) | 3,733 | 10,996 | `5ca745ee0ab9352077c3c876851caad8ea0e8a737bb3adb682b828e11f61e992` |
| `vendor/amba_axi/` | vendor: AMBA AXI4, AXI4-Lite, AXI4-Stream, APB/AHB rules, AMD AXI IP and verification (ours; brief 17) | 1 (2026-11-10, 17) | 15 | 19 | 61,524 (<= 80,000) | 5,465 | 15,381 | `1add990cc85f37a25cb94326dddf90849f720149918913d291f23e2c70e80e4a` |
| `family/zynq7000/` | family: Zynq-7000 PS7 basics (ours, from UG585/UG470) | 1 (2026-11-09, 10 B0) | 8 | 14 | 24,218 (none) | 2,461 | 6,054 | `5f581b4648505a6d4346d4cf3c694332c2c11dd793c360cefae11839cb1b5d7d` |
| `family/zynq_ultrascale_plus/` | family: Zynq UltraScale+ (PS8, GTH, K26 SOM; ours) | 2 (2026-11-10, 13) | 13 | 22 | 45,121 (none) | 4,929 | 11,280 | `bd536c669416de63c8786016aafef4fcaadb017a67220c91a9de0f8d2d4bb282` |
| `device/xc7z020clg484-1/` | device: the Zynq-7020 part on the ZedBoard (xc7z020clg484-1) | 1 (2026-11-09, 10 B0) | 3 | 7 | 7,062 (none) | 1,153 | 1,766 | `541c7bbd3add40d205c65840f038d96e17b023b061fa4c65a1887658e9488a6f` |
| `device/xck26/` | device: the K26 SOM part (xck26-sfvc784-2LV-c) | 1 (2026-11-09, 10 B0) | 3 | 7 | 6,497 (none) | 1,149 | 1,624 | `111bbb00559b7f8add60d3721c7c838085b5564b7e58bd713115567c913dd354` |
| `board/kr260/` | board: AMD Kria KR260 | 1 (2026-11-09, 10 B0) | 12 | 23 | 27,087 (none) | 3,704 | 6,772 | `838a34741bf2120beae39f6033bcf6998dac5399ee7343a7d2c2d033c1a186e8` |
| `board/zedboard/` | board: Avnet/Digilent ZedBoard | 1 (2026-11-09, 10 B0) | 15 | 28 | 36,556 (none) | 4,634 | 9,139 | `9fa5567f88f707b07efc84c456e8027a76064fd0981b0642739f85a90f42c18b` |
| `library/` | library (search_docs corpus: 1,783 chunks) | 2 (2026-11-02, 04h: +15 chunks) | - | 16 | see `library/MANIFEST.sha256` | - | - | `04ede99be370ae925d7596cc4a63af9c1a136500de661f6acfb8dfdf35c228d6` |

Root files: `SECTIONS.yaml` sha256 `1ae5c8dbc3bb887f05b7377d3915959879abbcd3d8cd4a80d788aea71a253251`; `INDEX.md` sha256
`5c8819c6414f206947752ecf8253bcee15be99e01e3deb50ed45be19d73bd3a9`.

## The vocabulary

`SECTIONS.yaml` defines 62 section ids: 19 techniques and 21 functional areas (generic; their ids,
kinds and definitions come from RTL_Knowledge_Pack `v3.0` and must match it), 4 device (04j added `primitives`), 15 tool-flow (vendor topics; 04j added `synthesis-attributes`, brief 13 `ip-cores`, brief 17 `amba`) and
3 procedures (`board-onboarding`, `ultrafast`, `verification-stages`). One id means one thing on every axis. Sections with no skill yet (gaps; this list is as of 2026-11-03 and is not re-derived here: the bank's root `INDEX.md` marks the current gaps with "(none yet)"):

- generic (15): `low-power`, `synthesis-and-dft`, `ethernet`, `high-speed-serial`, `usb`, `user-io`, `processors`, `dram`, `flash`, `sd-card`, `audio`, `sensors`, `analog`, `expansion-io`, `power-config` (`clocking` and `timing-concepts` were filled by v3.0).
- `vendor/ross_distilled` (4): `hls`, `vitis-ai`, `segmented-config`, `embedded-software`.
- `family/artix7` (6): `reset`, `arithmetic`, `fifo`, `cdc`, `low-power`, `high-speed-serial` (04h filled `analog`, `dram`, `power-config`).
- `device/xc7a100tcsg324-1` (7; `primitives` added by 04j is filled): `clocking`, `timing-concepts`, `on-chip-memory`, `high-speed-serial`, `dsp`, `dram`, `power-config`.
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
| `vendor/amd_constraints/` | `constraints` | tool-flow | 9 | 48,653 | `3b584f2ad3df698c3d018b7a0a974a652dcb3428080a29a293828166934a3daa` |
| `vendor/amd_ip_cores/` | `ip-cores` | tool-flow | 10 | 43,982 | `c3cce770057fcc9f5278ccb35ed0a0680c4ae588770aeabe9b8da7856888262f` |
| `vendor/amba_axi/` | `amba` | tool-flow | 9 | 34,898 | `ccf425bc3cf1c3c03375ece826aceb7dc6fdab2021210cba0dc8b7413a40243e` |
| `vendor/amba_axi/` | `ip-cores` | tool-flow | 3 | 13,321 | `8bb4aea3226501862b927fa33f92ae54a13a38d69307c4725a6a53ee9d395268` |
| `vendor/amba_axi/` | `simulation` | tool-flow | 3 | 13,305 | `50ee9a41b12688a6722f7f94f09c15a5df79078a5508450d09c1f64b31119869` |
| `vendor/free_simulators/` | `simulation` | tool-flow | 3 | 9,878 | `8718cc4fde03e66a48d192f53057e3a26c8c8ff70b86b740941709f030b71e20` |
| `vendor/ross_distilled/` | `clocking-ip` | tool-flow | 1 | 4,495 | `9cb66d5f9a42742c53be67e8270c1c81229132dc49ba1602986b9ecd4044e13f` |
| `vendor/ross_distilled/` | `constraints` | tool-flow | 1 | 4,495 | `2dfb95cff49e1da9a6edf6b2d4dc192306f6bffd1d363326b2655871979ecd57` |
| `vendor/ross_distilled/` | `debug-ila-vio` | tool-flow | 2 | 7,023 | `2be1ea67875613b39f7fa6cb9d7c0c4abd49a0c82599b7f1e69d992e72a717af` |
| `vendor/ross_distilled/` | `drc-and-cdc-reports` | tool-flow | 1 | 4,263 | `c3f669e75a9d18ffea52b27880868c26b28c37ebcea089faa66d9b40f987bd06` |
| `vendor/ross_distilled/` | `lint` | tool-flow | 2 | 8,310 | `95cc4d7d8a2fa6f590f9f5d503d1d2416766023ca448333029a2fb43475f6664` |
| `vendor/ross_distilled/` | `non-project-flow` | tool-flow | 2 | 6,907 | `665264ec5caf2df20fae50174c8b08ea02afb9a82b0b314676e0356fd58e4d0e` |
| `vendor/ross_distilled/` | `simulation` | tool-flow | 1 | 4,310 | `80dc14d75b047f67d705c3d891a3bd7c25bea8782da8f1bdc4363ba61661a648` |
| `vendor/ross_distilled/` | `timing-methodology` | tool-flow | 4 | 17,913 | `2fbc4f783120d8b4f77fafae89d1af6eac79ec81a2c9eceb71ac7dba78897347` |
| `vendor/vivado_synthesis/` | `synthesis-attributes` | tool-flow | 3 | 15,138 | `f1ea1633419300a00ab48d55f1cee2e23ef3908cce82e53a8785a0607b714c50` |
| `vendor/vivado_synthesis/` | `timing-methodology` | tool-flow | 1 | 5,827 | `873cf6cae5a8eb79af076d496512670e30c481ae0ad06da5fb1971a1e32fb6de` |
| `family/artix7/` | `analog` | function | 1 | 4,513 | `67821cec9f1c40a7b5f1adcb5bb9d473f821789a5202c0e1d2e5c1c0332f9680` |
| `family/artix7/` | `cdc` | technique | 6 | 33,651 | `998c3c15278a5ec564840ea9e5e1a321c5af912405ebe234642617b5c06790e9` |
| `family/artix7/` | `clocking` | technique | 5 | 27,223 | `cd05dc1c3016a00d5484038932a6ee92a35de9343dcb09bacf56e78fa4aaa70b` |
| `family/artix7/` | `dram` | function | 1 | 3,661 | `24cb37aa9fd9f7eb1e02b77ab24f121770abdeacb5d04a360b5b4344dfd1cef1` |
| `family/artix7/` | `dsp` | function | 2 | 9,896 | `289af58c8172d22e678a5cf1748f58b983b37c2258bffe5843f3cc65a37f9ae1` |
| `family/artix7/` | `fsm` | technique | 3 | 15,949 | `2ff7244d19ec42878e4227d53edffab65d1efeb0aa33c287fe27ea765b5b6ad1` |
| `family/artix7/` | `io-standards` | device | 3 | 15,895 | `e9d03ac87c513e9e34dcd533e9298f2128b657fc3b88decbf13d8fc72d0a2c9c` |
| `family/artix7/` | `logic-fabric` | device | 4 | 19,605 | `9e86ae2caa9dc8aa8fe702973802a8ab79b39313a5794484f2ecb49ef38fabab` |
| `family/artix7/` | `on-chip-memory` | function | 2 | 9,437 | `3def687be06300a50b4ae01830e6bc5effd1bf55415768c93fc42d2ed2d127ab` |
| `family/artix7/` | `pin-planning` | device | 5 | 25,643 | `8f24a38122f15ed4abd45ec56b3f6173ef00f4016eace43ed5f7abfe96fc9a24` |
| `family/artix7/` | `power-config` | function | 2 | 8,595 | `dc1004cf4a70e20234b4b0278c1c244952045af9749ead7f6ab76ed98780f0be` |
| `family/artix7/` | `primitives` | device | 6 | 28,882 | `973db3a1cde48f595f0c1afce9d37229d87a2d2d2fa949526101730c3ba4830b` |
| `family/artix7/` | `reset` | technique | 2 | 11,618 | `4d3a3281d3a0efd5dd1aa9dee7d0aa9910ce7586b1d58d5ea4bb9f397a48edd4` |
| `family/artix7/` | `timing-concepts` | technique | 1 | 3,422 | `566f1f9f5374de1c8339c65d8044c6c04c6ab44a2a925bbe0808f5dd487f0105` |
| `family/zynq7000/` | `clocking` | technique | 1 | 2,792 | `5c912bd3b6b5a58b1498b9c8080e41809b9feb7b374ea9ecb9dbb23494f99d12` |
| `family/zynq7000/` | `dram` | function | 2 | 7,284 | `3c902f2ef7f759636d9ab66e9197f739a5761eb19bd143694db1fd4b8f94e713` |
| `family/zynq7000/` | `io-standards` | device | 1 | 2,360 | `21c40f7d09d06e4e75ca094e5d29b1b5c0287ff060b66c7d5c78c643db98d546` |
| `family/zynq7000/` | `power-config` | function | 3 | 9,000 | `d7fb1f4d2f7fba199ec3c9d506d75e1e713af0b2df83debcc3f8160f4886d070` |
| `family/zynq7000/` | `reset` | technique | 1 | 2,782 | `73463a1e7941f304a34f349f2917f742c4b441ab97f9c8750c58b67ef14bac28` |
| `family/zynq_ultrascale_plus/` | `clocking` | technique | 2 | 7,700 | `b5cd91cc16f036ee930c1c53b3e98c7531613d166e1a5ea4df33d268f5109ce6` |
| `family/zynq_ultrascale_plus/` | `dram` | function | 2 | 6,573 | `8d00e24db9e1513d93b90842af33062c52ff118cb8632f1a7c7cbde1c5c77f3a` |
| `family/zynq_ultrascale_plus/` | `high-speed-serial` | function | 1 | 2,391 | `6ec940ef70a88c5b267cf1ce2d14048975c43da0b0f2f2d89aef1e320c4927ea` |
| `family/zynq_ultrascale_plus/` | `io-standards` | device | 2 | 7,651 | `38d18797cf351911e9578ff360fe95d6f5e68d1711c12ca7c995c3758e115d3d` |
| `family/zynq_ultrascale_plus/` | `pin-planning` | device | 1 | 4,297 | `1e5d9ff23f148496d3dab78a8231cc95c2fc405a4b3d80c5ee357cc89c5d5b80` |
| `family/zynq_ultrascale_plus/` | `power-config` | function | 2 | 5,362 | `1430521d662229ecb22e718fd74df8302a85726ad55691690ee35fd510a58fec` |
| `family/zynq_ultrascale_plus/` | `primitives` | device | 2 | 8,733 | `0fef4b8ca622e6ec6f9f9a38de9e09f3f0f3df0ecfc59e53bee9711f8b060c52` |
| `family/zynq_ultrascale_plus/` | `reset` | technique | 1 | 2,414 | `64448877a20a2672cc9209f7cbc2ecd099372f3aa0a8c7826ba84e6e805ada57` |
| `device/xc7a100tcsg324-1/` | `analog` | function | 1 | 3,025 | `1e1fc1efc184db3a695597cf54135da60fbcf1ee33de981eb7c4ad1460f8e704` |
| `device/xc7a100tcsg324-1/` | `io-standards` | device | 1 | 3,438 | `caff21b59a60ba8561dedeedd8bf610479d8b20a35c2a6ece89ff4e3adf32d6f` |
| `device/xc7a100tcsg324-1/` | `logic-fabric` | device | 1 | 2,981 | `dd3e1d0913e54847ef47313f30d5ccb51fae16e7030d106637a1c6cdec835a47` |
| `device/xc7a100tcsg324-1/` | `pin-planning` | device | 1 | 3,300 | `5732913f63c198e5a0e456b5b357111c073c32e6ef16739855beb5866803be54` |
| `device/xc7a100tcsg324-1/` | `primitives` | device | 1 | 3,551 | `ce246609ebe86412a7514481a58b45b6098c505e54b5d788fd3f4af1ff327784` |
| `device/xc7z020clg484-1/` | `analog` | function | 1 | 1,983 | `9204c4bf099d0a49a1db6667ea9b44e65b65d48d5f5b7f35b53915760f75cf48` |
| `device/xc7z020clg484-1/` | `io-standards` | device | 1 | 2,512 | `53279a3cabed434b4e5a24ddf8112deca29bbaeb7f05a7cd84b59033cadfd2ac` |
| `device/xc7z020clg484-1/` | `logic-fabric` | device | 1 | 2,567 | `dca07d5e8d3c11aecf9823f442e05377ebeb0d72bb7e197ca4dc5db7a2eb7242` |
| `device/xck26/` | `io-standards` | device | 1 | 2,764 | `8cbaf1b91b3c140ffb492277f0f10a6ee10791d5e1b0393667782a10100c8a4e` |
| `device/xck26/` | `logic-fabric` | device | 1 | 2,182 | `5c814ecdc1cf2f85e39b21ec79f2f8ff032366cacfba991f0e20b17291720845` |
| `device/xck26/` | `primitives` | device | 1 | 1,551 | `4281b5885850e9dcca9d8b4c729722d68c2def432de5f6c9bd1482a4abff2724` |
| `board/kr260/` | `clocking` | technique | 1 | 2,734 | `c130709a14bcb1349d9adef62001f4f6ecbb3d72f2841457cb84316d5f9c03a2` |
| `board/kr260/` | `dram` | function | 1 | 1,781 | `1a670fc749958b6f595501b93dbfe3f5fd4523e2f3802e5f2d82331e57a46153` |
| `board/kr260/` | `ethernet` | function | 2 | 6,017 | `b1bdf2a81387e93011a678daa276b6cc6825dd06b482b8522768f668513b1a10` |
| `board/kr260/` | `expansion-io` | function | 1 | 2,303 | `e632cd7209e8ca892e620453f54f96f22804c2907f952a3de8b145d7f1190acf` |
| `board/kr260/` | `flash` | function | 1 | 1,556 | `430aaea671b0710fead1081af84cbb9ce0351123f48a0b89e2c5bac48757b0c5` |
| `board/kr260/` | `power-config` | function | 2 | 5,562 | `80f12506cfcd89794a8cb4b597ff239e67f1d21fca164aae3f5c8fbb4ef6ea71` |
| `board/kr260/` | `sd-card` | function | 1 | 1,498 | `10ce75854459b3f632ba3dd7e722c0f09c288e689816b2f45034a723db1c1d82` |
| `board/kr260/` | `usb` | function | 1 | 1,614 | `8da2e063e16039a4087ae57ba49e0a79cd1fac15deb7089d7d62889450c3de9c` |
| `board/kr260/` | `user-io` | function | 1 | 1,917 | `e79adbd27f26bdcb9b7a6484afd7e6b95b76106acc40855e6cc4e7ab288cf363` |
| `board/kr260/` | `video` | function | 1 | 2,105 | `8740c57bf24351a2bc09d8281d92bc446aebe2c3b9220b29187ffb332751ec8a` |
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
| `board/zedboard/` | `audio` | function | 1 | 2,350 | `0b084ff8d460695e796aa4f9261c79a6c3e5880538ef418322876f5a52dc988d` |
| `board/zedboard/` | `clocking` | technique | 1 | 2,635 | `8ccbc7eed95a273eeace5132089cbf074f2dc1273ef0cd0f3ebd09ced2bdaacd` |
| `board/zedboard/` | `dram` | function | 1 | 2,479 | `08a8de9f6a0ac178576625faf4d9b1be9f7ae6457ea7782148e7baec596a27bb` |
| `board/zedboard/` | `ethernet` | function | 1 | 2,002 | `fd32d2d4120b9beed7f4c51d8bd48d30cdb5b413c84f72aee32bb9550d6b2ce7` |
| `board/zedboard/` | `expansion-io` | function | 2 | 4,895 | `faca826cec8d7d3711fea04439cd3c46b92a4dc31511e5ee7bde4705de820fc3` |
| `board/zedboard/` | `flash` | function | 1 | 2,385 | `d2bc33e3d36bf2675def22f81e64f0293acf9640a6f06ac46778f8541d776fda` |
| `board/zedboard/` | `power-config` | function | 1 | 3,757 | `29286b89802ce1da28c6315645a891bd8e251b3245df93d14c86f0982107b9db` |
| `board/zedboard/` | `sd-card` | function | 1 | 2,144 | `7964f0d64f15967eb6670fd72bfb4d600e8d50249ee3f04a100baa01a15fbb2f` |
| `board/zedboard/` | `serial-buses` | function | 1 | 2,000 | `0c2dd785e227545af9001d8852a7f03a2db4ebfd62bee31b73edc5b0cfd5db92` |
| `board/zedboard/` | `usb` | function | 1 | 2,370 | `c098b803f7bb8c48661a3f0e1e3c78aaa4fc0ae7ca3ded69dafcf4780bb3b593` |
| `board/zedboard/` | `user-io` | function | 2 | 4,843 | `80f4ebb1febfd338ab277544bb95cfad9a0e79bfcf58560f0134e2b9e83006ad` |
| `board/zedboard/` | `video` | function | 2 | 4,696 | `ec1f5f505f7fd45a5bc0511b78da02d377924aeb5430cdef38a52d00412fd6ca` |
| `procedures/` | `board-onboarding` | procedure | 1 | 5,285 | `6994af76389f07628736ade90381fe9cbaa272a4862bbb48c760966db50e59f4` |
| `procedures/` | `ultrafast` | procedure | 10 | 41,418 | `70ed44173d32eb2e86ce473780cb6216985c5c6d6094f283ae2c440f20959c61` |
| `procedures/` | `verification-stages` | procedure | 4 | 12,046 | `a27d6ed9f50dc94a5f9a1ad6c67250fb068a7eb725d4038a2a95338cfa4f5766` |

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
