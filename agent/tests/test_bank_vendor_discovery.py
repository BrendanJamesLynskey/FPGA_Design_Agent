"""The bank reads every sectioned vendor unit it holds, found from the bank's own layout (no hard-coded list).

Brief 20 found ``VENDOR_SETS = ("ross_distilled", "amd_constraints")`` left ``amd_ip_cores``, ``amba_axi``, ``vivado_synthesis`` and
``free_simulators`` unread. These tests fail if a sectioned vendor unit exists in the bank but its skills do not reach ``skills``."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.core.bank import DEFAULT_BANK, LocalBank, vendor_units


def _make(root: Path, unit: str, section: str, skill: str = "s") -> None:
    d = root / "vendor" / unit / section / skill
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("# t\n")


def test_vendor_units_come_from_the_layout_and_leave_out_unsectioned(tmp_path) -> None:
    for u in ("zeta_new", "ross_distilled", "amd_constraints", "alpha_new"):
        _make(tmp_path, u, "constraints")
    (tmp_path / "vendor" / "ross_shipped" / "skills" / "x").mkdir(parents=True)          # as AMD ships it: not sectioned
    (tmp_path / "vendor" / "ross_shipped" / "skills" / "x" / "SKILL.md").write_text("# t\n")
    (tmp_path / "vendor" / "empty_unit").mkdir()
    got = vendor_units(tmp_path)
    assert set(got) == {"zeta_new", "ross_distilled", "amd_constraints", "alpha_new"}
    assert got[:2] == ["ross_distilled", "amd_constraints"] and got[2:] == ["alpha_new", "zeta_new"]   # earlier-read first


def test_a_new_vendor_unit_is_read_without_a_code_change(tmp_path) -> None:
    for u in ("ross_distilled", "brand_new_unit"):
        _make(tmp_path, u, "constraints")
    calls = []

    class Skill:
        def __init__(self, path):
            self.path, self.axis, self.section, self.name, self.description = path, "vendor", "constraints", "n", "d"

    class Select:
        def select(self, **kw):
            calls.append(kw.get("vendor"))
            return [Skill(f"vendor/{kw['vendor']}/constraints/s/SKILL.md")] if kw.get("vendor") else []

    b = object.__new__(LocalBank)
    b.root, b._select = tmp_path, Select()
    got = b.skills(None, None, ["constraints"])
    assert [c for c in calls if c] == ["ross_distilled", "brand_new_unit"]
    assert {g["path"].split("/")[1] for g in got} == {"ross_distilled", "brand_new_unit"}


def test_every_sectioned_vendor_unit_of_the_real_bank_is_read() -> None:
    if not (DEFAULT_BANK / "tools" / "select_skills.py").exists():
        pytest.skip("no knowledge bank checkout")
    bank = LocalBank(DEFAULT_BANK)
    on_disk = sorted(u.name for u in (DEFAULT_BANK / "vendor").iterdir()
                     if u.is_dir() and u.name != "ross_shipped" and any(u.glob("*/*/SKILL.md")))   # independent of vendor_units
    assert on_disk, "the bank holds no sectioned vendor unit"
    unread = []
    for unit in on_disk:
        sections = sorted({p.parent.parent.name for p in (DEFAULT_BANK / "vendor" / unit).glob("*/*/SKILL.md")})
        got = {x["path"].split("/")[1] for x in bank.skills(None, None, sections) if x["path"].startswith("vendor/")}
        if unit not in got:
            unread.append(unit)
    assert not unread, f"sectioned vendor units in the bank that the agent never reads: {unread}"
    assert set(vendor_units(DEFAULT_BANK)) == set(on_disk)
