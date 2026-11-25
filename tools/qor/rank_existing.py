"""Brief 178 part 1: does the early (post-synthesis, post-place) WNS rank the routed WNS? From the 177 dataset (gates rows only: the arith rows
have no post-synthesis timing). Spearman rho and top-1 agreement, pooled and within one design (the candidate-set case).

    python3 tools/qor/rank_existing.py
"""
import csv,collections,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
import numpy as np
def rank(a):
    a=np.asarray(a,float); o=a.argsort(); r=np.empty(len(a)); i=0
    s=a[o]
    while i<len(a):
        j=i
        while j+1<len(a) and s[j+1]==s[i]: j+=1
        r[o[i:j+1]]=(i+j)/2+1; i=j+1
    return r
def sp(x,y):
    if len(x)<3: return None
    rx,ry=rank(x),rank(y)
    if rx.std()==0 or ry.std()==0: return None
    return float(np.corrcoef(rx,ry)[0,1])
r=[x for x in csv.DictReader(open(ROOT/'results/177_qor/dataset.csv')) if x['source']=='gates' and x['syn_wns'] and x['pl_wns'] and x['rt_wns']]
f=lambda x,k: float(x[k])
out={'n':len(r)}
S=[f(x,'syn_wns') for x in r];P=[f(x,'pl_wns') for x in r];R=[f(x,'rt_wns') for x in r]
out['pooled_syn_vs_rt']=sp(S,R); out['pooled_pl_vs_rt']=sp(P,R)
# slack-vs-clock normalised not available; within-design
g=collections.defaultdict(list)
for x in r:
    # same design AND same part AND same vivado (candidate set = variants of one design)
    g[(x['group'],x['part'],x['vivado'])].append(x)
rows=[]
for k,v in sorted(g.items()):
    if len(v)<3: continue
    s=[f(x,'syn_wns') for x in v];p=[f(x,'pl_wns') for x in v];rt=[f(x,'rt_wns') for x in v]
    rows.append(dict(group=k[0],part=k[1],vivado=k[2],n=len(v),syn_rho=sp(s,rt),pl_rho=sp(p,rt),
      best_syn_is_best_rt=int(np.argmax(s)==np.argmax(rt)),best_pl_is_best_rt=int(np.argmax(p)==np.argmax(rt)),
      rt_best=max(rt),rt_of_best_syn=rt[int(np.argmax(s))],rt_of_best_pl=rt[int(np.argmax(p))],rt_spread=max(rt)-min(rt)))
out['groups']=rows
for x in rows: print(x)
print({k:v for k,v in out.items() if k!='groups'})
json.dump(out,open(ROOT/'results/178_tournament/part1_existing_data.json','w'),indent=1)
