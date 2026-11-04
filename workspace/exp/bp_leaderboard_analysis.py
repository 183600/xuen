"""Benchmark mining on the public UniBot-V1 leaderboard JSON.
Fits a two-way difficulty/capability model on logit(SR) and quantifies
headroom for task-conditional (persona-routed) behaviour.
"""
import json, math, itertools, statistics as st
from pathlib import Path

URL = "https://unibot.unitree.com/leaderboard_data.json"
raw = Path("exp/leaderboard_data.json")
if not raw.exists():
    import urllib.request
    raw.write_bytes(urllib.request.urlopen(URL, timeout=60).read())
D = json.loads(raw.read_text())

tasks = D["tasks"]
models = D["models"]
names = [m["model_name"] for m in models]
SR = {m["model_name"]: {t["task"]: t["success_rate"] for t in m["task_metrics"]} for m in models}
SS = {m["model_name"]: {t["task"]: t["step_score"] for t in m["task_metrics"]} for m in models}
DUR = {m["model_name"]: {t["task"]: t["avg_duration_sec"] for t in m["task_metrics"]} for m in models}

def logit(p, eps=1e-3):
    p = min(max(p, eps), 1-eps)
    return math.log(p/(1-p))

def sigmoid(x):
    return 1/(1+math.exp(-x))

# ---------- 1. metric structure: is step score a separate axis? ----------
print("=== 1. step-score vs success-rate (per model affine fit) ===")
rows=[]
for m in models:
    xs=[SR[m["model_name"]][t] for t in tasks]
    ys=[SS[m["model_name"]][t] for t in tasks]
    k=sum(x*y for x,y in zip(xs,ys))/sum(x*x for x in xs)
    pred=[k*x for x in xs]
    ss_res=sum((y-p)**2 for y,p in zip(ys,pred)); ss_tot=sum((y-st.mean(ys))**2 for y in ys)
    rows.append((m["model_name"], m["avg_success_rate"], m["avg_step_score"], k, 1-ss_res/ss_tot,
                 m["avg_duration_sec"]))
print(f"{'model':16s} {'SR':>6s} {'step':>6s} {'k':>7s} {'R2':>7s} {'dur':>6s}")
for r in rows: print(f"{r[0]:16s} {r[1]:6.2f} {r[2]:6.2f} {r[3]:7.4f} {r[4]:7.5f} {r[5]:6.2f}")
ks=[r[3] for r in rows]
print(f"k range [{min(ks):.4f},{max(ks):.4f}] mean {st.mean(ks):.4f} sd {st.stdev(ks):.4f}")

# ---------- 2. two-way model on logit scale (ridge, gradient descent) ----------
def fit_two_way(Y, lam=1e-2, iters=4000, lr=0.05):
    M, T = len(Y), len(Y[0])
    mu = st.mean(logit(v) for row in Y for v in row)
    a=[0.0]*M; b=[0.0]*T
    def pred(i,j): return sigmoid(mu+a[i]+b[j])
    for _ in range(iters):
        ga=[0.0]*M; gb=[0.0]*T; gm=0.0
        for i in range(M):
            for j in range(T):
                p=pred(i,j); e=Y[i][j]-p
                gm+=e; ga[i]+=e; gb[j]+=e
        n=M*T
        a=[a[i]-lr*(ga[i]/n+lam*a[i]) for i in range(M)]
        b=[b[j]-lr*(gb[j]/n+lam*b[j]) for j in range(T)]
        mu=mu-lr*gm/n
    return mu,a,b

Y=[[SR[n][t]/100.0 for t in tasks] for n in names]
mu,a,b=fit_two_way(Y)
print("\n=== 2. two-way difficulty/capability fit (logit) ===")
print(f"mu={mu:.3f}")
fit=[[sigmoid(mu+a[i]+b[j])*100 for j in range(len(tasks))] for i in range(len(names))]
err=[abs(fit[i][j]-Y[i][j]*100) for i in range(len(names)) for j in range(len(tasks))]
print(f"mean abs err (pp): {st.mean(err):.2f}  max {max(err):.2f}")
print("\nmodel capability alpha (logit):")
for i,n in enumerate(names): print(f"  {n:16s} a={a[i]:+.3f}  fit_avg={st.mean(fit[i]):5.2f} (actual {st.mean(Y[i])*100:5.2f})")

# variance decomposition on residual of additive model
tot=[]; 
for i in range(len(names)):
    for j in range(len(tasks)):
        tot.append(Y[i][j]*100)
gm=st.mean(tot)
resid=[]; task_mean={}; model_mean={}
for j,t in enumerate(tasks):
    task_mean[j]=st.mean([Y[i][j]*100 for i in range(len(names))])
for i,n in enumerate(names):
    model_mean[i]=st.mean([Y[i][j]*100 for j in range(len(tasks))])
for i in range(len(names)):
    for j in range(len(tasks)):
        resid.append(Y[i][j]*100 - model_mean[i] - task_mean[j] + gm)
ss_res=sum(r*r for r in resid)
ss_model=len(tasks)*sum((model_mean[i]-gm)**2 for i in range(len(names)))
ss_task=len(names)*sum((task_mean[j]-gm)**2 for j in range(len(tasks)))
print(f"\nvariance share: model {ss_model/(ss_model+ss_task+ss_res):.3f}  task {ss_task/(ss_model+ss_task+ss_res):.3f}  interaction {ss_res/(ss_model+ss_task+ss_res):.3f}")

# ---------- 3. per-task table + headroom ----------
print("\n=== 3. per-task leaderboard spread (32 tasks x 8 models) ===")
print(f"{'task':26s} {'mean':>6s} {'min':>6s} {'max':>6s} {'spread':>7s} {'sd':>6s} {'b_model':>7s} {'dur':>6s}")
tab=[]
for j,t in enumerate(tasks):
    xs=[SR[n][t] for n in names]
    durs=[DUR[n][t] for n in names]
    best=names[xs.index(max(xs))]
    tab.append((t, st.mean(xs), min(xs), max(xs), max(xs)-min(xs), st.pstdev(xs), best, st.mean(durs), b[j]))
for r in sorted(tab, key=lambda r:-r[4]):
    print(f"{r[0]:26s} {r[1]:6.2f} {r[2]:6.2f} {r[3]:6.2f} {r[4]:7.2f} {r[5]:6.2f} {r[6]:>7s} {r[7]:6.2f}")

# ---------- 4. oracle / routing bounds ----------
avg_top=max(m["avg_success_rate"] for m in models)
oracle_task=st.mean(max(SR[n][t] for n in names) for t in tasks)
median_task=st.mean(st.median([SR[n][t] for n in names]) for t in tasks)
print("\n=== 4. headroom bounds (avg over 32 tasks) ===")
print(f"best single submitted model        : {avg_top:6.2f}  (leaderboard rank 1)")
print(f"per-task MEDIAN of the 8 models    : {median_task:6.2f}   <- 'generic model' reference")
print(f"per-task ORACLE (best of 8)       : {oracle_task:6.2f}   <- ceiling if we could pick the right behaviour per task")
print(f"headroom over median              : {oracle_task-median_task:+6.2f} pp")
print(f"headroom over rank-1              : {oracle_task-avg_top:+6.2f} pp")

# ---------- 5. rank agreement: do models fail on the same tasks? ----------
print("\n=== 5. inter-model rank correlation on per-task SR ===")
def pearson(x,y):
    mx,my=st.mean(x),st.mean(y)
    num=sum((a-mx)*(b-my) for a,b in zip(x,y))
    den=math.sqrt(sum((a-mx)**2 for a in x)*sum((b-my)**2 for b in y))
    return num/den if den else 0
C=[[0]*len(names) for _ in names]
for i,j in itertools.combinations(range(len(names)),2):
    r=pearson([SR[names[i]][t] for t in tasks],[SR[names[j]][t] for t in tasks])
    C[i][j]=C[j][i]=r
off=[C[i][j] for i,j in itertools.combinations(range(len(names)),2)]
print(f"mean pairwise r = {st.mean(off):.3f}  min {min(off):.3f}  max {max(off):.3f}")

# ---------- 6. top model's per-task loss budget ----------
top=max(models,key=lambda m:m["avg_success_rate"])
print(f"\n=== 6. loss budget of rank-1 model {top['model_name']} (SR {top['avg_success_rate']}) ===")
loss=[]
for t in tasks:
    sr=SR[top["model_name"]][t]
    gain=oracle_task # placeholder
    loss.append((100-sr, t, sr, max(SR[n][t] for n in names)))
loss.sort(reverse=True)
print("largest absolute point losses (pp of 100) and best-in-class for that task:")
for l in loss[:10]:
    print(f"  {l[1]:26s} own={l[2]:5.2f}  best={l[3]:5.2f} ({names[[SR[n][l[1]] for n in names].index(l[3])]})")

# ---------- 7. duration vs success ----------
print("\n=== 7. duration structure ===")
for i,n in enumerate(names):
    ds=[DUR[n][t] for t in tasks]; ss=[SR[n][t] for t in tasks]
    print(f"  {n:16s} dur mean {st.mean(ds):5.2f}s  min {min(ds):5.2f}  max {max(ds):5.2f}  r(dur,SR)={pearson(ds,ss):+.3f}")
allm=[DUR[n][t] for n in names for t in tasks]
print(f"  fleet duration: mean {st.mean(allm):.2f}s  p95 {sorted(allm)[int(.95*len(allm))]:.2f}s  max {max(allm):.2f}s")

Path("exp/bp_leaderboard_analysis.json").write_text(json.dumps({
 "metric": [{"model":r[0],"avg_sr":r[1],"avg_step":r[2],"k":r[3],"r2":r[4],"dur":r[5]} for r in rows],
 "two_way": {"mu":mu,"alpha":dict(zip(names,a)),"beta":dict(zip(tasks,b)),
             "mean_abs_err_pp":st.mean(err),
             "var_share":{"model":ss_model/(ss_model+ss_task+ss_res),"task":ss_task/(ss_model+ss_task+ss_res),"interaction":ss_res/(ss_model+ss_task+ss_res)}},
 "bounds": {"best_single":avg_top,"median_task":median_task,"oracle_task":oracle_task},
 "per_task": [{"task":r[0],"mean":r[1],"min":r[2],"max":r[3],"spread":r[4],"sd":r[5],"best_model":r[6],"mean_dur":r[7],"beta":r[8]} for r in tab],
 "inter_model_r": {"mean":st.mean(off),"min":min(off),"max":max(off)},
}, indent=1))
print("\nwrote exp/bp_leaderboard_analysis.json")
