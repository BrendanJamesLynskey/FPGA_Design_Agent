# Telemetry pacer (v2_e_tlm_pacer)

Domain E (networking), tier T2 (L1 probe of the endpoint ladder), Nexys A7-100T. Part of the UDP command and telemetry endpoint ladder project (brief 82). Draft for the problem catalogue; the task files are in
`benchmark/v2/tasks/v2_e_tlm_pacer/`.

## The problem, and where it is used

The timing block of a status-report stream: a frame falls due every N ticks, at most one waits, extra frames are dropped and counted, never queued.

Any stream that must not exceed a rate (heartbeats, telemetry, log shipping) needs the same rule: a fixed spacing, a single slot and an honest count of what was dropped, so a slow consumer cannot cause a burst afterwards.

## Hero diagram

A tick counter climbs to the period, a frame appears in a single slot and the counter restarts. If the slot is still full at the next due time, a drop counter ticks instead. A request to change the period waits for the next count to start.

## Animation plan (driven by `hidden/model.py`)

Use Model.tick() from hidden/model.py to step one tick at a time: show the counter, the period in force against the period asked for, the slot and the two totals, with a slow-consumer slider.

## Interface

Shell registers: CTRL (enable), REQ and EFF (period asked and in force), TICK (n ticks), TAKE, STAT, FRAMES, OVERRUNS, CNT. LED[15:0] shows the frame total. Parameter PERIOD_MIN (default 4).

## Acceptance criteria in plain words

A frame falls due on every period-th tick from the switch-on; one frame waits at most and a dropped one is counted; a request below PERIOD_MIN is raised, and a new request waits for the next count; switching off clears the count and the waiting frame and keeps the totals. Checked with two values of PERIOD_MIN.
