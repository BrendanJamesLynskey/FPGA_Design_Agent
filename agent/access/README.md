# Access gate

While the agent is developed it refuses to start without an access key. This page says what that does, what it does
not do, and how to set it up. Licence: [LICENSE](../../LICENSE).

## What it protects against, and what it does not

- It stops **casual use of a checkout**: someone who clones the repository and runs `python -m agent` gets a one-line
  refusal.
- It does **not** stop anyone who edits the code: the check is a few lines and can be deleted. The licence is what
  forbids using the agent without permission. The committed file holds salted hashes, so the key cannot be read back
  from the repository, but that is all it guarantees.
- The key is never printed, logged, committed or put in a run record: it is on the redaction list
  (`agent/core/security.py`), the audit log records only the entry's **name**, and the Claude Code arm's MCP
  configuration holds `${FDA_ACCESS_KEY}` as a reference, not the value.

## How it works

- `agent/access/keys.json` is a list of named entries: `name`, a per-entry `salt`, `sha256` (of the salt followed by
  the key), an optional `expires` date (the last day the key works) and `enabled`. The owner is entry `owner`.
- The gate accepts a key that matches **any enabled, unexpired entry** and records the entry's name for the run (an
  `access` record in `build/audit.jsonl`), so each run can be attributed to a person.
- **If `keys.json` does not exist the gate is not armed**: everything runs, and each process says so once on stderr.
  Once it exists, an entry point without a valid key exits with status 2 and one line naming `FDA_ACCESS_KEY` and
  `.env.example`.
- The key comes from `FDA_ACCESS_KEY` in the environment, else from a git-ignored `.env` at the repo root.
- Gated: `python -m agent` (run, resume, document), run creation (`new_runtime`), the Claude Code arm and its MCP
  server, the plan and closure arms, the skill service and index tools, the smoke run and the demo scripts.
  `python -m agent project spec` is gated (it drafts with a model); the other `project` subcommands, the models, flows, RTL tests and site builds do not need the key.
  A test (`agent/tests/test_94_access.py`) fails if a new script that imports the agent has no gate call.

## Owner: arming

1. In your `FPGA_Design_Agent` checkout: `python3 -c "import secrets; print('FDA_ACCESS_KEY=' + secrets.token_urlsafe(32))" >> .env`
2. `python3 tools/access/set_key_hash.py` (adds entry `owner`; prints no key), then commit `agent/access/keys.json`.
3. `gh secret set FDA_ACCESS_KEY` and paste the value when asked (or Settings, Secrets and variables, Actions).
   Do not paste the key into a chat, issue or log. Other worktrees and machines need the same `.env` or the variable.

## Owner: letting someone try it

Make them a key the same way, in a separate file, and add an entry with an expiry:

    python3 tools/access/set_key_hash.py --name alice --env-file /path/to/alice.env --expires 2027-03-31

Give them the key (not the file in the repository), commit `keys.json`. To end access: `--revoke alice` and commit.
Re-running with the same `--name` replaces the entry (new salt). Revoked entries stay in the file, disabled.

## Using it

Copy `.env.example` to `.env` and put the key you were given after `FDA_ACCESS_KEY=`. `.env` is git-ignored.

## CI

No CI job calls a live agent: the Python job runs the test suite with the gate bypassed for in-process tests (a
`conftest.py` fixture), and the gate has its own tests with the bypass off. The Python job reads the secret as
`FDA_ACCESS_KEY` so one test (`test_the_ci_secret_matches_the_committed_hash`) can confirm that the secret matches the
committed entries once armed; without the secret (fork pull requests) it **skips with a notice** and nothing fails.
