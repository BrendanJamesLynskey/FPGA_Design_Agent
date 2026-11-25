# Navigator screenshots for brief 194

Screenshots of the Start and Live pages with the verification profile picker, the switch drawer and the profile line, taken 2026-11-23. They show what the page looks like; they are not a measurement.

## Records

| file | what |
|---|---|
| `start_picker_wide.png`, `start_picker_phone.png` | Start page with the profile picker at 1280 and 390 px |
| `start_profile_drawer_wide.png`, `start_profile_drawer_phone.png` | the profile `high_dependability` selected and the switch drawer open |
| `start_started_wide.png` | after Start, with the fake spawner |
| `live_wide.png`, `live_phone.png` | the Live page |
| `report.json` | the script's own checks: page errors, blocked requests, overflow at 390 px (all empty) |

## Reproduce

Start the demo fixture with `python3 -m navigator.tests.demo_stage2 --port 8794 --workdir <scratch dir>`, then run `NODE_PATH=<repo>/node_modules node navigator/shoot_194.js <address with token> <output dir>`. The fixture uses a fake spawner and fake board transport, so no agent, Vivado or board is started.

## Known gaps and limits

- The Live page screenshots show a synthetic demo run that has no policy file, so the profile line reads "not recorded"; a real run's profile line was checked only by the unit test in `navigator/tests/test_194_navigator.py`.
- Only a dark theme at two widths was shot; no light theme.
- The settings questions are asked on the Live page through the existing question flow; no screenshot of them was taken.
