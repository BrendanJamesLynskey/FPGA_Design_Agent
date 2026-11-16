# Ambiguities in v2_e_cmd_exec

Items the interview must pin down, with the oracle's source being `spec.yaml`:

- Whether a refused command still leaves the previous read value: no, it is cleared by every GO.
- Counters are 32-bit.
- Register numbers 8 and above are refused, including 256 (not a wrap).
- STATUS does nothing else but counts as a success; telemetry stop ignores its parameters.
- Refusals do not change anything but ERRS and the code; an unknown type is checked after the register number only for types 1 and 2 (an unknown type has no register).
- Parameter and register widths; the view at 0x10.
