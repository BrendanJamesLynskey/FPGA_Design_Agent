# Requirements needed before this design can proceed

Requirements readiness stopped: the round limit (4) was reached with questions still open. Nothing was built.

Answer each question in `requirements_answers.yaml` (`Q1: <your answer>`, or `Q1: {answer: ..., who: ...}`), then run again; or answer through the interview.

| Id | Topic | Question | Where it came from |
|---|---|---|---|
| Q8 | requirement | Does h_rdata show 0x11 (new value) rather than 0x22 within 2 clk after h_re? (Scenario: h_we is pulsed at cycle T writing 0x11 to SCRATCH, and h_re for SCRATCH is pulsed in the same cycle T (SCRATCH previously 0x22).) Two careful readers of the requirements disagree about this; what is the intended behaviour? | readers (RDY-READ-01) |
