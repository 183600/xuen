"""Benchmark mining: metric structure, task-difficulty factorisation, and
inversion of the (hidden) evaluation timeout from public leaderboard statistics.
Sources: unibot.unitree.com/leaderboard_data.json (2026-11-04);
HF unitreerobotics/G1_Dex1_* meta/info.json (2026-11-04)."""
import sys, json, math, statistics as st, itertools
sys.path.insert(0,'exp')
from leaderboard_transcribed import MODELS, TASKS

NAMES=list(MODELS)
SR={n:MODELS[n]['sr'] for n in NAMES}
SS={n:MODELS[n]['ss'] for n in NAMES}
DUR={n:MODELS[n]['dur'] for n in NAMES}
def pearson(x,y):
    mx,my=st.mean(x),st.mean(y)
    num=sum((a-mx)*(b-my) for a,b in zip(x,y))
    den=math.sqrt(sum((a-mx)**2 for a in x)*sum((b-my)**2 for b in y))
    return num/den if den else 0.0
def fit_line(xs,ys):
    mx,my=st.mean(xs),st.mean(ys)
    sxx=sum((x-mx)**2 for x in xs); sxy=sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    b=sxy/sxx if sxx else 0.0; a=my-b*mx
    pred=[a+b*x for x in xs]
    sse=sum((y-p)**2 for y,p in zip(ys,pred)); sst=sum((y-my)**2 for y in ys)
    return a,b,(1-sse/sst if sst else 0.0)

print("="*78); print("A. METRIC STRUCTURE — is step score a separate optimisation axis?")
ks={}
for n in NAMES:
    a,b,r2=fit_line(SR[n],SS[n]); ks[n]=(b,a,r2)
    print(f"  {n:14s} step = {b:.4f}*SR + {a:+.3f}   R2={r2:.5f}  (rounding floor)")
kb=[v[0] for v in ks.values()]
print(f"  k_model in [{min(kb):.4f},{max(kb):.4f}], mean {st.mean(kb):.4f}, sd {st.stdev(kb):.4f}")
print("  => step score is a per-model affine image of success rate; no independent axis.")

print("="*78); print("B. TWO-WAY CAPABILITY x DIFFICULTY MODEL (logit scale, ridge)")
def logit(p): p=min(max(p,1e-3),1-1e-3); return math.log(p/(1-p))
def sig(x): return 1/(1+math.exp(-x))
Y=[[SR[n][j]/100 for j in range(32)] for n in NAMES]
mu=st.mean(logit(v) for row in Y for v in row); al=[0.0]*8; be=[0.0]*32
for _ in range(6000):
    ga=[0.0]*8; gb=[0.0]*32; gm=0.0
    for i in range(8):
        for j in range(32):
            e=Y[i][j]-sig(mu+al[i]+be[j]); gm+=e; ga[i]+=e; gb[j]+=e
    n=256; lr=0.05; lam=1e-2
    al=[al[i]+lr*(ga[i]/n-lam*al[i]) for i in range(8)]
    be=[be[j]+lr*(gb[j]/n-lam*be[j]) for j in range(32)]
    mu+=lr*gm/n
pred=[[sig(mu+al[i]+be[j])*100 for j in range(32)] for i in range(8)]
mae=st.mean(abs(pred[i][j]-Y[i][j]*100) for i in range(8) for j in range(32))
print(f"  mu={mu:.3f}  mean abs err {mae:.2f} pp")
gm=st.mean(SR[n][j] for n in NAMES for j in range(32))
mm={i:st.mean(SR[n][j] for j in range(32)) for i,n in enumerate(NAMES)}
tm={j:st.mean(SR[n][j] for n in NAMES) for j in range(32)}
ss_m=32*sum((mm[i]-gm)**2 for i in range(8)); ss_t=8*sum((tm[j]-gm)**2 for j in range(32))
ss_r=sum((SR[NAMES[i]][j]-mm[i]-tm[j]+gm)**2 for i in range(8) for j in range(32))
tot=ss_m+ss_t+ss_r
print(f"  variance share: model {ss_m/tot:.3f} | task {ss_t/tot:.3f} | interaction {ss_r/tot:.3f}")

print("="*78); print("C. PER-TASK SPREAD and ORACLE BOUNDS")
oracle=st.mean(max(SR[n][j] for n in NAMES) for j in range(32))
median=st.mean(st.median([SR[n][j] for n in NAMES]) for j in range(32))
top=max(NAMES,key=lambda n:MODELS[n]['avg'][0])
print(f"  best submitted single model ({top}) = {MODELS[top]['avg'][0]:.1f}")
print(f"  per-task median over 8 models        = {median:.2f}")
print(f"  per-task ORACLE (best of 8)          = {oracle:.2f}   (+{oracle-MODELS[top]['avg'][0]:.2f} pp over rank-1)")
print(f"  mean per-task spread (max-min)       = {st.mean(max(SR[n][j] for n in NAMES)-min(SR[n][j] for n in NAMES) for j in range(32)):.2f} pp")
print(f"  tasks where spread > 25 pp: {sum(1 for j in range(32) if max(SR[n][j] for n in NAMES)-min(SR[n][j] for n in NAMES)>25)}/32")
print(f"  tasks where ALL models < 25 pp (capability floor): "
      f"{[TASKS[j] for j in range(32) if max(SR[n][j] for n in NAMES)<25]}")
off=[pearson([SR[NAMES[i]][j] for j in range(32)],[SR[NAMES[k]][j] for j in range(32)])
     for i,k in itertools.combinations(range(8),2)]
print(f"  inter-model per-task rank correlation: mean r={st.mean(off):.3f} (min {min(off):.3f}, max {max(off):.3f})")

print("="*78); print("D. HIDDEN TIMEOUT INVERSION  (per task: regress duration on success rate)")
DS={r['repo'].split('G1_Dex1_')[1]:r for r in json.load(open('exp/unibot_dataset_stats.json'))}
name2tag={"Hang the Cup":"HangCup","Fruit Basket Collection":"FruitCollection","Pack the Doll":"PackDoll",
 "Fruit Sorting":"FruitSorting","Disconnect Ethernet":"DisconnectEthernet","Color Arrangement":"ColorArrangement",
 "Place Photo Frames":"PlacePhotoFrame","Organize Bookshelf":"OrganizeBookshelf","Toolbox Storage":"ToolboxStorage",
 "Plug Charger":"PlugCharger","Pick Out Battery":"PickOutBatteries","Unlock":"Unlock",
 "Arrange Test Tubes":"ArrangeTestTubes","Open Pill Bottle":"PourOutMedicine","Organize Tools":"OrganizeTools",
 "Fold Towel":"FoldTowel","Organize Stationery":"OrganizeStationery","Pack Bag":"PackBag","Zip Up":"ZipUp",
 "Paper Cup Stacking":"PaperCupStacking","Clear Plates":"ArrangePlates","Spell robot":"SpellRobot",
 "Store Racket":"StorePaddle","Conveyor Food Sorting":"ConveyorSorting","Stack Cups":"StoreCups",
 "Plug In Ethernet":"PlugInEthernet","Stack Bowls":"StackBowls","Store Earphones":"StoreEarphones",
 "Pack Phone":"PackPhone","Remove Pinned Note":"RemovePinnedNote","Organize Pencil Case":"OrganizePencilCase",
 "Syringe Water Transfer":"SyringeWaterTransfer"}
rows=[]
print(f"  {'task':26s} {'T_hat':>7s} {'t_succ':>7s} {'R2':>6s} {'slope':>7s} {'demo_s':>7s} {'demo/T':>7s}")
for j,t in enumerate(TASKS):
    xs=[SR[n][j] for n in NAMES]; ys=[DUR[n][j] for n in NAMES]
    a,b,r2=fit_line(xs,ys)
    T=a+b*0.0 if False else a          # duration at SR=0  => timeout-dominated episode
    tsucc=a+b*100                        # duration at SR=100 => successful episode
    demo=DS[name2tag[t]]['demo_seconds_per_episode']
    rows.append((t,a,b,r2,tsucc,demo,a))
    print(f"  {t:26s} {a:7.1f} {tsucc:7.1f} {r2:6.3f} {b:+7.3f} {demo:7.1f} {demo/a if a else 0:7.2f}")
good=[r for r in rows if r[3]>0.3]
print(f"\n  tasks with R2>0.3 (timeout signal credible): {len(good)}/32")
if good:
    print(f"  T_hat  median {st.median([r[5] for r in good]):.1f}s  range [{min(r[5] for r in good):.1f},{max(r[5] for r in good):.1f}]")
    print(f"  t_succ median {st.median([r[4] for r in good]):.1f}s")
    print(f"  demo/timeout ratio median {st.median([r[6]/r[5] for r in good if r[5]]):.2f}")
    print(f"  corr(T_hat, demo_len) = {pearson([r[5] for r in good],[r[6] for r in good]):+.3f}")
    print(f"  corr(slope, demo_len) = {pearson([r[4] for r in good],[r[6] for r in good]):+.3f}")

print("="*78); print("E. WHERE THE POINTS ARE — marginal value of fixing one task")
tot_gain=0; rows2=[]
for j,t in enumerate(TASKS):
    sr_top=SR[top][j]; best=max(SR[n][j] for n in NAMES)
    gain=(best-sr_top)
    rows2.append((gain,t,sr_top,best))
rows2.sort(reverse=True)
print(f"  top-5 tasks where the leaderboard shows the most headroom over rank-1:")
for g,t,s,b in rows2[:5]: print(f"    {t:26s} rank1={s:5.2f} best={b:5.2f} gap={g:5.2f} pp")
print(f"  sum of all 32 gaps = {sum(r[0] for r in rows2):.1f} pp (=> oracle {oracle:.2f} vs {MODELS[top]['avg'][0]:.1f})")

print("="*78); print("F. SPEED / BUDGET VIEW")
print(f"  published avg_duration: " + ", ".join(f"{n}={MODELS[n]['avg'][1]:.2f}s" for n in NAMES))
print(f"  mean demo length (dataset, 30fps) over 32 tasks: "
      f"{st.mean([DS[name2tag[t]]['demo_seconds_per_episode'] for t in TASKS]):.2f}s")
print(f"  demo length range: {min(DS[name2tag[t]]['demo_seconds_per_episode'] for t in TASKS):.1f}s "
      f"(HangCup) .. {max(DS[name2tag[t]]['demo_seconds_per_episode'] for t in TASKS):.1f}s (ToolboxStorage)")
print(f"  corr(demo_len, task difficulty beta) = "
      f"{pearson([DS[name2tag[t]]['demo_seconds_per_episode'] for t in TASKS], be):+.3f}")
json.dump({"per_model_k":ks,"beta":dict(zip(TASKS,be)),"alpha":dict(zip(NAMES,al)),"mu":mu,
 "bounds":{"best_single":MODELS[top]['avg'][0],"median":median,"oracle":oracle},
 "timeout_rows":[(r[0],r[5],r[4],r[3],r[6]) for r in rows]},open("exp/bp_analysis.json","w"),indent=1)
print("\nwrote exp/bp_analysis.json")
