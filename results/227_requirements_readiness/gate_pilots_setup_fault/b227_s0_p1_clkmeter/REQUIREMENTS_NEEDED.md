# Requirements needed before this design can proceed

Requirements readiness stopped: no answer was available for the open questions. Nothing was built.

Answer each question in `requirements_answers.yaml` (`Q1: <your answer>`, or `Q1: {answer: ..., who: ...}`), then run again; or answer through the interview.

| Id | Topic | Question | Where it came from |
|---|---|---|---|
| Q11 | Names, files and the build target | What are the exact port names of p1_clkmeter_core, beyond the h_* register port? In particular: where does the BUILD word come from (an input of the core, or is USR_ACCESSE2 inside the core), and are the LED and SFP outputs and the reset and clock inputs ports of the core, or produced only in the top? | reviewer (RDY-REV-01) |
| Q12 | requirement | What value does h_rdata show? (Scenario: At the same clock edge h_we writes SCRATCH=0x55 and h_re reads SCRATCH, whose previous value was 0x11.) Two careful readers of the requirements disagree about this; what is the intended behaviour? | readers (RDY-READ-01) |
