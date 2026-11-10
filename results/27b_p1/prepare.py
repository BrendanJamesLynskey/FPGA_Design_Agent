"""Brief 27B P1: set up the two phase 0 measurement projects (development-split subjects only).

    python results/27b_p1/prepare.py            # writes results/27b_p1/<spec>/system/spec.md and results/27b_p1/oracle/<spec>.yaml

- ``pilot1``: the user's words are the pilot's ``system/spec.md`` (project/examples/video_median). The oracle's hidden
  spec is the two development tasks the pilot is built from (``c9_nexys_vga_720p``, ``c9_median3x3``, their
  ``hidden/spec.yaml``) plus the owner's three accepted contract choices (brief 27, 2026-11-10), word for word.
- ``c12_pwm_audio``: the development task ``c12_nexys_pwm_audio``; the user's words are its ``spec.md``, the oracle's
  hidden spec its ``hidden/spec.yaml``, unchanged.

Nothing here reads ``benchmark_private/``, ``eval1/`` or ``_eval1/``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TASKS = ROOT / "benchmark" / "course" / "tasks"

#: brief 27, "Pilot-1 contract choices (owner, 2026-11-10: 'I accept the three contract choices')", word for word
OWNER_CHOICES = ["A full-raster video stream with no back-pressure.",
                 "Median latency H_TOTAL + 2.",
                 "Shell registers at window base 0x00."]


def main() -> None:
    (HERE / "oracle").mkdir(exist_ok=True)
    out = {}
    # pilot 1
    d = HERE / "pilot1" / "system"
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "project" / "examples" / "video_median" / "system" / "spec.md", d / "spec.md")
    hidden = {"name": "video_median_pilot1",
              "owner_contract_choices": OWNER_CHOICES,
              "video_source_task": yaml.safe_load((TASKS / "c9_nexys_vga_720p" / "hidden" / "spec.yaml").read_text()),
              "median_filter_task": yaml.safe_load((TASKS / "c9_median3x3" / "hidden" / "spec.yaml").read_text())}
    p = HERE / "oracle" / "pilot1.yaml"
    p.write_text("# The pilot 1 oracle's hidden spec (results/27b_p1/prepare.py): the owner's accepted choices and the two\n"
                 "# development tasks' hidden/spec.yaml, as data.\n"
                 + yaml.safe_dump(hidden, sort_keys=False, width=10_000, allow_unicode=True))
    out["pilot1"] = p
    # c12
    d = HERE / "c12_pwm_audio" / "system"
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy(TASKS / "c12_nexys_pwm_audio" / "spec.md", d / "spec.md")
    out["c12_pwm_audio"] = TASKS / "c12_nexys_pwm_audio" / "hidden" / "spec.yaml"
    print(json.dumps({k: {"hidden_spec": str(v.relative_to(ROOT)), "sha256": hashlib.sha256(v.read_bytes()).hexdigest()}
                      for k, v in out.items()}, indent=1))


if __name__ == "__main__":
    main()
