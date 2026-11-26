# Requirements needed before this design can proceed

Requirements level: **standard** (from command line). The run stopped at the clarify stage; nothing was built.

3 question(s) need an answer or an explicit waiver. For each, either put the answer in the request (spec.md) and run again, answer it with `--interview on`, or record a waiver in `requirements_waivers.yaml` (question or id, value, who, when, why).

| Id | Risk | Question | The agent would have used | Why it matters |
|---|---|---|---|---|
| q4 | high | What is the host register map (offset, width, reset value and access of every register)? | One register STATUS at 0x00, 32 bits, reset 0, read-only, bit0 = LED lit | the register map is what host software and the test shell are written against |
| q5 | high | Should the host be able to read other things, for example a press counter or a sticky 'pressed' flag? | No, only the LED lit bit | it settles what the design does in a case the request left open |
| q6 | high | Should the reset button clear the stretch? | Yes, reset clears the counter and led0 | a reset's polarity, style or value decides the start-up state and the interface |

Example waiver (`requirements_waivers.yaml`):

```yaml
waivers:
  - match: <question id or words of the question>
    value: agent's default accepted
    who: <your name>
    when: <YYYY-MM-DD>
    why: <the reason, at least a sentence>
```
