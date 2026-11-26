# Requirements needed before this design can proceed

Requirements level: **strict** (from command line). The run stopped at the clarify stage; nothing was built.

3 question(s) need an answer or an explicit waiver. For each, either put the answer in the request (spec.md) and run again, answer it with `--interview on`, or record a waiver in `requirements_waivers.yaml` (question or id, value, who, when, why).

| Id | Risk | Question | The agent would have used | Why it matters |
|---|---|---|---|---|
| q1 | high | What is the register map for host readback (offset, width, reset value, access of every register)? | One 32-bit RO register STATUS at offset 0x00, bit0 = LED lit, reset 0. | the register map is what host software and the test shell are written against |
| q3 | high | How exact is "about half a second" and what debounce time is wanted? | 50,000,000 clocks (0.5 s) and 2,000,000 clocks (20 ms) debounce. | a rate, delay or latency target is a requirement the tests check |
| q4 | high | Does the press act on the press edge or the release edge? | Press (debounced rising) edge. | it settles what the design does in a case the request left open |

Example waiver (`requirements_waivers.yaml`):

```yaml
waivers:
  - match: <question id or words of the question>
    value: agent's default accepted
    who: <your name>
    when: <YYYY-MM-DD>
    why: <the reason, at least a sentence>
```
