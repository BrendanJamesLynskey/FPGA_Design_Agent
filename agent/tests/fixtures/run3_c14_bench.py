"""Fixture: the head of run 3's tests/c14_bench.py (c14_int8_dot_requant, run 20261106-211457-2e65). Importing it raises
cocotb_coverage "CoverPoint must have a parent": the names have no parent prefix such as "top.x"."""


import cocotb
from cocotb_coverage.coverage import CoverPoint, coverage_db


CPB = 8
TO = 2000
STAMP = 0x1234ABCD
M32 = 0xFFFFFFFF

# ---------------------------------------------------------------- functional coverage


@CoverPoint("cov_result_class", xf=lambda v: v,
            bins=["neg_sat", "pos_sat", "relu_zero", "zero", "in_pos", "in_neg"])
def cov_result(v):
    pass


@CoverPoint("cov_rounding_class", xf=lambda v: v, bins=["half_pos", "half_neg", "not_half"])
def cov_round(v):
    pass
