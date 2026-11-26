# Requirements needed before this design can proceed

Requirements readiness stopped: no answer was available for the open questions. Nothing was built.

Answer each question in `requirements_answers.yaml` (`Q1: <your answer>`, or `Q1: {answer: ..., who: ...}`), then run again; or answer through the interview.

| Id | Topic | Question | Where it came from |
|---|---|---|---|
| Q1 | requirement | What is the CRC value read (hex, as to whether it is 0x00000000 or the INIT state 0xFFFFFFFF)? (Scenario: After INIT, a PUSH_N is written with TAIL_LEN 0, then CRC, BYTE_COUNT and BUSY_CYCLES are read.) Two careful readers of the requirements disagree about this; what is the intended behaviour? | readers (RDY-READ-01) |
| Q2 | requirement | What BYTE_COUNT value is read after reset? (Scenario: Midway through a message, with 5 PUSH4 done (BYTE_COUNT 20), rst is asserted for 1 clk while a PUSH4 is written in that same clock; after release BYTE_COUNT and CRC are read.) Two careful readers of the requirements disagree about this; what is the intended behaviour? | readers (RDY-READ-01) |
