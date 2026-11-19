# Brief 103: the navigator, stage 1 (records)

The service and its pages are described in [navigator/README.md](../../navigator/README.md). This folder holds the headless screenshots and their check.

## Records

| File | Made by | Shows |
|---|---|---|
| `screenshots/<view>_wide.png`, `<view>_phone.png` | `NODE_PATH=<node_modules> node navigator/shoot.js <url with token> results/103_navigator/screenshots` | each page and drawer at 1280 px and 390 px: project (with a component drawer and a scope picked), timing (with a stage drawer), runs (with a run drawer), measurements (eye, 3-D bathtub with slices, compare with the difference map, board sessions, frequency offset, buffer latency, conditions), health, models |
| `screenshots/check.json` | the same script | 32 screenshots, 0 page errors (console errors count), 0 requests outside the service, 0 pages wider than 390 px at 390 px |

The service ran against this repository's records and the owner's 24 local run records (`--runs`, which are not in the repository). The eye captures are the **synthetic** examples of brief 96D (`results/b96d/offline`): the watermark in the eye views is theirs.

## Tests

`python -m pytest navigator/tests` (18 tests): loopback-only binding (a non-loopback host is refused), token and Host-header rules, the access gate called on every request, POST rules, the endpoints on the real records, the scope picker (frozen and excluded parts cannot be scoped), the eye page and record viewer serving only listed files (traversal attempts get 404), a planted key, prompt text and account email never appearing in any response or action result, free health checks starting no costly or hardware command (the runner is a fake that records them), actions running only their fixed commands, no JTAG or Vivado code path, usage levels against the 88% line, and stale-lock detection.

## Review

One Sonnet review (security and correctness; the three questions of the brief) and one fix round. Findings fixed: the eye page built HTML from capture text (an XSS that, same-origin, could reach the actions): it now escapes every interpolated value and is served and embedded sandboxed (opaque origin, height by `postMessage`); the record viewer could follow a committed symlink and showed JSON as raw text: it refuses symlinks and key, prompt, secret and token file names, and parses and scrubs JSON; the scrubber now matches normalised key names by substring and knows JWT, Google and Basic-auth patterns; run-record fields are scalar-only and capped; tool errors show one capped line; a negative Content-Length is clamped; each action runs one at a time; an action needs the token in a header (the cookie alone is refused). **The fixes were not re-reviewed** (check once). No finding on reachability from another machine or origin, nor on a free check starting a costly or hardware command.

## Known gaps and limits

- **Stage 1 only.** No run is started from the page; the scope picker builds a command to paste. Live progress, starting and refining runs, and hosting for named people are stage 2.
- **The cookie is not scoped by port**, so another localhost service the browser visits receives it; an action needs the header token as well (fetched from `/api/session`), which that service cannot read.
- **The token is printed on the terminal** and moves into a cookie. Another process of the same user can read the cookie jar or the terminal; the service is not a defence against that, nor against anyone who can edit the code.
- **No JTAG or hardware-server step in stage 1** (planner decision after review): the listing needs `board.lock` and a heavy slot, so Health shows it as disabled; a test asserts no navigator code can start the hardware server or Vivado. Stage 2 item.
- **No board eye data exists yet**, so the eye views have only been drawn from synthetic captures. The difference map and the slice sliders are checked by screenshot, not against a measured pair.
- (The two synthetic captures now carry `settings.expected_points`, added by this PR.)
- The latency page shows `designs/b96_kr260_10g/latency_stages.yaml`, which describes the `RATE_MATCH = 1` chain (13 clocks simulated); the default build is `RATE_MATCH = 0` (11 clocks), and its stage file is the git history of this one. The stage file's post-route slack file is not recorded, so stages show "not recorded". Board E and L are shown under Measurements (restart statistics), not added into the chain.
- Supply and temperature are only the start and end samples each record holds; no timeline exists to draw.
- Only managed projects (`designs/*/project.yaml`) are shown as trees; the project layer of brief 27 (`project/examples`) is not.
- The CI-status and usage actions were exercised with fakes; the usage button runs `usage_check.sh`, which starts a headless Claude Code process.
- The KB-pin check compares `knowledge/PACKS.md` with the local private checkout's HEAD; today they differ (the checkout has moved on), so it shows a warning that is a fact, not a fault.
- Prompt names and hashes are read from `claude_code/*.prompt.json`; runs of the Deep Agents harness record no such file, so their drawer says so.
