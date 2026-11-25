# Re-scoring recorded runs with the brief 210 risk classes

Each recorded question is classed now by `agent.graph.requirements.classify` (none had a class when it ran). A failure is a run that did not stop cleanly; a rework is a run that re-entered a stage after a failed gate. They are coincidences by run, not causes.

| Group | Runs | Questions asked | Defaulted | Defaulted: high / medium / low | Runs with a high default | Failure (with / without) | Rework (with / without) |
|---|---|---|---|---|---|---|---|
| all | 39 | 338 | 267 | 195 / 69 / 3 | 38 of 39 | 27 of 38 / 1 of 1 | 36 of 38 / 1 of 1 |
| main records (benchmark and development runs) | 30 | 272 | 201 | 157 / 41 / 3 | 29 of 30 | 25 of 29 / 1 of 1 | 27 of 29 / 1 of 1 |
| 209 pilot (--interview off) | 9 | 66 | 66 | 38 / 28 / 0 | 9 of 9 | 2 of 9 / 0 of 0 | 9 of 9 / 0 of 0 |
| oracle-answered main runs | 15 | 125 | 54 | 47 / 6 / 1 | 14 of 15 | 12 of 14 / 1 of 1 | 12 of 14 / 1 of 1 |
| main runs with no interview (off) | 15 | 147 | 147 | 110 / 35 / 2 | 15 of 15 | 13 of 15 / 0 of 0 | 15 of 15 / 0 of 0 |

High-risk defaults by rule: reset 52, interface 51, behaviour 39, clock 22, rate-and-latency 17, external-device 8, number-format 5, pins-and-io 1


Pilot records: `origin/b209-kr260-pilot` at `917ddf5a1b1c`; runs included: p1_clkmeter/run1, p1_clkmeter/run2, p1_clkmeter/run3, p2_bram_rom/run1, p2_bram_rom/run2, p2_bram_rom/run3, p3_crc_engine/run1, p3_crc_engine/run2, p3_crc_engine/run3.
