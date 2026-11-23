#!/bin/bash
# Brief 178 / 178b evaluation driver. Per spec: (1) a synthesis tournament over the whole menu; (2) an implementation tournament on the TOP TWO synthesis
# candidates (brief 178's finding: the synthesis rank alone does not pick the routed winner when candidates are close); (3) the default-synthesis by
# default-implementation baseline, if the default is not already in the top two. Slots are taken inside flow.tournament (one per stage).
# Resumable: a stage whose tournament.json exists is not redone (a tournament in which nothing completed writes no tournament.json, so it is retried).
# 178b fixes: UltraScale+ synthesis children are declared at 4 GiB (2 GiB killed them), the light-class gate falls back to one child alone, and
# implementation gets the top-2 ids through --from (the old driver passed an empty or "None" id after a failed synthesis).
cd "$(dirname "$0")/../.." || exit 1
S=results/178_tournament/specs
IMPL_MENU=default,explore,extra_timing,extra_netdelay,aggressive,congestion,amd:Performance_Explore,amd:Performance_ExtraTimingOpt,amd:Performance_NetDelay_high,amd:Performance_RefinePlacement
[ -f results/178_tournament/vendor_strategies.json ] || python3 -m flow.tournament strategies
for f in $S/*.yaml; do
  n=$(basename "$f" .yaml)
  B=build/tournament/$n
  [ -f $B/synth/tournament.json ] || python3 -m flow.tournament run "$f" --stage synth --k 2 --jobs 3 || { echo "driver: synthesis failed for $n"; continue; }
  top2=$(python3 -c "import json;c=[c['id'] for c in json.load(open('$B/synth/tournament.json'))['candidates'] if c['status']=='ok'];print(','.join(c[:2]))")
  [ -n "$top2" ] || { echo "driver: no synthesis candidate for $n"; continue; }
  [ -f $B/impl_top2/tournament.json ] || python3 -m flow.tournament run "$f" --stage impl --from "$top2" --menu "$IMPL_MENU" --tag top2 --k 2
  case ",$top2," in
    *,default,*) ;;
    *) [ -f $B/impl_base/tournament.json ] || python3 -m flow.tournament run "$f" --stage impl --from default --menu default --tag base --k 1 ;;
  esac
done
