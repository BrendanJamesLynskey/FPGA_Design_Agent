"""The lab tool (brief 221's ``register_tool_action`` slot, filled by brief 225's addendum): ``drive_instrument``.

A request to drive a lab instrument's output into the board. Three checks stand in front of it, in this order:

1. ``agent.core.permissions.never_violation`` (run by ``registry.dispatch`` through ``tool_gate`` before any mode is read) calls
   ``hil.lab.check_drive`` over the lab merged for this design. An over-limit request, an unknown or not-onboarded instrument, an output the lab file
   never lets a script enable, or a value the call does not state is refused as the ``lab_limits`` never-rule in every permission mode, ``full`` included.
2. The run's permission mode: ``drive_instrument_output`` (``plan``: deny; ``ask`` and ``auto``: ask; ``full``: allow).
3. This function checks the request once more (a tool called by code that did not go through ``dispatch`` meets the same limits).

The tool **does not enable an output and opens no instrument**. It writes the approved request to ``build/lab/drive_requests.json``; the output is
enabled only by the owner-run bring-up script (``python -m hil.lab_bringup run``), which runs ``check_drive`` again at run time and needs the owner's typed
confirmation. So even in ``full`` the agent never touches a bench from this tool; the permission and the limits decide what a request may say.
"""

from __future__ import annotations

import json
import time

from agent.core.registry import tool
from agent.core.session import Session
from agent.core import permissions as _perm

_NUM = {"type": "number"}


@tool("drive_instrument",
      "Ask for a lab instrument output (a signal generator, bench supply or similar) to be driven into the board, inside the lab file's safety limits "
      "(hil.lab.check_drive). The request is checked against the lab file and recorded in build/lab/drive_requests.json for the owner-run bring-up script; "
      "nothing is enabled and no instrument is opened here. A value above a limit, an output the lab file never lets a script enable, an instrument that is "
      "not onboarded, or a value the output needs and the request omits, is refused in every permission mode.",
      {"instrument": {"type": "string", "maxLength": 64}, "output": {"type": "string", "maxLength": 64},
       "volts": _NUM, "amps": _NUM, "dbm": _NUM, "hz": _NUM, "attenuator_db": _NUM, "board_vcco_v": _NUM,
       "purpose": {"type": "string", "maxLength": 300}},
      ["instrument", "output"], hardware=True)
def drive_instrument(s: Session, instrument: str, output: str, volts: float | None = None, amps: float | None = None, dbm: float | None = None,
                     hz: float | None = None, attenuator_db: float | None = None, board_vcco_v: float | None = None, purpose: str = "") -> dict:
    args = {"instrument": instrument, "output": output, "volts": volts, "amps": amps, "dbm": dbm, "hz": hz, "attenuator_db": attenuator_db,
            "board_vcco_v": board_vcco_v}
    why = _perm.lab_drive_violation(args, s.design)
    if why:
        raise _perm.NeverRefused("lab_limits", why)
    d = s.design / "build" / "lab"
    d.mkdir(parents=True, exist_ok=True)
    f = d / "drive_requests.json"
    rows = json.loads(f.read_text()) if f.is_file() else []
    rows.append({**{k: v for k, v in args.items() if v is not None}, "purpose": purpose, "checked": time.strftime("%Y-%m-%dT%H:%M:%S"),
                 "status": "approved_within_limits_not_enabled"})
    f.write_text(json.dumps(rows, indent=1) + "\n")
    return {"ok": True, "output": f"{instrument}.{output}: within the lab file's limits; recorded in build/lab/drive_requests.json. Nothing was enabled: "
                                  "the owner-run bring-up script enables it, checks the limits again and asks the owner to confirm.", "request": rows[-1]}


_perm.register_tool_action("drive_instrument", "drive_instrument_output")
