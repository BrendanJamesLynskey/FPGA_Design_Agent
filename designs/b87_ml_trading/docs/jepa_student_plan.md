# Arm (d), phase 2 plan: a JEPA-pretrained encoder distilled into a fabric-sized student

Status: **plan only**. Nothing in this folder trains or builds arm (d) yet.

## The question

A joint-embedding predictive architecture (JEPA) learns a representation by predicting the embedding of a hidden part
of the input from the embedding of a visible part, without labels. It is a representation and world-model learner,
not a decision rule. The question for this design is narrow: does pretraining on unlabelled order flow, then
distilling into a student no larger than the phase-1 arms, give better test accuracy than training that student
directly on the labels, at the same latency?

## Data

- Pretraining: unlabelled sessions from `model/lobsim.py` with new seeds (5001 onwards), many more events than the
  labelled train split (for example 200 sessions of 10,000 events). The same microstructure parameters, plus a second
  set with a different event mix, so the encoder cannot rely on one parameter set.
- Labelled data for the head and the student: the phase-1 train split unchanged; the phase-1 validation and test
  splits unchanged, so the result is comparable with the arms here.
- No real market data. A public academic order-book dataset only after a licence check recorded in the report.

## Encoder (teacher)

- Input: a window of the last 32 events, each as the integer features of `model/lobsim.py` plus the event type and
  side (no hidden value, no future).
- Context encoder and target encoder: small transformers or 1-D convolutions, about 50k-200k parameters, CPU-trainable.
- Target: the embedding of the next 8 events' window (the target encoder an exponential moving average of the
  context encoder, as in I-JEPA and V-JEPA); a predictor maps context embedding to target embedding; loss in
  embedding space, with a variance term against collapse.
- Probe: a linear head on the frozen embedding, trained on the labelled train split, scored on validation. If the
  probe does not beat the phase-1 MLP on validation, stop: the student has nothing to distil.

## Student (the fabric part)

- Size budget: at most the phase-1 MLP's cost at its closed clock (results/b87/ooc/mlp_hand.json), and a latency of
  at most 8 clocks at 125 MHz so that it fits the 58A decision slot (the trigger_core check).
- Inputs: the same seven integer features the fabric already computes (no new feature logic), or at most three
  extra history registers, each costed.
- Training: distillation from the teacher's probe outputs (soft labels, temperature chosen on validation) plus the
  hard labels; then the same quantisation-aware fine-tuning and integer model as arm (b), so the RTL generator and
  the bit-exact test apply unchanged.

## Measurements and decision

- The pre-registered comparison: student distilled from the JEPA teacher against the same student trained on the
  labels only, paired over the 10 test sessions, three seeds each. A null is reported as a null.
- Hardware: the phase-1 OOC flow and the determinism test, unchanged.
- The fast/slow split (a larger model re-estimating the student's thresholds or weights every millisecond through
  the register map) is a separate experiment: it needs a weight-loading path in the RTL, which phase 1 does not have.

## Cost and risks

- CPU only, under the 5 GB memory scope; the teacher sized so that pretraining takes under an hour.
- Risk: on this synthetic generator the label depends on few features, so a learned representation may add
  nothing. That is a useful result and says the generator, not the method, limits the test; a richer generator
  (several instruments, hidden regimes) would be the next step.
