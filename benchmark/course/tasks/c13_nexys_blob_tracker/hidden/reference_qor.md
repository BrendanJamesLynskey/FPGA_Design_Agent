# Reference QoR: P13-2

The course's single-pass labeller (`solutions/p13l08_ccl/ccl.sv`) is a behavioural reference (integer arrays, a one-clock root resolve loop); it is **not synthesisable as written to
meet a pixel clock**, so no QoR was measured. A pipelined resolve is the agent's design task (lesson 8). Full-flow and OOC QoR: **not run**. The re-scoped reference (v1.1) adds a small
selection and centroid block (`blob_report.sv`, a divider on 20-bit sums) around it; simulated only.
