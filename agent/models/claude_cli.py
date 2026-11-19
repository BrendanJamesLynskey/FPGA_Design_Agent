"""The one place that builds and runs a headless ``claude -p`` call (brief 108).

Every Claude Code call in the repository (the sub-agent arm, the interview oracle, the spec tests, the DOC step, the
review judge, the RapidWright experiment) takes its argv from :func:`build_argv` and runs it through :func:`run`, so the
isolation flags and the environment are one definition. The gate test ``agent/tests/test_108_model_config.py`` fails when
any other file spells out a ``claude`` argv. The Max-plan token comes from ``agent.claude_code_arm.arm.oauth_token``
(an environment variable or a mode-600 file) and is never written to a record.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

EXE = "claude"


def build_argv(*, system: str, model: str, prompt: str | None = None, output_format: str = "json", verbose: bool = False,
               effort: str | None = None, max_turns: int = 1, mcp_file: Path | str | None = None,
               allowed_tools: Sequence[str] | None = None, strict_mcp: bool = True, exe: str = EXE) -> list[str]:
    """The argv of one isolated headless call: no built-in tools, no settings, no slash commands, nothing saved.

    ``prompt`` None means the prompt goes on standard input (the review judge). ``mcp_file`` adds ``--mcp-config``
    (with ``--strict-mcp-config``) and ``allowed_tools`` the ``--allowedTools`` list (the sub-agent arm)."""
    argv = [exe, "-p", *([prompt] if prompt is not None else []), "--output-format", output_format,
            *(["--verbose"] if verbose else []), "--system-prompt", system, "--tools", ""]
    if mcp_file is not None:
        argv += ["--mcp-config", str(mcp_file)]
    if strict_mcp:
        argv += ["--strict-mcp-config"]
    if allowed_tools is not None:
        argv += ["--allowedTools", *allowed_tools]
    argv += ["--permission-mode", "dontAsk", "--setting-sources", "", "--disable-slash-commands", "--no-session-persistence",
             "--model", model, *(["--effort", effort] if effort else []), "--max-turns", str(max_turns)]
    return argv


def redacted(argv: list[str], user_ref: str, system_ref: str) -> list[str]:
    """The argv as it is recorded: the user message and the system prompt (private) replaced by references to their hashes."""
    shown = list(argv)
    shown[2], shown[argv.index("--system-prompt") + 1] = user_ref, system_ref
    return shown


def available(exe: str = EXE) -> bool:
    return shutil.which(exe) is not None


def version(exe: str = EXE) -> str:
    return subprocess.run([shutil.which(exe) or exe, "--version"], capture_output=True, text=True).stdout.strip()


def run(argv: list[str], *, cwd: Path, env: dict[str, str], timeout: float, input: str | None = None) -> subprocess.CompletedProcess:
    """Run one call in its isolated working directory and environment (``arm.isolated_env``). Raises ``subprocess.TimeoutExpired``."""
    try:
        return subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout,
                              **({"input": input} if input is not None else {"stdin": subprocess.DEVNULL}))
    except subprocess.TimeoutExpired as e:        # its message would carry the whole argv, prompt included
        raise subprocess.TimeoutExpired("claude -p (argv withheld)", e.timeout, output=e.output, stderr=e.stderr) from None


def text_call(system: str, user: str, *, model: str, effort: str | None = None, timeout_s: float = 900,
              prefix: str = "fda_cc_") -> dict[str, Any]:
    """One tool-less single-turn call; returns the parsed ``--output-format json`` result (``{}`` when it was not JSON).
    Raises ``ArmBlocked`` when the CLI or the token is missing."""
    import json
    import tempfile

    from agent.claude_code_arm import arm
    from agent.graph.run import ArmBlocked
    if not available():
        raise ArmBlocked("the claude CLI is not on PATH")
    token = arm.oauth_token()
    if not token:
        raise ArmBlocked("CLAUDE_CODE_OAUTH_TOKEN is not set and the token file is missing")
    work = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        p = run(build_argv(system=system, prompt=user, model=model, effort=effort), cwd=work,
                env=arm.isolated_env(work, token), timeout=timeout_s)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    try:
        return json.loads(p.stdout)
    except ValueError:
        return {}
