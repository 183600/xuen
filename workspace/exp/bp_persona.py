"""Persona layer: (i) which persona features predict where behaviour diversity pays,
(ii) LOO-CV of the capability x difficulty model on the public 8x32 matrix,
(iii) task-level intervention value estimator."""
import sys, json, math, statistics as st
sys.path.insert(0,'exp')
from leaderboard_transcribed import MODELS, TASKS
NAMES=list(MODELS); SR={n:MODELS[n]['sr'] for n in NAMES}
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
def pearson(x,y):
    mx,my=st.mean(x),st.mean(y)
    n=sum((a-mx)*(b-my) for a,b in zip(x,y)); d=math.sqrt(sum((a-mx)**2 for a in x)*sum((b-my)**2 for b in y))
    return n/d if d else 0.0
def logit(p): p=min(max(p,1e-3),1-1e-3); return math.log(p/(1-p))
def sig(x): return 1/(1+math.exp(-x))
def fit(Y,lam=1e-2,iters=8000,lr=0.05):
    M=len(Y);T=len(Y[0]); mu=st.mean(logit(v) for r in Y for v in r)
    a=[0.0]*M;b=[0.0]*T
    for _ in range(iters):
        ga=[0.0]*M;gb=[0.0]*T;gm=0.0
        for i in range(M):
            for j in range(T):
                e=Y[i][j]-sig(mu+a[i]+b[j]);gm+=e;ga[i]+=e;gb[j]+=e
        n=M*T
        a=[a[i]+lr*(ga[i]/n-lam*a[i]) for i in range(M)]
        b=[b[j]+lr*(gb[j]/n-lam*b[j]) for j in range(T)]
        mu+=lr*gm/n
    return mu,a,b

feat={}
for j,t in enumerate(TASKS):
    xs=[SR[n][j] for n in NAMES]
    feat[t]=dict(mean_sr=st.mean(xs), spread=max(xs)-min(xs), sd=st.pstdev(xs),
        demo_s=DS[name2tag[t]]['demo_seconds_per_episode'], frames=DS[name2tag[t]]['frames_per_episode'],
        eps=DS[name2tag[t]]['total_episodes'], rank1=SR[NAMES[0]][j], best=max(xs))
print("=== persona features vs behaviour-diversity (spread) ===")
keys=['mean_sr','rank1','demo_s','frames','eps']
for k in keys:
    print(f"  corr(spread, {k:8s}) = {pearson([feat[t]['spread'] for t in TASKS],[feat[t][k] for t in TASKS]):+.3f}")
print(f"  corr(spread, |mean_sr-30|) = "
      f"{pearson([feat[t]['spread'] for t in TASKS],[abs(feat[t]['mean_sr']-30) for t in TASKS]):+.3f}")
print(f"  corr(spread, log demo_s)  = "
      f"{pearson([feat[t]['spread'] for t in TASKS],[math.log(feat[t]['demo_s']) for t in TASKS]):+.3f}")

print("\n=== LOO-CV: predict an UNSEEN model's per-task score from the other 7 ===")
Y=[[SR[n][j]/100 for j in range(32)] for n in NAMES]
errs=[];avg_err=[]
for h in range(8):
    keep=[i for i in range(8) if i!=h]
    mu,a,b=fit([[Y[i][j] for j in range(32)] for i in keep])
    mu2,a2,b2=fit([[Y[i][j] for j in range(32)] for i in keep])
    # recalibrate global level using the 7 held-in models' residuals (empirical Bayes)
    resid=[Y[i][j]-sig(mu2+a2[keep.index(i)]+b2[j]) for i in keep for j in range(32)]
    off=st.mean(resid)
    pred=[sig(mu2+off+b2[j])*100 for j in range(32)]
    actual=[Y[h][j]*100 for j in range(32)]
    e=st.mean(abs(p-a2_) for p,a2_ in zip(pred,actual))
    errs+= [abs(p-a2_) for p,a2_ in zip(pred,actual)]
    avg_err.append((NAMES[h], st.mean(actual), st.mean(pred), abs(st.mean(actual)-st.mean(pred))))
    print(f"  {NAMES[h]:14s} actual avg {st.mean(actual):5.2f}  predicted {st.mean(pred):5.2f}  "
          f"|err| {abs(st.mean(actual)-st.mean(pred)):5.2f} pp | per-task MAE {e:5.2f} pp")
print(f"  MEAN |per-task error| = {st.mean(errs):.2f} pp ; MEAN |avg-score error| = "
      f"{st.mean([x[3] for x in avg_err]):.2f} pp")

print("\n=== intervention value estimator: if task j were solved at the best observed rate ===")
best=st.mean(max(SR[n][j] for n in NAMES) for j in range(32))
top=NAMES[0]
for j in [i for i,_ in sorted(enumerate(TASKS), key=lambda p:-max(SR[n][p[0]] for n in NAMES)-SR[top][p[0]])][:6]:
    g=max(SR[n][j] for n in NAMES)-SR[top][j]
    print(f"  {TASKS[j]:26s} rank1 {SR[top][j]:5.2f} -> best {max(SR[n][j] for n in NAMES):5.2f} "
          f"=> +{g/32:4.2f} pp on the 32-task average")
print(f"  all 32 tasks at their best observed rate => avg {best:.2f} (+{best-MODELS[top]['avg'][0]:.2f} pp)")
json.dump({"persona":feat}, open("exp/bp_persona.json","w"), indent=1)
