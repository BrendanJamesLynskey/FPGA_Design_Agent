import random, statistics as st
dev=[.5,1,1,0,.6,0,1,1,.67,1,1]
random.seed(20261109)
def sim(runs, T=19, reps=400, B=1000):
    hws=[]
    for _ in range(reps):
        p=[random.choice(dev) for _ in range(T)]
        r=[sum(random.random()<q for _ in range(runs))/runs for q in p]
        bs=sorted(st.mean(random.choices(r,k=T)) for _ in range(B))
        hws.append((bs[int(.975*B)]-bs[int(.025*B)])/2)
    return st.mean(hws), sorted(hws)[int(.9*reps)]
for n in (3,5,10): print(n, ["%.3f"%x for x in sim(n)])
