#!/bin/bash
# Brief 178 evaluation driver: the probe, then for each spec a synthesis tournament (all menu entries, light class), a rank study (every
# synthesis candidate through the default place and route) and an implementation tournament on the best synthesis candidate.
# Slots are taken inside flow.tournament (one per stage). Resumable: a finished tournament.json is not redone.
cd "$(dirname "$0")/../.." || exit 1
S=results/178_tournament/specs
[ -f results/178_tournament/vendor_strategies.json ] || python3 -m flow.tournament strategies
for f in $S/*.yaml; do
  n=$(basename "$f" .yaml)
  B=build/tournament/$n
  [ -f $B/synth/tournament.json ] || python3 -m flow.tournament run "$f" --stage synth --k 2 --jobs 3
  ids=$(python3 -c "import json;print(','.join(c['id'] for c in json.load(open('$B/synth/tournament.json'))['candidates'] if c['status']=='ok'))")
  [ -f $B/impl_study/tournament.json ] || python3 -m flow.tournament run "$f" --stage impl --from "$ids" --menu default --tag study --k 1
  best=$(python3 -c "import json;print(json.load(open('$B/synth/tournament.json'))['winner'])")
  [ -f $B/impl_best/tournament.json ] || python3 -m flow.tournament run "$f" --stage impl --from "$best" --tag best --k 1
  [ -f $B/impl_default/tournament.json ] || python3 -m flow.tournament run "$f" --stage impl --from default --tag default --k 1
done
