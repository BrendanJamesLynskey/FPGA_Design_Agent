# Knowledge packs: names and hashes

The knowledge packs live in the **private** repository `BrendanJamesLynskey/FPGA_Design_Agent_Knowledge`. This
file records only each layer's name, version, size and hash, so a scored run can prove which frozen pack it
loaded. **No pack content is published here.**

- Private repo commit: `cecdb18b83a5` (branch `f1a-packs`, PR #1 there).
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
| `generic/` | generic v2 | v2 (2026-10-30) | 19 | 21 | 80,000 (<= 80,000) | 20,000 | `9da7878f67d3020fc10f5e667588cba4611b7241c8f82b8914e10cf59bf4121a` |
| `vendor/ross_distilled/` | vendor: Ross distilled | 1 (2026-10-30) | 14 | 17 | 59,356 (<= 60,000) | 14,839 | `add703f2b90f3ea57f64959f634b36cf0f724a4b7396ad00cbc78198bf76c42b` |
| `vendor/ross_shipped/` | vendor: Ross as shipped | Ross release 2026.10.1 | 50 | 1,195 | 931,036 (none) | 228,707 | `3d2cf1b50012d4676a3b432f0725b00848795059224f913935e37cc98846e773` |
| `family/artix7/` | family: Artix-7 (Nexys A7-100T, xc7a100tcsg324-1) | 1 (2026-10-30) | 10 | 12 | 38,213 (<= 40,000) | 9,553 | `ff0e08361dd6439a7e37b4f8a81c37568df5dc5f465a8bb91387135b05c4cc01` |
| `library/` | library (search_docs corpus) | 1 (2026-10-30) | - | 12 | 6,944,186 total (none) | - | `7ffe2cc14c4b7bc3ef5a3c7f5257f354088b84b8aadc57880e094c444d6d307d` |

## Sources, per layer

- `generic/`: CVDP RTL pack's 15 skills unchanged, plus 4 new: serial protocols, CRC/LFSR, DSP structures, buttons/displays/video timing. Textbooks, IEEE 1800, AMBA, NXP UM10204, ITU-T O.150, VESA DMT.
- `vendor/ross_distilled/`: 9 skills mined from AMD Ross (MIT) at the commit below, rewritten for the batch non-project flow on Vivado 2025.2; 5 gap skills from AMD UG835, UG894, UG903, UG906, UG949 (v2025.2), UG901, UG474, UG479.
- `vendor/ross_shipped/`: AMD Ross `skills/` tree, unchanged, with its MIT LICENSE.
- `family/artix7/`: AMD UG474 v1.9, UG473 v1.14, UG479 v1.10, UG472 v1.14, UG471 v1.10, DS181 v1.27.1 (-1 speed grade), UG901/UG949 v2025.2; Digilent Nexys A7 reference manual (rev. 2019-07-10) and master XDC.
- `library/`: 1,768 chunks: 34 of our summaries of the AMD/Digilent documents above, and the full Ross markdown text (1,734 chunks). Offline BM25; used only by the skills-plus-library arm.

## How F3 uses them

Knowledge depth arms: no pack; `generic`; `generic` + `vendor/ross_shipped` or `vendor/ross_distilled`; and
those plus `family/artix7`. The `library` is a separate add-on (skills only against skills plus library). Each
scored run records the layer hashes it loaded; a run whose hashes differ from this table is not a scored run.

The human debug playbook ([docs/debug_playbook.md](../docs/debug_playbook.md)) is not a pack and is never given
to the agent in scored runs.
