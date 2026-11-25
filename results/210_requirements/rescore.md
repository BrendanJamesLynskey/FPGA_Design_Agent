# Re-scoring recorded runs with the brief 210 risk classes

Each recorded question is classed now by `agent.graph.requirements.classify` (none had a class when it ran). A failure is a run that did not stop cleanly; a rework is a run that re-entered a stage after a failed gate. They are coincidences by run, not causes.

| Group | Runs | Questions asked | Defaulted | Defaulted: high / medium / low | Runs with a high default | Failure (with / without) | Rework (with / without) |
|---|---|---|---|---|---|---|---|
| all | 40 | 347 | 276 | 200 / 73 / 3 | 39 of 40 | 28 of 39 / 1 of 1 | 37 of 39 / 1 of 1 |
| main records (benchmark and development runs) | 30 | 272 | 201 | 157 / 41 / 3 | 29 of 30 | 25 of 29 / 1 of 1 | 27 of 29 / 1 of 1 |
| 209 pilot (--interview off) | 10 | 75 | 75 | 43 / 32 / 0 | 10 of 10 | 3 of 10 / 0 of 0 | 10 of 10 / 0 of 0 |
| oracle-answered main runs | 15 | 125 | 54 | 47 / 6 / 1 | 14 of 15 | 12 of 14 / 1 of 1 | 12 of 14 / 1 of 1 |
| main runs with no interview (off) | 15 | 147 | 147 | 110 / 35 / 2 | 15 of 15 | 13 of 15 / 0 of 0 | 15 of 15 / 0 of 0 |

High-risk defaults by rule: interface 46, behaviour 41, register-map 30, reset 29, clock 22, rate-and-latency 17, external-device 8, number-format 6, pins-and-io 1


Pilot records: `origin/b209-kr260-pilot` at `451e5777e0cc`; runs included: p1_clkmeter/run1, p1_clkmeter/run2, p1_clkmeter/run3, p2_bram_rom/run1, p2_bram_rom/run2, p2_bram_rom/run3, p3_crc_engine/run1, p3_crc_engine/run2, p3_crc_engine/run3, p4_fir_dsp/run1.
