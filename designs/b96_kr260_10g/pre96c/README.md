# pre96c: the design's RTL as it was before brief 96C (main 6909e43f)

A frozen copy of `rtl/` from before the elastic buffer (`rate_match.sv`) went in. The latency variants `lat_agent_cdc`, `lat_hand_ref` and `lat_agent_both`
(brief 97) were built on that RTL and are left unchanged by 96C; their `build.yaml` now reads their unchanged files from here, so they still build exactly
what brief 97 measured. `lat_all3` was rebuilt on the new base (see `docs/design.md`, section 9). Not edited, not part of the current design.
