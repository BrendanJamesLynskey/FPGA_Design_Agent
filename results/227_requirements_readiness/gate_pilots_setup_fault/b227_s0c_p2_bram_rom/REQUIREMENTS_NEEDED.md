# Requirements needed before this design can proceed

Requirements readiness stopped: no answer was available for the open questions. Nothing was built.

Answer each question in `requirements_answers.yaml` (`Q1: <your answer>`, or `Q1: {answer: ..., who: ...}`), then run again; or answer through the interview.

| Id | Topic | Question | Where it came from |
|---|---|---|---|
| Q1 | requirement | Does MEM_ADDR advance on that BUSY RAM_DATA read (i.e. MEM_ADDR after read equals 101)? (Scenario: While BUSY, RAM_DATA is written 0xAAAA5555 at MEM_ADDR 3 and MEM_ADDR is written 100; a RAM_DATA read follows. AUTOINC is set.) The requirements do not say; what should happen? | readers (RDY-READ-02) |
| Q2 | requirement | Is DONE set and completed pass count equal to 5 in the same sample where BUSY is 0? (Scenario: The last pass of a 5-pass march ends. In the clock in which BUSY falls, MARCH_STATUS is sampled.) The requirements do not say; what should happen? | readers (RDY-READ-02) |
