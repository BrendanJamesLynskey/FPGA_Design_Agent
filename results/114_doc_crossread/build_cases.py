"""Build the code side of the brief 114 cases (run from the repository root): the real files at the commits named in PREREGISTRATION.md,
and the four planted mutations. The planted files are single, labelled edits of real files (synthetic mistakes); nothing is invented otherwise.

    python3 results/114_doc_crossread/build_cases.py
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "cases"

#: (case, [(published name, repo path, commit or None for the working tree)])
REAL = {
    "h1_96d_five_word": [("hw.py", "flow/eyescan/hw.py", "854cb409"), ("eyescan.py", "designs/b96_kr260_10g/model/eyescan.py", "854cb409")],
    "h2_96d2_ten_word": [("hw.py", "flow/eyescan/hw.py", "253d73c6"), ("eyescan.py", "designs/b96_kr260_10g/model/eyescan.py", "253d73c6")],
    "f1_uartlite": [("tb_uartlite.sv", "amd_ip_probe/tb/tb_uartlite.sv", None)],
    "f2_timer": [("tb_timer.sv", "amd_ip_probe/tb/tb_timer.sv", None)],
    "f3_gpio": [("tb_gpio.sv", "amd_ip_probe/tb/tb_gpio.sv", None)],
    "f4_zb_accel": [("zb_accel_regs.h", "designs/b64b_zedboard/gen/regs/zb_accel_regs.h", None)],
}
#: planted mistakes: (case, base case, file, [(old, new)]) each old string occurs exactly once
PLANTS = {
    "p1_uartlite_stat_ctrl_swapped": ("f1_uartlite", "tb_uartlite.sv", [("STAT = 4'h8, CTRL = 4'hC", "STAT = 4'hC, CTRL = 4'h8")]),
    "p2_timer_load_bit": ("f2_timer", "tb_timer.sv", [("LOAD = 32'h20", "LOAD = 32'h40")]),
    "p3_zb_accel_id_reset": ("f4_zb_accel", "zb_accel_regs.h", [("#define ZB_ACCEL_ID_RESET 0x64b30100u", "#define ZB_ACCEL_ID_RESET 0x64b30101u"),
                                                                 ("#define ZB_ACCEL_ID_VERSION_RESET 0x100u", "#define ZB_ACCEL_ID_VERSION_RESET 0x101u")]),
    "p4_zb_accel_version_width": ("f4_zb_accel", "zb_accel_regs.h", [("#define ZB_ACCEL_ID_VERSION_WIDTH 16u", "#define ZB_ACCEL_ID_VERSION_WIDTH 8u"),
                                                                     ("#define ZB_ACCEL_ID_VERSION_MASK 0x0000ffffu", "#define ZB_ACCEL_ID_VERSION_MASK 0x000000ffu")]),
}


def main() -> None:
    for case, files in REAL.items():
        d = OUT / case / "code"
        d.mkdir(parents=True, exist_ok=True)
        for name, path, commit in files:
            data = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT, capture_output=True, text=True, check=True).stdout if commit \
                else subprocess.run(["git", "show", f"origin/main:{path}"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
            (d / name).write_text(data)
    for case, (base, name, edits) in PLANTS.items():
        text = (OUT / base / "code" / name).read_text()
        for old, new in edits:
            assert text.count(old) == 1, (case, old)
            text = text.replace(old, new)
        d = OUT / case / "code"
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(text)
        (d / "PLANTED.txt").write_text(f"Synthetic mistake planted in a copy of {base}/{name}: " + "; ".join(f"{o!r} -> {n!r}" for o, n in edits) + "\n")


if __name__ == "__main__":
    main()
