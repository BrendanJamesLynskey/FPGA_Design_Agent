"""Brief 42 H2: a static check for cocotb benches that can hang, and the wall-clock limit of a simulation.

``unbounded_waits`` finds ``while`` loops that wait on simulation events with nothing bounding them (brief 24 B1: three
1800 s hangs on ``while`` waits in the agent's own bench). A loop is accepted when

- it is a ``while True`` with no ``break`` or ``return`` outside a test (a clock driver, monitor or model process that
  nothing awaits; cocotb ends it with the test),
- its condition compares a counter the body changes (``while n < MAX: ... n += 1``),
- its body has an ``if`` on a counter the body changes that ends in ``break``, ``return``, ``raise`` or ``assert``,
- it sits in a test declared with ``timeout_time=`` (cocotb ends it in simulation time), or
- the file uses ``with_timeout``.

Heuristic and syntactic: it looks only at the file it reads.
"""

from __future__ import annotations

import ast
from pathlib import Path

_EVENT_WAITS = {"RisingEdge", "FallingEdge", "Edge", "ClockCycles", "ReadOnly", "ReadWrite", "NextTimeStep", "Timer",
                "Combine", "First", "Event"}
_CMP = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)


def _call_name(n: ast.AST) -> str:
    f = n.func if isinstance(n, ast.Call) else n
    return f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""


def _is_test(fn: ast.AsyncFunctionDef | ast.FunctionDef) -> tuple[bool, bool]:
    """(is a @cocotb.test, declares timeout_time)."""
    for d in fn.decorator_list:
        if _call_name(d) == "test" and (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                                        and getattr(d.func.value, "id", "") == "cocotb" or _call_name(d) == "test"):
            has_t = isinstance(d, ast.Call) and any(k.arg in ("timeout_time", "timeout") for k in d.keywords)
            return True, has_t
    return False, False


def _changed_names(body: list[ast.stmt]) -> set[str]:
    out = set()
    for n in ast.walk(ast.Module(body=body, type_ignores=[])):
        if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name):
            out.add(n.target.id)
        elif isinstance(n, ast.Assign):
            out.update(t.id for t in n.targets if isinstance(t, ast.Name))
    return out


def _names(n: ast.AST) -> set[str]:
    return {x.id for x in ast.walk(n) if isinstance(x, ast.Name)}


def _bounded(loop: ast.While) -> bool:
    changed = _changed_names(loop.body)
    t = loop.test
    if isinstance(t, ast.Compare) and any(isinstance(o, _CMP) for o in t.ops) and _names(t) & changed:
        return True
    for n in ast.walk(ast.Module(body=loop.body, type_ignores=[])):
        if isinstance(n, ast.If) and isinstance(n.test, ast.Compare) and _names(n.test) & changed:
            if any(isinstance(x, (ast.Break, ast.Return, ast.Raise, ast.Assert)) for b in n.body for x in ast.walk(b)):
                return True
    return False


def _own_loops(fn: ast.AST) -> list[ast.While]:
    """The ``while`` loops of ``fn`` itself, not those of functions defined inside it."""
    out, stack = [], list(ast.iter_child_nodes(fn))
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        if isinstance(n, ast.While):
            out.append(n)
        stack.extend(ast.iter_child_nodes(n))
    return out


def unbounded_waits(path: Path) -> list[dict]:
    """Unbounded event-waiting ``while`` loops in one Python file: ``[{file, line, function, loop, waits}]``."""
    src = Path(path).read_text(errors="replace")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []                                    # the import check reports a syntax error
    if "with_timeout" in src:
        return []
    out = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        is_test, has_timeout = _is_test(fn)
        if has_timeout:
            continue
        for loop in sorted(_own_loops(fn), key=lambda x: x.lineno):
            waits = {_call_name(a.value) for a in ast.walk(loop) if isinstance(a, ast.Await)} & _EVENT_WAITS
            if not waits:
                continue
            if _bounded(loop):
                continue
            forever = isinstance(loop.test, ast.Constant) and loop.test.value is True and not any(
                isinstance(x, (ast.Break, ast.Return)) for b in loop.body for x in ast.walk(b))
            if forever and not is_test:
                continue                             # a monitor or model process: nothing awaits its end
            out.append({"file": str(path), "line": loop.lineno, "function": fn.name,
                        "loop": ast.get_source_segment(src, loop.test) or "", "waits": sorted(waits)})
    seen, uniq = set(), []
    for o in out:                                    # nested functions are walked twice
        k = (o["line"], o["function"])
        if k not in seen:
            seen.add(k)
            uniq.append(o)
    return uniq


def refusal_text(findings: list[dict], design: Path) -> str:
    rows = "\n".join(f"  {Path(f['file']).relative_to(design) if Path(f['file']).is_relative_to(design) else f['file']}:{f['line']} "
                     f"in {f['function']}: `while {f['loop']}` waits on {', '.join(f['waits'])} with no bound" for f in findings)
    return ("The simulation did not start: the bench has a wait loop with no bound, which can hang the simulator until the "
            "tool's time limit.\n" + rows + "\nBound each one: `for _ in range(MAX_CYCLES)` with an assert after it, a counter "
            "that is checked inside the loop, `cocotb.triggers.with_timeout(...)`, or `@cocotb.test(timeout_time=..., "
            "timeout_unit=\"us\")` on the test.")


_UNIT_NS = {"fs": 1e-6, "ps": 1e-3, "ns": 1.0, "us": 1e3, "ms": 1e6, "sec": 1e9, "s": 1e9}


def declared_budget_ns(tests_dir: Path) -> float | None:
    """The sum of the ``timeout_time`` of every ``@cocotb.test`` under tests_dir in ns, or None when any test has none
    or a value that is not a number and a unit literal."""
    total, n = 0.0, 0
    for f in sorted(Path(tests_dir).rglob("*.py")):
        try:
            tree = ast.parse(f.read_text(errors="replace"))
        except SyntaxError:
            return None
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.AsyncFunctionDef, ast.FunctionDef)) and _is_test(fn)[0]:
                kw = {}
                for d in fn.decorator_list:
                    if isinstance(d, ast.Call):
                        kw = {k.arg: k.value for k in d.keywords}
                t, u = kw.get("timeout_time"), kw.get("timeout_unit")
                if not (isinstance(t, ast.Constant) and isinstance(t.value, (int, float))
                        and isinstance(u, ast.Constant) and u.value in _UNIT_NS):
                    return None
                total += t.value * _UNIT_NS[u.value]
                n += 1
    return total if n else None


H2_MIN, H2_MAX, H2_DEFAULT = 180, 900, 600
NS_PER_WALL_S = 1e5            # conservative simulation speed: Icarus runs about 1e5 clock cycles per second at a 10 ns clock


def h2_wall_limit(tests_dir: Path, baseline_s: float | None, coverage: bool = False) -> tuple[int, str]:
    """The wall-clock limit of one ``simulate`` call and where it came from: the declared simulation-time budget
    (``120 s + budget / 1e5 ns per second``) when every test declares one, else 4 x the last passing run + 120 s, else
    600 s; always within 180..900 s, doubled with coverage."""
    b = declared_budget_ns(tests_dir)
    if b is not None:
        lim, why = 120 + b / NS_PER_WALL_S, f"declared simulation-time budget {b:.0f} ns"
    elif baseline_s is not None:
        lim, why = 4 * baseline_s + 120, f"4 x the last passing run ({baseline_s:.0f} s) + 120 s"
    else:
        lim, why = H2_DEFAULT, "default"
    lim = min(H2_MAX, max(H2_MIN, lim)) * (2 if coverage else 1)
    return int(lim), why
