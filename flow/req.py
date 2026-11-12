"""Requirement tags for cocotb tests (brief 53).

    from flow.req import req

    @cocotb.test()
    @req("REQ-03")                       # this test verifies REQ-03 (several ids allowed)
    async def pwm_on_time_matches_duty(dut): ...

    @cocotb.test()
    @req(robustness="malformed frames: the spec says nothing, the shell must not hang")
    async def garbage_frames(dut): ...

The decorator only records the ids on the function; it never changes what the test does. The traceability tool
(flow/trace.py) reads the tags statically from the source, so a comment does the same job where an import is not
wanted:

    # req: REQ-03
    @cocotb.test()
    async def pwm_on_time_matches_duty(dut): ...

A test that verifies no requirement is marked ``robustness`` (behaviour outside the spec: bad inputs, stress) or
``structural`` (it exists to reach code or coverage, for example the coverage dump), each with a reason.
"""

from __future__ import annotations

from typing import Any, Callable

#: the two classes of test or property that cite no requirement (each needs a reason)
CLASSES = ("robustness", "structural")


def req(*ids: str, robustness: str | None = None, structural: str | None = None) -> Callable[[Any], Any]:
    """Tag a test with the requirement ids it verifies, or mark it robustness/structural with a reason."""
    def tag(fn: Any) -> Any:
        try:
            fn.__fda_reqs__ = tuple(ids)
            fn.__fda_class__ = "robustness" if robustness else "structural" if structural else None
            fn.__fda_reason__ = robustness or structural
        except (AttributeError, TypeError):      # a wrapped object that refuses attributes: the static tag still counts
            pass
        return fn
    return tag
