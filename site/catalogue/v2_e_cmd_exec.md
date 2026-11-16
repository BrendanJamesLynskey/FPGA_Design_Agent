# Command executor and register file (v2_e_cmd_exec)

Domain E (networking), tier T2 (L1 probe of the endpoint ladder), Nexys A7-100T. Part of the UDP command and telemetry endpoint ladder project (brief 82). Draft for the problem catalogue; the task files are in
`benchmark/v2/tasks/v2_e_cmd_exec/`.

## The problem, and where it is used

The part of a command protocol that carries out screened commands on a bank of eight registers and records the outcome.

Every register-over-network or register-over-serial interface has this core: read, write, status and stream control against registers with read-only, read-write and counter semantics, and a result code that tells the host exactly why a command was refused.

## Hero diagram

A command with its parameters is staged and run. The bank lights up the register touched; a refusal flashes the reason code and bumps the error count without touching anything else; counters shown before the command is counted.

## Animation plan (driven by `hidden/model.py`)

Use Model.go() from hidden/model.py to run commands and show the bank, the result code, the read value and the counters, with a command palette including the refused ones.

## Interface

Shell registers: TYP, P0, P1, GO, CODE, RDATA, TICK, REFUSED, TLM and a direct view of the bank. LED[15:0] shows the low bytes of the two counters.

## Acceptance criteria in plain words

Read and write act on the bank; read-only registers refuse writes with code 5; register numbers of 8 or more give code 3 and unknown types code 1; a successful command counts in CMDS, a refused one in ERRS and changes nothing else; telemetry start sets the period (raised to 4; zero keeps it) and switches telemetry on; counters read before the command is counted.
