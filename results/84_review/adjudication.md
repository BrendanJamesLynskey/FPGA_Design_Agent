# Adjudication of unmatched findings (read by the executor, from the design text; not a model)

Per the pre-registration, unmatched major or critical findings on the three held-out controls (r1 of each) were read. They are
reported apart from precision and recall.

| Control | Finding (shortened) | Judgement |
|---|---|---|
| stream slice bench | stimulus decides "accepted" from the ready flag after the edge | reasonable observation about the bench, not a defect that hides a design bug; severity high |
| pulse bridge | independent resets can lose or add a pulse | already documented in the block's clocking note: not a new finding |
| pulse bridge bench | varied clock phase and minimum spacing not exercised | partly true (the bench steps 6 to 12 clocks); not a defect |
| latency bench (control) | the bench does not check the latency it prints | **real, unplanted**: the pass rule accepts any latency from 1 to 8. The control was not perfectly clean |

Of the 146 false alarms over the 47 held-out agent reviews, 70 are in category verification (46 at major): a reviewer can nearly always
find something a bench does not exercise. The rater's finding-level ratings on six reviews are in `usefulness_rating.md`.
