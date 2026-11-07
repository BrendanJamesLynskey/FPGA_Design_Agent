"""Brief 07a2 fix 5, group A: tests-role conventions and the V1 message for a bench test given method `formal`
(batch 1: c10 four lines, c12 eight lines of ``REQ-0n:formal:<bench>.<test>: not a formal job``)."""

from __future__ import annotations

from pathlib import Path

import yaml

from agent.graph import run as gr
from flow import verif_gates as G

T1 = Path(__file__).resolve().parents[2] / "designs" / "t1_dimmer_counter"


def test_tests_role_conventions_state_the_bench_proof_method_and_random_name() -> None:
    t = gr.tests_conventions_text({"design_rel": "designs/x", "name": "x"})
    assert "proven by method `simulation`" in t and "only for a job in verif/formal" in t
    assert '"random"' in t


def test_v1_message_names_the_valid_methods_for_a_bench_test(tmp_path, monkeypatch) -> None:
    plan = yaml.safe_load((T1 / "verif" / "testplan.yaml").read_text())
    real = yaml.safe_load
    # the c10 mistake: a bench test declared with method formal
    plan["proof"].append({"requirement": "REQ-03", "method": "formal", "artefact": "t1_cocotb.test_reset_values"})
    monkeypatch.setattr(G.yaml, "safe_load", lambda t: plan if "fpga-design-agent/testplan" in t else real(t))
    c = G.evaluate(T1, tmp_path, [], tmp_path, None, None)["stages"]["V1"]["checks"]["proof_references_resolve"]
    msg = " ".join(c["value"])
    assert "t1_cocotb.test_reset_values: not a formal job" in msg
    assert "valid methods: analysis, formal, hardware, simulation" in msg and "`simulation`" in msg
