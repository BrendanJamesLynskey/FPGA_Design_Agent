"""Agent tool for brief 104: ``design_analysis``, the read-only analysis a strategy proposal starts from (components with ownership, latency by stage,
timing, resources per component, clock crossings, gaps). It reads existing records in the design's own directory and never builds, simulates or edits."""
from __future__ import annotations

from agent.core.registry import tool
from agent.core.session import Session


@tool("design_analysis", "Read-only analysis of this design from records that already exist: components with ownership, the latency budget by stage (when the design "
      "declares its chain), WNS/WHS and the worst path, LUT and FF per component, clock crossings, and what is missing. Excluded components are not shown. It starts "
      "no build; with no reports it says so. Strategy options for a request are made by `python -m agent improve`, not by this tool.", {})
def design_analysis(s: Session) -> dict:
    from flow.options import analysis as A
    from flow.options.cli import _render_analysis
    try:
        an = A.analyse(s.design)
    except (ValueError, OSError, KeyError) as e:
        return {"ok": False, "output": f"design_analysis: {e}"}
    return {"ok": True, "output": _render_analysis(an), "analysis_hash": an["hash"]}
