"""Instruction portrait: the official challenge dataset stores ONE task string per
dataset containing 5 '@'-separated paraphrases. Parse them, measure paraphrase
diversity, and evaluate a deterministic instruction->task router under
paraphrase shift (held-out paraphrase + rule-based perturbations)."""
import json, re, random, statistics as st
from collections import Counter
DS=json.load(open('exp/unibot_dataset_stats.json'))
TASK_BY_REPO={}
for r in DS:
    TASK_BY_REPO[r['repo'].split('G1_Dex1_')[1]]=[s.strip() for s in r['instructions'][0].split('@') if s.strip()]
print("datasets:",len(TASK_BY_REPO),"paraphrases per task:",sorted(set(len(v) for v in TASK_BY_REPO.values())))
for k,v in list(TASK_BY_REPO.items())[:2]:
    print(f"\n{k}:")
    for p in v: print("   -",p)

def norm(s):
    s=s.lower().strip()
    s=re.sub(r"[^a-z0-9 ]"," ",s); s=re.sub(r"\s+"," ",s)
    return s
STOP=set("the a an of on in to at into with and or for from by please now then so as is are be it its this that put place".split())
def toks(s): return [w for w in norm(s).split() if w not in STOP]
def ngrams(s,n=3):
    s=" "+norm(s)+" "
    return {s[i:i+n] for i in range(max(1,len(s)-n+1))}
def jacc(a,b):
    return len(a&b)/len(a|b) if (a|b) else 0.0
def cosine_tok(a,b):
    ca,cb=Counter(a),Counter(b)
    dot=sum(ca[k]*cb[k] for k in ca); na=sum(v*v for v in ca.values())**.5; nb=sum(v*v for v in cb.values())**.5
    return dot/(na*nb) if na and nb else 0.0
def score(query, cand):
    return 0.6*cosine_tok(toks(query),toks(cand))+0.4*jacc(ngrams(query),ngrams(cand))

# ---- paraphrase diversity per task ----
print("\n=== paraphrase diversity within a task (max pairwise router-score) ===")
divs=[]
for k,v in TASK_BY_REPO.items():
    best=max(score(a,b) for i,a in enumerate(v) for j,b in enumerate(v) if i!=j)
    divs.append((k,round(best,3)))
divs.sort(key=lambda x:-x[1])
print("most paraphrase-robust tasks (near-duplicates):")
for k,v in divs[:5]: print(f"   {k:26s} max pair score {v}")
print("most paraphrase-fragile tasks (semantically drifted):")
for k,v in divs[-5:]: print(f"   {k:26s} max pair score {v}")
print(f"median within-task max-pair score {st.median([v for _,v in divs]):.3f}")

# ---- router: nearest task by centroid of its paraphrases ----
CENT={k:list(v) for k,v in TASK_BY_REPO.items()}
def route(q):
    sc={k:max(score(q,p) for p in ps) for k,ps in CENT.items()}
    rank=sorted(sc.items(),key=lambda kv:-kv[1])
    return rank[0][0],rank[0][1],rank[1][1]
def evaluate(name,queries):
    ok=0; margins=[]; top1=[]
    for q,gold in queries:
        pred,s1,s2=route(q); ok+= (pred==gold); margins.append(s1-s2); top1.append(s1)
    print(f"  {name:44s} n={len(queries):4d} acc={ok/len(queries):.3f}  mean top1={st.mean(top1):.3f}  mean margin={st.mean(margins):.3f}")
    return ok/len(queries)

Q=[]
for k,v in TASK_BY_REPO.items():
    for p in v: Q.append((p,k))
print("\n=== router on the 160 official instructions (closed set) ===")
evaluate("all 160 official paraphrases",Q)

print("\n=== router under paraphrase shift ===")
random.seed(0)
SYN={"place":"set","put":"position","tidy":"neatly","neatly":"cleanly","arrange":"organise","organize":"tidy",
 "gripper":"claw","robot":"machine","pick":"grasp","grab":"take","hold":"clamp","racket":"paddle",
 "earphones":"headphones","test tubes":"tubes","battery":"batteries","medicine":"pills","pill":"capsule",
 "charger":"plug","cable":"cord","bookshelf":"shelf","stationery":"pens","toolbox":"tool case"}
def mut_drop(s,p=0.2):
    w=s.split(); random.shuffle(w); return " ".join(x for x in w if random.random()>p)
def mut_typo(s,p=0.05):
    out=[]
    for w in s.split():
        if len(w)>3 and random.random()<p:
            i=random.randrange(1,len(w)-1); w=w[:i]+w[i+1]+w[i]+w[i+2:]
        out.append(w)
    return " ".join(out)
def mut_syn(s,p=0.6):
    return " ".join(SYN.get(w.lower(),w) if random.random()<p else w for w in s.split())
def mut_shuffle(s):
    w=s.split(); random.shuffle(w); return " ".join(w)
def mut_case(s): return s.upper()
def mut_compose(s):
    w=s.rstrip('.').split(); random.shuffle(w); return " ".join(w).capitalize()+" please."
sets={
 "word dropout 20%":[mut_drop for _ in range(1)],
 "typos 5%":[mut_typo],
 "synonym substitution 60%":[mut_syn],
 "word order shuffle":[mut_shuffle],
 "UPPERCASE":[mut_case],
 "shuffle+dropout+synonym":[lambda s: mut_syn(mut_drop(mut_shuffle(s),0.15),0.5)],
}
for nm,fns in sets.items():
    QQ=[(fns[0](p),k) for p,k in Q]
    evaluate(nm,QQ)
print("\n=== router on the placeholder instruction used by the official example env ===")
for q in ["move the block to the target position."]:
    p,s1,s2=route(q); print(f"  '{q}' -> {p} (top1 {s1:.3f}, margin {s1-s2:.3f})")
