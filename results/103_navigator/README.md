# Brief 103: the navigator, stage 1 (records)

The service and its pages are described in [navigator/README.md](../../navigator/README.md). This folder holds the headless screenshots and their check.

## Records

| File | Made by | Shows |
|---|---|---|
| `screenshots/<view>_wide.png`, `<view>_phone.png` | `NODE_PATH=<node_modules> node navigator/shoot.js <url with token> results/103_navigator/screenshots` | each page and drawer at 1280 px and 390 px: project (with a component drawer and a scope picked), timing (with a stage drawer), runs (with a run drawer), measurements (eye, 3-D bathtub with slices, compare with the difference map, board sessions, frequency offset, buffer latency, conditions), health, models |
| `screenshots/check.json` | the same script | 32 screenshots, 0 page errors (console errors count), 0 requests outside the service, 0 pages wider than 390 px at 390 px |

The service ran against this repository's records and the owner's 24 local run records (`--runs`, which are not in the repository). The eye captures are the **synthetic** examples of brief 96D (`results/b96d/offline`): the watermark in the eye views is theirs.

## Tests

`python -m pytest navigator/tests` (28 tests): loopback-only binding (a non-loopback host is refused), token and Host-header rules, the access gate called on every request, POST rules, the endpoints on the real records, the scope picker (frozen and excluded parts cannot be scoped), the eye page and record viewer serving only listed files (traversal attempts get 404), a planted key, prompt text and account email never appearing in any response or action result, free health checks starting no costly or hardware command (the runner is a fake that records them), actions running only their fixed commands, the JTAG listing refused while the board lock is held, usage levels against the 88% line, and stale-lock detection.

## Known gaps and limits

- **Stage 1 only.** No run is started from the page; the scope picker builds a command to paste. Live progress, starting and refining runs, and hosting for named people are stage 2.
- **The token is printed on the terminal** and moves into a cookie. Another process of the same user can read the cookie jar or the terminal; the service is not a defence against that, nor against anyone who can edit the code.
- **The JTAG listing starts hw_server and Vivado batch** (`flow/hw_list.tcl`) when clicked. It refuses while `board.lock` is held but does not take the lock itself, and does not take a heavy slot. It was exercised only with a fake runner here; it has not been clicked on the real board.
- **No board eye data exists yet**, so the eye views have only been drawn from synthetic captures. The difference map and the slice sliders are checked by screenshot, not against a measured pair.
- The synthetic captures in `results/b96d/offline` carry no `settings.expected_points`, so the navigator says "grid size not recorded" for their completeness (96D's `margin` tool would call them incomplete). Worth fixing in 96D's fake.
- The latency page shows `designs/b96_kr260_10g/latency_stages.yaml`, which describes the `RATE_MATCH = 1` chain (13 clocks simulated); the default build is `RATE_MATCH = 0` (11 clocks), and its stage file is the git history of this one. The stage file's post-route slack file is not recorded, so stages show "not recorded". Board E and L are shown under Measurements (restart statistics), not added into the chain.
- Supply and temperature are only the start and end samples each record holds; no timeline exists to draw.
- Only managed projects (`designs/*/project.yaml`) are shown as trees; the project layer of brief 27 (`project/examples`) is not.
- The CI-status and usage actions were exercised with fakes; the usage button runs `usage_check.sh`, which starts a headless Claude Code process.
- The KB-pin check compares `knowledge/PACKS.md` with the local private checkout's HEAD; today they differ (the checkout has moved on), so it shows a warning that is a fact, not a fault.
- Prompt names and hashes are read from `claude_code/*.prompt.json`; runs of the Deep Agents harness record no such file, so their drawer says so.
