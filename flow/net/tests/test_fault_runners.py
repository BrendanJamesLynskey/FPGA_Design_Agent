"""Each ip_lib entry's seeded faults have one declared runner, and each runner takes only its own blocks.

flow/net/faults.py copies a block's rtl/ and points the tests at it through NET_RTL_<BLOCK>; the hil/ip_faults.py
testbenches do not read that variable, so a fault run by the wrong runner can never be caught (or is "caught" only
because the test errors). The owner is declared in faults.yaml (`runner:`), not kept as a list in either runner."""
from __future__ import annotations

from pathlib import Path

import yaml

from flow.net import faults as net_faults

ROOT = Path(__file__).resolve().parents[3]
RUNNERS = {"flow/net/faults.py", "hil/ip_faults.py"}


def test_every_faults_yaml_declares_a_runner() -> None:
    for f in sorted((ROOT / "ip_lib").glob("*/faults.yaml")):
        y = yaml.safe_load(f.read_text())
        assert y.get("runner") in RUNNERS, f
        assert (ROOT / y["runner"]).exists(), f


def test_net_runner_takes_only_its_blocks() -> None:
    mine = {b for b, _ in net_faults.faults()}
    for f in sorted((ROOT / "ip_lib").glob("*/faults.yaml")):
        owned = yaml.safe_load(f.read_text())["runner"] == "flow/net/faults.py"
        assert (f.parent.name in mine) == owned, f.parent.name
    assert "fir" not in mine


def test_k_expression_with_spaces_stays_one_argument() -> None:
    assert net_faults.pytest_args("ip_lib/fir/tb/test_fir_rtl.py -k test_adversarial and lut_mult") == \
        ["ip_lib/fir/tb/test_fir_rtl.py", "-k", "test_adversarial and lut_mult"]
    assert net_faults.pytest_args("a.py::t b.py") == ["a.py::t", "b.py"]
