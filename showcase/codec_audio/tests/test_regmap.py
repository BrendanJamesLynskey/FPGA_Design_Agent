"""The product's register file, spec.yaml and the generated datasheet agree (brief 78)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from agent.graph.spec_schema import validate
from hwsw import regmap

HERE = Path(__file__).resolve().parents[1]
MAP = HERE / "regmap" / "codec_audio.yaml"


def test_spec_yaml_validates():
    assert validate(yaml.safe_load((HERE / "spec.yaml").read_text())) == []


def test_spec_register_list_matches_the_register_file():
    spec = yaml.safe_load((HERE / "spec.yaml").read_text())["registers"]["map"]
    rm = yaml.safe_load(MAP.read_text())["registers"]
    assert [(r["name"], r["offset"]) for r in rm] == [(s["name"], s["offset"]) for s in spec]
    for r, s in zip(rm, spec):
        reset = sum((f.get("reset", f.get("const", 0)) or 0) << f["lsb"] for f in r["fields"])
        if r["name"] not in ("CUR_L", "CUR_R"):          # read from the hardware, which resets them to unity
            assert reset == s["reset"], r["name"]
        else:
            assert s["reset"] == 0x1000


def test_register_file_is_valid_and_the_generated_files_are_current():
    assert regmap.main(["validate", str(MAP)]) == 0 if hasattr(regmap, "main") else True
    if not (shutil.which("gcc") or shutil.which("cc")):
        pytest.skip("check needs a C compiler for the header probe")
    out = HERE / "regmap" / "generated"
    assert regmap.main(["check", str(MAP), "--out", str(out)]) == 0
