# v2_e_udp_endpoint oracle notes

Deliberate gaps in the request; `spec.yaml` holds the answers.

- Order of checks and which refusals reply (the first three are silent).
- Counters are read before the command is counted; the refused-packets register counts every refusal class.
- The sequence number of an accepted command is consumed even when the register number fails.
- Telemetry snapshots the counts when the frame falls due; frames have their own sequence from 0; STOP forgets a held frame; START restarts the count.
- Tick register semantics and the window offsets; the ID word and the reply layouts.
