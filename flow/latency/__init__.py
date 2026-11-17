"""Latency as an agent skill (brief 97): the latency-critical path of a design, as data the agent can reason from.

``latency_path`` joins a design's ``latency_stages.yaml`` (every register and clock crossing on the wire-to-wire chain)
with the simulated clocks of its benches and, when a post-route checkpoint has been read, the slack of each stage's registers.
``latency_budget`` turns that into the table the closure loop reasons from: stage, clocks, ns, why it exists, what removing
it risks, how much could come out, and the board's share that simulation cannot see.

The timing-critical path (worst slack) limits the clock period. The latency-critical path is the chain of registers and
clock crossings from the first bit of the input on the wire to the first bit of the output on the wire; its length is
(registers on it) x (period) plus the GT and optics. See ``model.py``.
"""
