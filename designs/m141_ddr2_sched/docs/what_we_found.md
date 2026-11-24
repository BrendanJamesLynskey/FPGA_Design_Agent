# What we found in phase 0 (brief 141)

The question: can we build memory controllers optimised for an application? The answer from phase 0, with the numbers that back each point (all simulation, `nexys_650` profile, command-bus clocks of 3077 ps; records in `results/b141`).

## The policy that wins depends on the traffic

- **Random reads, light load: eager precharge is worth exactly tRP.** Median read latency 12 clocks for the latency-first policy against 17 for the open-page policy; the difference is the five-clock PRECHARGE the open-page policy pays before every ACTIVATE on a miss.
- **Related reads (bursts at one address): open page wins.** Median 7 clocks against 12; the later reads of a burst hit the open row. Locality decides.
- **Streams of reads: no policy is needed.** Both policies and all three address maps keep the data bus 0.98 busy.
- **Streams that mix directions (a copy): batching and bank interleaving matter.** 0.67 to 0.86 utilisation across policy and map; bandwidth-first with every burst to the next bank is best (0.86); a deeper queue adds a few points and costs latency.
- **Random mixed traffic at saturation: latency-first is better** (0.735 against 0.665) with about the same number of bus turnarounds (371 and 352), so direction batching does not explain it; eager precharge hiding tRP behind other work is the likely cause and was not isolated.

## Refresh placement is a tail-latency tool, and it moves the tail, it does not remove it

Postponing refresh (`REF_POST` 4) and deferring in a window keeps the window clean (maximum read latency inside the window 28 clocks against 73 with no postponement), and the cost lands after the window (maximum 91 against 73 outside it), because the postponed refreshes are done back to back. This is a trade the application chooses by when it drives `ref_defer`.

## What the simulations found that the proofs could not

`AGE_LIM` is a performance parameter as well as a bound. At 64 clocks the bandwidth-first copy run fell to 0.22 utilisation from 0.76: in a full queue every request is older than the limit, so the oldest is always served alone and the queue degenerates to first-come first-served. The default became 1024.
The bench's own tag allocator also taught one rule worth stating in the contract: tags must be unique among queued requests (a deeper queue held a request older than the tag space, and a reused tag looked like a scheduler bug).

## What the proofs found about the method

- The rules are simple to state and the proofs are simple once the right **helper invariants** are written down: each RTL down-counter is at least N - 1 minus the age of the event as the bus shows it. Property-directed reachability alone did not converge on the real constants; k-induction at depth 3 proves every rule in seconds with them.
- A bounded check is not a proof, and a mutant is the test of a property: the aging mutant was **missed** by a check shorter than the bound it was supposed to violate, and caught once the depth exceeded it.
- tRC is implied by tRAS + tRP at these data sheet values, so a short tRC alone cannot be seen on the bus. A read-to-write spacing mutant is invisible to random traffic (a write must find its row already open); the hazard pattern finds it. The traffic list in the faults test records which pattern finds which bug.

## What MIG offers (UG586 v4.2) and what that means for the next phase

User-controlled refresh (`USER_REFRESH` on, `app_ref_req` / `app_ref_ack`) already gives level A the refresh lever. The PHY can be used without the controller (UG586, "Physical Layer Interface (Non-Memory Controller Design)"), with periodic reads and the temperature sample enable left to the user: that is level B, the path for the full scheduler. Neither has been built or run here.

## Dead ends and costs

Boolector's bounded checks took seconds a step at depth 16 on this design (the unrolled queue and timer file are large); ABC's bounded model check was far faster at depth 100 and its induction was not needed once the invariants existed. Both heavy slots were taken by other sessions, so no Vivado number exists.
