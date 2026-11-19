"""The health panel: live checks, each with a status, the time it was checked and how it was checked.

Free checks (reading a file, a version query of a local tool, the USB device list in sysfs) run whenever the panel is opened and are cached for
a minute. A check that spends tokens, calls GitHub, or touches the hardware server is an **action**: it runs only on a click (a POST that
the server accepts only with the session token), never on its own. Nothing here prints a key or token: key *presence* is all it reads.

Statuses: ``ok``, ``warn``, ``fail``, ``unknown`` (could not be checked; the detail says why) and ``not-run`` (an action no one has clicked).
"""

from __future__ import annotations

import datetime as dt
import threading
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

import yaml

from navigator import redact

USAGE_STOP_PCT = 88            # the owner's stop line for weekly (all models) usage
USAGE_WARN_PCT = 80
USAGE_STALE_H = 6
LOAD_LIMIT = 6                 # house rules: a second heavy job only while the load is under 6 ...
FREE_GB_SLOT2 = 12             # ... and more than 12 GB is free
DISK_WARN_GB = 20
USB_VENDORS = {"0403": "FTDI", "03fd": "AMD (Xilinx)", "1443": "Digilent", "09fb": "Intel (Altera)"}


class Runner:
    """The only way the navigator starts a process: a fixed argv (no shell), a timeout, output captured. Tests pass a fake."""

    def run(self, argv: list[str], timeout: float = 20, cwd: Path | None = None, env: dict[str, str] | None = None) -> tuple[int, str, str]:
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=env)
        except FileNotFoundError:
            return 127, "", f"{argv[0]}: not found"
        except subprocess.TimeoutExpired:
            return 124, "", f"{argv[0]}: timed out after {timeout:.0f} s"
        return p.returncode, p.stdout, p.stderr


def _last4(serial: Any) -> str | None:
    """Only the last 4 characters of a cable serial are ever shown."""
    return "..." + str(serial)[-4:] if serial else None


def now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def chk(id: str, group: str, title: str, status: str, detail: str, how: str, **extra: Any) -> dict[str, Any]:
    return {"id": id, "group": group, "title": title, "status": status, "detail": redact.text(detail), "how": how, "checked_at": now(), **extra}


class Health:
    def __init__(self, root: Path, handoff: Path, runner: Runner | None = None, config_dir: Path | None = None, sysfs_usb: Path = Path("/sys/bus/usb/devices"),
                 python: str = "python3", cache_s: float = 60.0):
        self.root, self.handoff, self.runner = Path(root), Path(handoff), runner or Runner()
        self.config_dir = config_dir if config_dir is not None else Path.home() / ".config" / "fpga_design_agent"
        self.sysfs_usb, self.python, self.cache_s = sysfs_usb, python, cache_s
        self._cache: dict[str, tuple[float, Any]] = {}
        self.actions_run: dict[str, dict[str, Any]] = {}
        self._locks = {a: threading.Lock() for a in self.ACTIONS}

    def _cached(self, key: str, fn: Callable[[], Any]) -> Any:
        t = time.monotonic()
        hit = self._cache.get(key)
        if hit and t - hit[0] < self.cache_s:
            return hit[1]
        v = fn()
        self._cache[key] = (t, v)
        return v

    # -- LLMs -----------------------------------------------------------------------------------------------------------------------
    def claude_cli(self) -> list[dict[str, Any]]:
        rc, out, err = self.runner.run(["claude", "--version"], timeout=10)
        v = chk("claude_cli", "LLM availability", "Claude Code CLI", "ok" if rc == 0 and out.strip() else "fail",
                out.strip().splitlines()[0] if rc == 0 and out.strip() else f"not available: {redact.brief(err or out)}", "claude --version (a local version query; no model call)")
        rc, out, err = self.runner.run(["claude", "auth", "status", "--json"], timeout=15)
        a = None
        try:
            a = json.loads(out)
        except ValueError:
            pass
        if isinstance(a, dict):
            exp = str(a.get("loginExpiresAt") or "")[:10]
            ok = bool(a.get("loggedIn"))
            detail = (f"signed in ({a.get('authMethod')}, provider {a.get('apiProvider')}); sign-in expires {exp}" if ok else "not signed in") if exp or not ok else \
                f"signed in ({a.get('authMethod')}, provider {a.get('apiProvider')})"
            s = dt.date.fromisoformat(exp) if re.match(r"\d{4}-\d\d-\d\d$", exp) else None
            status = "ok" if ok else "fail"
            if ok and s is not None and (s - dt.date.today()).days < 3:
                status = "warn"
        else:
            status, detail = "unknown", f"could not read the sign-in state: {redact.brief(err or out)}"
        au = chk("claude_auth", "LLM availability", "Claude Code sign-in", status, detail, "claude auth status (local; only logged-in state, method, provider and expiry are read: never the account or token)")
        return [v, au]

    def key_state(self, key_env: str | None) -> str:
        """Presence only: whether the variable the endpoint names is set (or the owner's mode-600 key file exists); the value is never read into a response."""
        if not key_env:
            return "no key needed (subscription CLI)"
        present = bool(os.environ.get(key_env)) or (key_env == "OPENROUTER_API_KEY" and (self.config_dir / "openrouter.env").is_file())
        return "key present" if present else "key MISSING"

    def models_view(self) -> dict[str, Any]:
        """Brief 108's resolved model table, as ``python -m agent models show`` prints it: one row per purpose with where each value came from."""
        how = "python -m agent models show (--json for the values, the text form for the layer each came from; brief 108's resolver, no endpoint is called)"
        rc, out, err = self.runner.run([self.python, "-m", "agent", "models", "show", "--json"], timeout=60, cwd=self.root)
        try:
            rec = json.loads(out)
            tab = rec["purposes"]
        except (ValueError, KeyError, TypeError):
            return {"error": f"could not read the table: {redact.brief(err or out)}", "how": how, "checked_at": now()}
        rc2, txt, _ = self.runner.run([self.python, "-m", "agent", "models", "show"], timeout=60, cwd=self.root)
        frm: dict[str, str] = {}
        for ln in txt.splitlines():
            m = re.match(r"(\S+)\s+.*\[([^\]]+)\]", ln)
            if m and not ln.startswith(("purpose", "table hash")):
                frm[m.group(1)] = m.group(2)
        rows = []
        for name, e in tab.items():
            rows.append({"name": name, "purpose": e.get("purpose"), "stage": e.get("stage"), "endpoint": e.get("endpoint"), "kind": e.get("kind"), "model": e.get("model"),
                         "options": e.get("options") or {}, "from": frm.get(name, "builtin"), "key_env": e.get("key_env"), "key_state": self.key_state(e.get("key_env")),
                         "note": e.get("deployment_note") or ""})
        return {"table": rows, "hash": rec.get("hash"), "layers": rec.get("layers") or [], "how": how, "checked_at": now()}

    def models(self) -> list[dict[str, Any]]:
        v = self._cached("models_view", self.models_view)
        how = "python -m agent models show --json (brief 108's resolver; reads the model files, calls no endpoint); only whether a key is present is checked"
        if "error" in v:
            return [chk("models_table", "LLM availability", "Resolved model table", "unknown", v["error"], how)]
        eps: dict[str, dict[str, Any]] = {}
        for r in v["table"]:
            if r["model"] is None:
                continue
            ep = eps.setdefault(r["endpoint"], {"endpoint": r["endpoint"], "kind": r["kind"], "models": set(), "purposes": [], "key_state": r["key_state"]})
            ep["models"].add(r["model"])
            ep["purposes"].append(r["name"])
        rows = [{**e, "models": sorted(e["models"])} for e in eps.values()]
        worst = "warn" if any("MISSING" in e["key_state"] for e in rows) else "ok"
        return [chk("models_table", "LLM availability", "Providers the agent is configured for", worst,
                    "; ".join(f"{e['endpoint']} ({e['kind']}): {', '.join(e['models'])}, {e['key_state']}" for e in rows) or "no purpose has a model", how, endpoints=rows)]

    def usage(self) -> dict[str, Any]:
        f = self.handoff / "usage_log.txt"
        how = "last line of _handoff/usage_log.txt, written by _handoff/usage_check.sh (0 tokens); a click re-reads it live"
        try:
            last = [ln for ln in f.read_text().splitlines() if ln.strip()][-1]
        except (OSError, IndexError):
            return chk("usage", "Weekly usage", "Weekly usage (all models)", "unknown", "no usage_log.txt line yet; run the usage check", how, stop_pct=USAGE_STOP_PCT)
        m = re.match(r"(\d{4}-\d\d-\d\d \d\d:\d\d)\s+", last)
        w = re.search(r"Current week \(all models\):\s*(\d+)% used", last)
        if not (m and w):
            return chk("usage", "Weekly usage", "Weekly usage (all models)", "unknown", "the last line of usage_log.txt is not in the expected format", how, stop_pct=USAGE_STOP_PCT)
        age_h = (dt.datetime.now() - dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M")).total_seconds() / 3600
        pct = int(w.group(1))
        status = "fail" if pct >= USAGE_STOP_PCT else "warn" if pct >= USAGE_WARN_PCT or age_h > USAGE_STALE_H else "ok"
        reset = re.search(r"resets ([^;]+)", last)
        detail = f"{pct}% of the week used (stop line {USAGE_STOP_PCT}%), read {m.group(1)}, {age_h:.1f} h ago" + (f"; resets {reset.group(1)}" if reset else "") + \
                 ("; the reading is stale: click to re-read" if age_h > USAGE_STALE_H else "")
        return chk("usage", "Weekly usage", "Weekly usage (all models)", status, detail, how, percent=pct, stop_pct=USAGE_STOP_PCT, age_hours=round(age_h, 1))

    # -- tools ----------------------------------------------------------------------------------------------------------------------
    def _tool_version(self, argv: list[str], pat: str = r"[\d][\w.+-]*") -> tuple[str | None, str]:
        rc, out, err = self.runner.run(argv, timeout=10)
        if rc == 127:
            return None, "not installed"
        text = (out or err).strip().splitlines()
        m = re.search(pat, text[0]) if text else None
        return (m.group(0) if m else None), (text[0][:100] if text else "no output")

    def _oss_bin(self) -> Path | None:
        cand = [os.environ.get("FDA_OSS_CAD"), str(Path.home() / ".local/opt/oss-cad-suite")]
        for c in cand:
            if c and (Path(c) / "bin").is_dir():
                return Path(c) / "bin"
        return None

    def tools(self) -> list[dict[str, Any]]:
        from flow import version_pin as VP
        from flow import rapidwright_pin as RW
        out = []
        g = "Tools"
        # Vivado: the install directory, never started (it is a heavy job); the licence tier from the recorded probe
        vp = Path(VP.vivado_path({}))
        have = vp.is_file()
        probe = self._load(self.root / "results/95_boards/licence_probe.json")
        tier = (probe or {}).get("licence")
        out.append(chk("vivado", g, "Vivado", "ok" if have else "fail",
                       f"pinned {VP.DEFAULT_VIVADO_VERSION}; installed: {'present' if have else 'MISSING'} at {vp.parent.parent.parent.name if have else vp}; "
                       f"licence tier: {tier or 'not recorded'} (from results/95_boards/licence_probe.json)",
                       "the install path under /opt/Xilinx (Vivado itself is not started: it is a heavy job); the tier is read from the committed probe record",
                       pinned=VP.DEFAULT_VIVADO_VERSION, installed=VP.DEFAULT_VIVADO_VERSION if have else None))
        # OSS CAD Suite
        pin = None
        try:
            m = re.search(r"oss-cad-suite-(\d{8})", (self.root / ".github/workflows/ci.yml").read_text())
            pin = m.group(1) if m else None
        except OSError:
            pass
        bindir = self._oss_bin()
        for name, argv in (("yosys", ["yosys", "-V"]), ("eqy", ["eqy", "--help"]), ("sby", ["sby", "--help"])):
            if bindir is None:
                out.append(chk(name, g, name, "fail", f"OSS CAD Suite not found (set FDA_OSS_CAD or install under ~/.local/opt/oss-cad-suite); CI pins {pin}",
                               "looked for $FDA_OSS_CAD/bin and ~/.local/opt/oss-cad-suite/bin", pinned=f"OSS CAD Suite {pin}", installed=None))
                continue
            exe = bindir / name
            if name == "yosys":
                v, line = self._tool_version([str(exe), "-V"])
                detail = f"pinned OSS CAD Suite {pin}; installed: {line}"
                status = "ok" if v else "fail"
            else:
                status = "ok" if exe.is_file() else "fail"
                detail = f"pinned OSS CAD Suite {pin}; {'present' if exe.is_file() else 'MISSING'} in {bindir}"
            out.append(chk(name, g, name, status, detail, f"{'yosys -V' if name == 'yosys' else 'the executable in the suite directory'} (a local version query)",
                           pinned=f"OSS CAD Suite {pin}", installed=None))
        tools_yaml = self._load(self.config_dir / "tools.yaml", yml=True) or {}
        vroot = (tools_yaml.get("env") or {}).get("VERILATOR_ROOT")
        vpin = re.search(r"verilator-(\d)(\d+)", vroot or "")
        vpinned = f"{vpin.group(1)}.{vpin.group(2)}" if vpin else None
        vb = Path(os.path.expanduser(str((tools_yaml.get("path") or [""])[0]))) / "verilator" if tools_yaml.get("path") else None
        v, line = self._tool_version([str(vb) if vb and vb.exists() else "verilator", "--version"])
        out.append(chk("verilator", g, "Verilator", "ok" if v and (not vpinned or v.startswith(vpinned)) else "warn" if v else "fail",
                       f"pinned {vpinned or 'not recorded'} (from ~/.config/fpga_design_agent/tools.yaml); installed: {line}", "verilator --version (a local version query)",
                       pinned=vpinned, installed=v))
        v, line = self._tool_version(["iverilog", "-V"], r"version\s+([\d.]+)")
        out.append(chk("icarus", g, "Icarus Verilog", "ok" if v else "fail", f"pinned: not pinned (CI installs the distribution package); installed: {line}", "iverilog -V",
                       pinned=None, installed=v))
        out.append(self._py("cocotb", "cocotb", g))
        have_rw, why = RW.available()
        out.append(chk("rapidwright", g, "RapidWright and Java", "ok" if have_rw else "unknown",
                       f"pinned RapidWright {RW.RAPIDWRIGHT_VERSION} with the JRE of Vivado {RW.VIVADO_VERSION}; " + ("both present" if have_rw else f"not present here: {why}"),
                       "whether the venv and the JRE exist (neither is started)", pinned=RW.RAPIDWRIGHT_VERSION, installed=RW.RAPIDWRIGHT_VERSION if have_rw else None))
        return out

    def _py(self, dist: str, pretty: str, group: str) -> dict[str, Any]:
        from importlib import metadata
        pin = None
        try:
            m = re.search(rf"{dist}==([\d.]+)", (self.root / "pyproject.toml").read_text())
            pin = m.group(1) if m else None
        except OSError:
            pass
        try:
            v = metadata.version(dist)
        except metadata.PackageNotFoundError:
            v = None
        status = "fail" if v is None else "ok" if pin in (None, v) else "warn"
        return chk(dist, group, pretty, status, f"pinned {pin or 'not pinned'} (pyproject.toml); installed: {v or 'not installed'}", "the installed package's metadata", pinned=pin, installed=v)

    def _load(self, p: Path, yml: bool = False) -> Any:
        try:
            t = p.read_text()
            return yaml.safe_load(t) if yml else json.loads(t)
        except (OSError, ValueError, yaml.YAMLError):
            return None

    # -- resources ------------------------------------------------------------------------------------------------------------------
    def locks(self) -> list[dict[str, Any]]:
        out = []
        how = "the lock file's text and age (_handoff/heavy_slot.lock and heavy_slot2.lock)"
        for name, title in (("heavy_slot.lock", "Heavy slot 1"), ("heavy_slot2.lock", "Heavy slot 2")):
            f = self.handoff / name
            if not f.is_file():
                out.append(chk(name, "Resources", title, "ok", "free", how))
                continue
            text = f.read_text().strip()[:300]
            age = (time.time() - f.stat().st_mtime) / 3600
            m = re.search(r"expected end (\d{1,2}):(\d\d)", text)
            status, note = "ok", ""
            if m:
                end = dt.datetime.fromtimestamp(f.stat().st_mtime).replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
                if end < dt.datetime.fromtimestamp(f.stat().st_mtime):
                    end += dt.timedelta(days=1)
                if dt.datetime.now() > end + dt.timedelta(minutes=30):
                    status, note = "warn", f"; STALE? it is more than 30 min past its expected end ({m.group(1)}:{m.group(2)})"
            elif age > 6:
                status, note = "warn", "; STALE? older than 6 h and it names no expected end"
            out.append(chk(name, "Resources", title, status, f"held: {text} (taken {age:.1f} h ago){note}", how, lock_text=text))
        return out

    def memory_load_disk(self) -> list[dict[str, Any]]:
        out = []
        try:
            mem = {k: int(v.split()[0]) for k, v in (ln.split(":", 1) for ln in Path("/proc/meminfo").read_text().splitlines())}
            free_gb = mem["MemAvailable"] / 1048576
            load = float(Path("/proc/loadavg").read_text().split()[0])
            s = "ok" if free_gb > FREE_GB_SLOT2 and load < LOAD_LIMIT else "warn"
            out.append(chk("mem_load", "Resources", "Memory and load", s,
                           f"{free_gb:.1f} GB available (a second heavy job needs more than {FREE_GB_SLOT2} GB), load {load:.1f} (needs under {LOAD_LIMIT})",
                           "/proc/meminfo MemAvailable and /proc/loadavg against the owner's admission rule", free_gb=round(free_gb, 1), load=load))
        except (OSError, KeyError, ValueError):
            out.append(chk("mem_load", "Resources", "Memory and load", "unknown", "/proc is not readable here", "/proc/meminfo and /proc/loadavg"))
        for label, p in (("repository disk", self.root), ("home disk", Path.home())):
            try:
                du = shutil.disk_usage(p)
                free = du.free / 1e9
                out.append(chk("disk_" + label.split()[0], "Resources", f"Free space ({label})", "ok" if free > DISK_WARN_GB else "warn",
                               f"{free:.0f} GB free of {du.total / 1e9:.0f} GB", f"shutil.disk_usage on {p.name or p}", free_gb=round(free, 1)))
            except OSError:
                pass
        return out

    # -- boards ---------------------------------------------------------------------------------------------------------------------
    def boards(self) -> list[dict[str, Any]]:
        out = []
        f = self.config_dir / "boards.yaml"
        bd = (self._load(f, yml=True) or {}).get("boards") or {}
        rows = [{"board": n, "part": b.get("part"), "power": b.get("power_source"), "discovered": str(b.get("discovered") or "")[:10], "cable": _last4(b.get("cable_serial"))}
                for n, b in bd.items() if isinstance(b, dict)]
        out.append(chk("boards_file", "Boards", "Local board list", "ok" if rows else "warn",
                       ", ".join(f"{r['board']} ({r['part']}, {r['power']} power, cable {r['cable']})" for r in rows) or "no boards.yaml: run flow/hw_discover.py",
                       "~/.config/fpga_design_agent/boards.yaml (serials cut to the last 4 characters)", boards=rows))
        bl = self.handoff / "board.lock"
        if bl.is_file():
            out.append(chk("board_lock", "Boards", "Board lock", "warn", f"held: {bl.read_text().strip()[:240]}", "_handoff/board.lock text", held=True))
        else:
            out.append(chk("board_lock", "Boards", "Board lock", "ok", "free: no board job is running", "_handoff/board.lock text", held=False))
        out.append(self.usb())
        out.append(chk("jtag_disabled", "Boards", "JTAG target listing", "not-run", "disabled in stage 1: a listing starts the hardware server and Vivado, so it needs board.lock and a heavy slot (stage 2)",
                       "no navigator code path starts the hardware server or Vivado"))
        return out

    def usb(self) -> dict[str, Any]:
        found = []
        try:
            for d in sorted(self.sysfs_usb.iterdir()):
                v = (d / "idVendor")
                if not v.is_file():
                    continue
                vid = v.read_text().strip().lower()
                if vid in USB_VENDORS:
                    prod = (d / "product").read_text().strip() if (d / "product").is_file() else "?"
                    ser = (d / "serial").read_text().strip() if (d / "serial").is_file() else ""
                    found.append({"vendor": USB_VENDORS[vid], "product": prod, "serial": ("..." + ser[-4:]) if ser else None})
        except OSError:
            return chk("usb", "Boards", "USB JTAG or serial cable", "unknown", "the USB device list is not readable here", "/sys/bus/usb/devices (a passive listing; nothing is opened)")
        return chk("usb", "Boards", "USB JTAG or serial cable", "ok" if found else "warn",
                   "; ".join(f"{x['vendor']} {x['product']} ({x['serial'] or 'no serial'})" for x in found) or "no FTDI, AMD, Digilent or Intel USB device is visible",
                   "/sys/bus/usb/devices vendor ids (a passive listing: no hardware server, no JTAG access, nothing opened)", devices=found)

    # -- repository state -----------------------------------------------------------------------------------------------------------
    def repo(self) -> list[dict[str, Any]]:
        out = []
        g = "Repository"
        from agent import access
        ents = access.load_entries()
        out.append(chk("access", g, "Access gate", "ok" if ents is not None else "warn",
                       (f"armed: {sum(1 for e in ents if e.get('enabled', True))} enabled entr{'y' if sum(1 for e in ents if e.get('enabled', True)) == 1 else 'ies'}; this session was admitted" if access.CURRENT
                        else f"armed: {len(ents)} entries; this session was admitted") if ents is not None else "NOT armed: agent/access/keys.json is absent, so the agent runs without a key",
                       "agent/access/keys.json present (names, salts and hashes are not shown)"))
        # knowledge bank pin: PACKS.md against the local private checkout
        pin = None
        try:
            m = re.search(r"Private repo commit:\s*`([0-9a-f]{7,40})`", (self.root / "knowledge/PACKS.md").read_text())
            pin = m.group(1) if m else None
        except OSError:
            pass
        kb = self._kb_dir()
        head = None
        if kb:
            rc, o, _ = self.runner.run(["git", "-C", str(kb), "rev-parse", "HEAD"], timeout=10)
            head = o.strip() if rc == 0 else None
        if pin and head:
            same = head.startswith(pin)
            out.append(chk("kb_pin", g, "Knowledge-bank pin", "ok" if same else "warn",
                           f"pinned {pin[:8]}; local checkout at {head[:8]}" + ("" if same else " (differs: the checkout has moved on, or is on another branch)"),
                           "knowledge/PACKS.md against `git rev-parse HEAD` of the local private checkout (hashes only)"))
        else:
            out.append(chk("kb_pin", g, "Knowledge-bank pin", "unknown", f"pinned {pin[:8] if pin else 'not found'}; the local private checkout was not found, so it cannot be compared",
                           "knowledge/PACKS.md; the checkout is $FDA_KB or a sibling directory FPGA_Design_Agent_Knowledge"))
        try:
            from agent.core import prompts as P
            prov = P.provenance()
            pinned, now_ = prov.get("pinned_manifest_sha256"), prov.get("manifest_sha256")
            same = bool(pinned) and pinned == now_
            how = "agent/core/prompts_pin.json against the private prompts manifest (hashes only; no prompt text is read)"
            if not pinned:
                out.append(chk("prompts_pin", g, "Prompts pin", "unknown", "nothing is pinned yet", how))
            elif not now_:
                out.append(chk("prompts_pin", g, "Prompts pin", "unknown", f"pinned manifest {str(pinned)[:12]}; the private prompts directory was not found here, so it cannot be compared", how))
            else:
                out.append(chk("prompts_pin", g, "Prompts pin", "ok" if same else "warn",
                               f"pinned manifest {str(pinned)[:12]}, on disk {str(now_)[:12]}, enforced: {prov.get('enforced')}", how))
        except Exception as e:                                   # a missing private checkout is a state, not a crash
            out.append(chk("prompts_pin", g, "Prompts pin", "unknown", f"cannot compare with the private prompts: {str(e)[:140]}", "agent.core.prompts.provenance()"))
        out.append(chk("ci_main", g, "CI status of main", "not-run", "not checked: click to ask GitHub (one API call)", "an action: gh run list on main, run only when you click", action="ci_main"))
        return out

    def _kb_dir(self) -> Path | None:
        for c in (os.environ.get("FDA_KB"), str(self.root.parent / "FPGA_Design_Agent_Knowledge"), str(self.root.parent.parent / "FPGA_Design_Agent_Knowledge")):
            if c and (Path(c) / ".git").exists():
                return Path(c)
        return None

    # -- the panel ------------------------------------------------------------------------------------------------------------------
    def all(self) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        for key, fn in (("llm", lambda: self.claude_cli() + self.models()), ("usage", lambda: [self.usage()]), ("tools", self.tools),
                        ("locks", self.locks), ("mem", self.memory_load_disk), ("boards", self.boards), ("repo", self.repo)):
            checks += self._cached(key, fn) if key not in ("usage", "locks", "boards") else fn()
        checks.append(chk("llm_probe", "LLM availability", "Probe every endpoint in use", "not-run",
                          "not checked: click to send one minimal call to each endpoint in use (this spends a few tokens)",
                          "an action: python -m agent models check --probe, run only when you click", action="llm_probe"))
        for c in checks:
            a = self.actions_run.get(c["id"]) or (self.actions_run.get(c.get("action")) if c.get("action") else None)
            if a:
                c.update(status=a["status"], detail=a["detail"], checked_at=a["checked_at"], how=a["how"], output=a.get("output"))
        order = {"fail": 0, "warn": 1, "unknown": 2, "not-run": 3, "ok": 4}
        counts: dict[str, int] = {}
        for c in checks:
            counts[c["status"]] = counts.get(c["status"], 0) + 1
        return {"checked_at": now(), "counts": counts, "checks": checks, "groups": list(dict.fromkeys(c["group"] for c in checks)), "order": order,
                "note": "free checks refresh when this page is opened (cached for a minute); an action runs only when you click it"}

    # -- actions (a click) ----------------------------------------------------------------------------------------------------------
    ACTIONS = ("usage_live", "llm_probe", "ci_main")

    def run_action(self, name: str) -> dict[str, Any]:
        if name not in self.ACTIONS:
            raise KeyError(name)
        fn = getattr(self, "_act_" + name)
        if not self._locks[name].acquire(blocking=False):             # a second click or request while one is running starts nothing
            return {"id": name, "status": "warn", "detail": "already running: wait for it to finish", "checked_at": now(), "how": "one run of each action at a time", "output": None}
        try:
            res = fn()
        finally:
            self._locks[name].release()
        self.actions_run[name] = res
        if name == "usage_live":
            self._cache.pop("usage", None)
        return {**res, "id": name}

    def _act_usage_live(self) -> dict[str, Any]:
        rc, out, err = self.runner.run(["bash", str(self.handoff / "usage_check.sh")], timeout=90)
        u = self.usage()
        u.update(how="_handoff/usage_check.sh (headless /usage, 0 tokens), run on your click")
        if rc != 0:
            u.update(status="unknown", detail=f"usage_check.sh failed (exit {rc}): {redact.brief(err or out)}")
        return {"status": u["status"], "detail": u["detail"], "checked_at": now(), "how": u["how"], "output": None}

    def _act_llm_probe(self) -> dict[str, Any]:
        rc, out, err = self.runner.run([self.python, "-m", "agent", "models", "check", "--probe"], timeout=300, cwd=self.root)
        rows = [ln for ln in out.splitlines() if re.match(r"(ok  |FAIL) ", ln)]
        status = "ok" if rc == 0 and rows else "fail" if rows else "unknown"
        return {"status": status, "detail": f"{sum(r.startswith('ok') for r in rows)} of {len(rows)} endpoints answered" if rows else f"no probe result (exit {rc}): {redact.brief(err or out)}",
                "checked_at": now(), "how": "python -m agent models check --probe: one minimal call per endpoint in use (spends tokens), run on your click",
                "output": [redact.text(r)[:200] for r in rows]}

    def _act_ci_main(self) -> dict[str, Any]:
        how = "gh run list --branch main --limit 1 (one GitHub API call), run on your click"
        rc, out, err = self.runner.run(["gh", "run", "list", "--branch", "main", "--limit", "1", "--json", "status,conclusion,headSha,createdAt,workflowName"], timeout=30, cwd=self.root)
        try:
            r = json.loads(out)[0]
        except (ValueError, IndexError):
            return {"status": "unknown", "detail": f"no answer from GitHub (exit {rc}): {redact.brief(err or out)}", "checked_at": now(), "how": how, "output": None}
        ok = r.get("conclusion") == "success"
        return {"status": "ok" if ok else "fail" if r.get("conclusion") else "warn",
                "detail": f"{r.get('workflowName')} on {str(r.get('headSha'))[:8]}: {r.get('conclusion') or r.get('status')} ({str(r.get('createdAt'))[:16]})", "checked_at": now(), "how": how, "output": None}
