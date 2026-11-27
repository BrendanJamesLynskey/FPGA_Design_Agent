# Requirements needed before this design can proceed

Requirements readiness stopped: no answer was available for the open questions. Nothing was built.

Answer each question in `requirements_answers.yaml` (`Q1: <your answer>`, or `Q1: {answer: ..., who: ...}`), then run again; or answer through the interview.

| Id | Topic | Question | Where it came from |
|---|---|---|---|
| Q1 | requirement | Please restate REQ-17 so that one statement can be checked: split it into one requirement per checkable statement, each with its own id and proof method | code (RDY-CLEAR-01) |
| Q2 | requirement | Please restate REQ-27 so that one statement can be checked: split it into one requirement per checkable statement, each with its own id and proof method | code (RDY-CLEAR-01) |
| Q3 | requirement | Please restate REQ-29 so that one statement can be checked: split it into one requirement per checkable statement, each with its own id and proof method | code (RDY-CLEAR-01) |
| Q4 | requirement | In which clock offset after T (0, 1, or 2) is h_rdata first guaranteed to show the value, and is the exact latency fixed? Give the number of clocks of the earliest latency allowed. (Scenario: h_re is asserted for one clock at address 0x008 at clock T.) Two careful readers of the requirements disagree about this; what is the intended behaviour? | readers (RDY-READ-01) |
| Q5 | requirement | What does CRC read after reset? (Scenario: Five consecutive-clock PUSH4 writes are in progress; rst is asserted during the third push's clock. After rst release, CRC is read without INIT.) The requirements do not say; what should happen? | readers (RDY-READ-02) |
