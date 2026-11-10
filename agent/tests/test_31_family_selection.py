"""Brief 31: the bank's family units follow the target part in build.yaml, so a K26 design never gets the Artix-7 layer."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent.core import bank as B
from agent.core.registry import dispatch
from agent.core.session import Session, family_for_part, part_of
from agent.tests.conftest import FakeRunner

K26 = "xck26-sfvc784-2LV-c"
A7 = "xc7a100tcsg324-1"


class PartBank:
    """Records what load_skill asks for; takes ``part`` like a brief-31 bank."""

    def __init__(self):
        self.calls = []

    def search(self, query, k=5, sections=None):
        return []

    def skills(self, board, family, sections, primary_only=True, procedures=False, part=None):
        self.calls.append({"family": family, "part": part, "sections": list(sections)})
        return [{"path": "family/x/clocking/s/SKILL.md", "axis": "family", "section": "clocking", "name": "s",
                 "description": "d", "text": "# s"}]


def _design(tmp_path: Path, part: str) -> Path:
    d = tmp_path / "designs" / "d"
    d.mkdir(parents=True)
    (d / "build.yaml").write_text(f"top: top\npart: {part}\nboard: kr260\nsources: []\nconstraints: []\n")
    return d


def test_family_for_part():
    assert family_for_part(A7) == "artix7"
    assert family_for_part("xc7z020clg484-1") == "zynq7000"
    assert family_for_part(K26) == "zynq_ultrascale_plus"
    assert family_for_part("xcvu9p-flga2104-2-i") is None


def test_session_reads_part_from_build_yaml(tmp_path):
    d = _design(tmp_path, K26)
    s = Session(design=d, root=tmp_path, runner=FakeRunner(), bank=PartBank())
    assert part_of(d) == K26 and s.part == K26 and s.family == "zynq_ultrascale_plus"


def test_load_skill_passes_the_part(tmp_path):
    bank = PartBank()
    s = Session(design=_design(tmp_path, K26), root=tmp_path, runner=FakeRunner(), bank=bank)
    assert dispatch(s, "load_skill", {"sections": ["clocking"]})["ok"]
    assert bank.calls[0]["part"] == K26 and bank.calls[0]["family"] == "zynq_ultrascale_plus"


def _real_bank():
    root = Path(os.environ.get("FDA_KNOWLEDGE", B.DEFAULT_BANK))
    if not (root / "tools" / "select_skills.py").exists():
        pytest.skip("the private knowledge bank is not checked out here")
    bank = B.LocalBank(root)
    import inspect
    if "part" not in inspect.signature(bank._select.select).parameters:
        pytest.skip("the checked-out bank predates brief 31 (no part-based selection)")
    return bank


@pytest.mark.parametrize("part,want,never", [
    (A7, "family/artix7/", ("family/zynq_ultrascale_plus/", "family/zynq7000/")),
    (K26, "family/zynq_ultrascale_plus/", ("family/artix7/", "family/zynq7000/")),
])
def test_real_bank_selects_by_part(part, want, never):
    got = [x["path"] for x in _real_bank().skills(None, "artix7", ["clocking", "primitives"], part=part)]
    assert any(p.startswith(want) for p in got), got
    assert not any(p.startswith(n) for p in got for n in never), got
