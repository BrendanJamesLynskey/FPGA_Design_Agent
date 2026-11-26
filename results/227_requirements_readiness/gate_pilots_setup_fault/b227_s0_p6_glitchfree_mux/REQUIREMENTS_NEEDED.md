# Requirements needed before this design can proceed

Requirements readiness stopped: the round limit (4) was reached with questions still open. Nothing was built.

Answer each question in `requirements_answers.yaml` (`Q1: <your answer>`, or `Q1: {answer: ..., who: ...}`), then run again; or answer through the interview.

| Id | Topic | Question | Where it came from |
|---|---|---|---|
| Q18 | requirement | Which value does MUX_COUNT hold? (Scenario: A SNAPSHOT write occurs in the same clk_c3 cycle that the muxed counter increments from 0x0000_00FF to 0x0000_0100.) The requirements do not say; what should happen? | readers (RDY-READ-02) |
