"""Brief 230: the port and clock completeness check on every committed design that has a build.yaml and an XDC (designs that close, mostly).
A finding on a design that closes is a false positive or a real gap, and is listed for reading. Usage: python false_positive_scan.py <out.json>"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from flow import known_constraints as KC  # noqa: E402

rows = []
for b in sorted((ROOT / "designs").glob("**/build.yaml")):
    d = b.parent
    if "/build/" in str(d) or "/lat_" in str(d):
        continue
    try:
        found = KC.findings(d, ROOT)
        ctx = KC.Ctx(d, ROOT)
        n_ports = len(ctx.ports)
    except Exception as e:                    # noqa: BLE001
        rows.append({"design": str(d.relative_to(ROOT)), "error": f"{type(e).__name__}: {e}"[:200]})
        continue
    if not n_ports:
        continue
    rows.append({"design": str(d.relative_to(ROOT)), "top_ports": n_ports, "findings": [f"{f['rule']} {f['text']}" for f in found]})
Path(sys.argv[1]).write_text(json.dumps(rows, indent=1) + "\n")
print(len(rows), "designs read;", sum(1 for r in rows if r.get("findings")), "with findings;", sum(1 for r in rows if "error" in r), "errors")
for r in rows:
    if r.get("findings") or "error" in r:
        print(r["design"], r.get("findings") or r["error"])
