"""Brief 62A: deterministic report digests for the closure loop (agent/graph/closure.py). No model inside.

Each parser turns one Vivado report into a compact, typed record the closure controller and the repair prompt read:

- :mod:`flow.digest.timing`: the worst setup (or hold) path of ``report_timing``: slack, logic and route delay, logic levels
  by cell type, each cell and net fanout on the path, and the RTL register names at both ends; plus the path's *features*
  (a carry chain built from LUTs where a DSP would do, a high-fanout net, a route-dominated path) that pick the repair.
- :mod:`flow.digest.utilization`: ``report_utilization -hierarchical`` by instance.
- :mod:`flow.digest.power`: ``report_power`` on-chip components and the by-hierarchy table.
- :mod:`flow.digest.synth`: the synthesis messages that break area closure (inferred latches, RAM implemented in registers).
- :mod:`flow.digest.build`: all of the above for one build directory, as a dict and as a short text for the model.

The existing H9 digests (``agent/core/report_digest.py``, brief 42) summarise a report for the agent's ``report_digest``
tool; these go one level deeper on the reports the closure playbook needs (cells and fanouts of the critical path,
utilisation and power by hierarchy).
"""

from flow.digest.build import digest_build, digest_text  # noqa: F401
