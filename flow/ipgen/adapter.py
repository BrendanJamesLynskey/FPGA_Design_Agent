"""The ipgen adapter interface (brief 19, section 4). One adapter per IP; `run.py` drives them all the same way.

An adapter turns a plain-number spec into everything the common pipeline needs. Subclass `IpAdapter`, fill the hooks,
register the class in `run.ADAPTERS`. The pipeline never knows which IP it is running.
"""
from __future__ import annotations

from pathlib import Path


class IpAdapter:
    #: short name, used as the results directory and the module name of the IP instance
    name = "ip"
    #: words for Vivado's create_ip (name, vendor, library, version)
    create_args = ""
    #: the IP's clock port and its AXI-Stream widths are read from the generated VHDL by the pipeline when this is True
    clock_port = "aclk"
    #: which stages of the pipeline apply (all three for a data-path core)
    can_simulate = True

    # ---- 1. the Python design tool -------------------------------------------------------------------------------
    def design(self, spec: dict) -> dict:
        """spec -> design (a dict with a JSON-safe summary under 'summary' and anything else the later hooks need)."""
        raise NotImplementedError

    def design_artifacts(self, spec: dict, design: dict, outdir: Path) -> dict:
        """Write data files the IP reads (a .coe, a table, a .prj) and plot data. Return {name: path}."""
        return {}

    # ---- 2. the IP configuration ---------------------------------------------------------------------------------
    def props(self, spec: dict, design: dict, artifacts: dict) -> list:
        """Flat [name, value, name, value, ...] of CONFIG.* settings for set_property."""
        raise NotImplementedError

    def predicted(self, spec: dict, design: dict) -> dict:
        """What the Python tool predicts the IP will report (widths, gain, ...), to compare with the read-back."""
        return {}

    def readback_keys(self) -> list:
        """CONFIG.* names (read-back) and generated model parameters (from the .xci) worth recording."""
        return []

    # ---- 3. simulation ---------------------------------------------------------------------------------------------
    def dut_inst(self, module: str, ports: dict) -> str:
        """SystemVerilog instance of the IP using the testbench's fixed signal names (see tb_axis_io.sv.tmpl)."""
        raise NotImplementedError

    def stimulus(self, spec: dict, design: dict):
        """-> (list of input samples, input width in bits)."""
        raise NotImplementedError

    def check(self, spec: dict, design: dict, samples, resp: dict, out_w: int) -> dict:
        """Compare the response (harness.read_response) against the bit-accurate Python golden model. Must return a dict
        with at least 'match' (bool)."""
        raise NotImplementedError
