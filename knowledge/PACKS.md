# Knowledge packs: names and hashes

The knowledge packs live in the **private** repository `BrendanJamesLynskey/FPGA_Design_Agent_Knowledge`. This
file records only each layer's name, version, size and hash, so a scored run can prove which frozen pack it
loaded. **No pack content is published here.**

- Private repo commit: `6a677334d5c4` (branch `f1a2-generic-from-pack`, PR #2 there; F1A was `cecdb18b83a5`, PR #1).
- Generic source: the private repository `BrendanJamesLynskey/RTL_Knowledge_Pack`, annotated tag `v2.1`, commit
  `d83f39889bef4260fcc6cd3bf7494e55dd350806`. `generic/` is that tag converted to Agent Skills by
  `tools/import_rtl_pack.py` in the knowledge repo (bodies byte-identical; a test re-imports and compares).
- AMD Ross: https://github.com/Xilinx/ross-ai-assistant, commit `dce0fb90611b144dd529490359b51cea5d0d5596`
  (release 2026.10.1, MIT, Copyright (C) 2026 Advanced Micro Devices, Inc.).
- Format: Agent Skills (`<layer>/<skill>/SKILL.md`, YAML front matter `name` and `description`), an `INDEX.md`
  and `PROVENANCE.md` per layer, and a `MANIFEST.sha256` written last.
- **Layer hash** = SHA-256 of the layer's `MANIFEST.sha256` (`sha256sum <layer>/MANIFEST.sha256` reproduces it;
  `python3 tools/hash_layers.py` in the private repo re-checks every file).
- **Loadable bytes** = every `SKILL.md` plus `INDEX.md` (what the agent loads); tokens are approximated as
  characters / 4. Raw AMD PDFs are never committed to either repository.

| Layer | Name | Version | Skills | Files | Loadable bytes (budget) | ~Tokens | Layer hash |
|---|---|---|---|---|---|---|---|
| `generic/` | generic: RTL_Knowledge_Pack | `v2.1` @ `d83f398` (2026-10-31) | 28 | 30 | 119,825 (<= 120,000; each file <= 6,000) | 29,956 | `eb2da1efaf218756ddce32f004ff864dbf2454d140593a80011012196f246d36` |
| `vendor/ross_distilled/` | vendor: Ross distilled | 1 (2026-10-30) | 14 | 17 | 59,356 (<= 60,000) | 14,839 | `add703f2b90f3ea57f64959f634b36cf0f724a4b7396ad00cbc78198bf76c42b` |
| `vendor/ross_shipped/` | vendor: Ross as shipped | Ross release 2026.10.1 | 50 | 1,195 | 931,036 (none) | 228,707 | `3d2cf1b50012d4676a3b432f0725b00848795059224f913935e37cc98846e773` |
| `family/artix7/` | family: Artix-7 device (xc7a100tcsg324-1) | 2 (2026-10-31) | 6 | 8 | 23,954 (<= 40,000) | 5,988 | `48456e156d3ac92f10659d064d8bc833084bd73910d91f4432dcd958862213de` |
| `board/nexys_a7_100t/` | board: Digilent Nexys A7-100T | 1 (2026-10-31) | 5 | 7 | 19,240 (<= 30,000) | 4,810 | `094ee1af45b31564936ee13aedee424a277a538e06a9e1a777250359ddb80a64` |
| `library/` | library (search_docs corpus) | 1 (2026-10-30) | - | 12 | 6,944,186 total (none) | - | `7ffe2cc14c4b7bc3ef5a3c7f5257f354088b84b8aadc57880e094c444d6d307d` |

## Sources, per layer

- `generic/`: RTL_Knowledge_Pack `v2.1`: 28 vendor-neutral RTL skills (spec reading to caches, ciphers, DSP, serial links, display timing). Textbooks, IEEE 1800, AMBA, NIST FIPS, IEEE 802.3, NXP UM10204, ITU-T, VESA DMT.
- `vendor/ross_distilled/`: 9 skills mined from AMD Ross (MIT) at the commit below, rewritten for the batch non-project flow on Vivado 2025.2; 5 gap skills from AMD UG835, UG894, UG903, UG906, UG949 (v2025.2), UG901, UG474, UG479.
- `vendor/ross_shipped/`: AMD Ross `skills/` tree, unchanged, with its MIT LICENSE.
- `family/artix7/`: AMD UG474 v1.9, UG473 v1.14, UG479 v1.10, UG472 v1.14, UG471 v1.10, DS181 v1.27.1 (-1 speed grade), UG901/UG949 v2025.2.
- `board/nexys_a7_100t/`: Digilent Nexys A7 reference manual (rev. 2019-07-10) and master XDC.
- `library/`: 1,768 chunks: 34 of our summaries of the AMD/Digilent documents above, and the full Ross markdown text (1,734 chunks). Offline BM25; used only by the skills-plus-library arm.

## How F3 uses them

Knowledge depth arms: no pack; `generic`; `generic` + `vendor/ross_shipped` or `vendor/ross_distilled`; and
those plus `family/artix7` and `board/nexys_a7_100t`. An arm that preloads all of `generic` reads about 30,000
tokens; arms that load skills on demand read `INDEX.md` (about 1,000 tokens) and the bodies they pick. The `library` is a separate add-on (skills only against skills plus library). Each
scored run records the layer hashes it loaded; a run whose hashes differ from this table is not a scored run.

The human debug playbook ([docs/debug_playbook.md](../docs/debug_playbook.md)) is not a pack and is never given
to the agent in scored runs.

## Why generic changed (2026-10-31, F1A2)

Until F1A2 there were two generic RTL packs: the private RTL_Knowledge_Pack (25 skills at `v2.0`) and this
project's `generic/` (19 skills). Three topics overlapped. By owner decision RTL_Knowledge_Pack is now the single
generic source: the generic RTL parts of the four skills F1A had written were moved into it (tag `v2.1`, three new
skills; CRC/LFSR was already covered), and `generic/` became a pinned, converted copy of that tag. The board facts
moved to a new `board/nexys_a7_100t/` layer, so `family/` is the device only. The generic budget went from 80,000
to 120,000 bytes, with each skill file capped at 6,000, because skills load on demand. The F1A hashes
(generic `9da7878f…`, family `ff0e0836…`) are superseded; the other three layers are unchanged.
