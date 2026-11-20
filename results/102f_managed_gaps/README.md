# Brief 102F: managed-project gaps (records)

Closes the gaps left after stages 1-3 of the managed-project work: waiver files owner-only, writes to frozen files prevented while a tool runs design
code, the scope in the run record and re-checked on resume, an evidence-signing proposal, and the check of the `run4_c14` fixture failures. Rules and
the full table of write paths are in [docs/managed_projects.md](../../docs/managed_projects.md) ("Waiver files are the owner's", "Writes prevented, not
only detected", "The scope in the run record", "Evidence signing (proposed, not built)").

## Records

| File | Made by | Shows |
|---|---|---|
| `demo_session.json` | `FDA_102F_DEMO_OUT=results/102f_managed_gaps/demo_session.json python3 -m pytest -q -s agent/tests/test_102f_demo.py` (script: `designs/b102_managed_ext/scripts/demo_gaps_session.py`) | on a scratch copy of `b102_managed_ext`: four writes to waiver files or in-source waivers refused; a tool that runs design code fails to write the frozen `lfsr.v` and a waiver file (PermissionError), the files unchanged and the modes restored; the same attempts inside the sandbox container, where write, chmod-then-write and rename-over all fail; the scope record; five resume re-checks |
| `run4_c14_fixture.md` | the 6-minute local run of `agent/tests/fixtures/run4_c14` before and after the fix | the cause of the three failures and the two-line fix |

## Reproduce

Python with PyYAML, jsonschema and pytest; the container step needs Docker and the `fda-sim:2` image and is skipped with a note otherwise. No Vivado is
needed: the demonstration is on the sources and the tool layer. Tests: `python3 -m pytest -q agent/tests/test_102f_gaps.py agent/tests/test_102f_demo.py`.
The session runs under pytest because outside it the agent's access gate needs the access key.

## Known gaps and limits

- The lock prevents plain writes by design code on the host; code that chmod-s a file back, or replaces a protected file inside a directory that also holds
  owned files, is still only detected (the integrity re-hash). Inside the container runner the files are mounted read-only and those routes fail too.
  The container runner is used for `simulate` (and the kinds the run enables); builds, lint and the other tools run on the host.
- Reads of excluded files by design code are neither detected nor prevented.
- The waiver rule covers the files the flow reads today (`lint/**`, `waivers.yaml`, `verif/justifications.yaml`, the three keyed lists, in-source
  comments). A new waiver mechanism added to the flow later needs a line in `managed.WAIVER_PATHS` or `WAIVER_KEYS`.
- Evidence signing is a proposal; the trust labels are still computed from unsigned evidence.
- No model-driven run: the sessions are scripts that call the real tool dispatch.
