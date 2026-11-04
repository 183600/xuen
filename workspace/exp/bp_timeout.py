"""Global timeout inversion: fit  dur_{m,t} = SR_{m,t} * c * H_t + (1-SR_{m,t}) * T
with a single global timeout T and a single efficiency factor c (successful
episodes take c x the expert demo length). 256 observations, 2 unknowns."""
import sys, json, math, statistics as st
sys.path.insert(0,'exp')
from leaderboard_transcribed import MODELS, TASKS
DS={r['repo'].split('G1_Dex1_')[1]:r for r in json.load(open('exp/unibot_dataset_stats.json'))}
tag={"Hang the Cup":"HangCup","Fruit Basket Collection":"FruitCollection","Pack the Doll":"PackDoll",
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
H=[DS[tag[t]]['demo_seconds_per_episode'] for t in TASKS]
X=[];Y=[]
for n,m in MODELS.items():
    for j in range(32):
        sr=m['sr'][j]/100
        X.append([sr*H[j], 1-sr]); Y.append(m['dur'][j])
# normal equations for 2x2 least squares
a11=sum(r[0]*r[0] for r in X); a12=sum(r[0]*r[1] for r in X); a22=sum(r[1]*r[1] for r in X)
b1=sum(r[0]*y for r,y in zip(X,Y)); b2=sum(r[1]*y for r,y in zip(X,Y))
det=a11*a22-a12*a12
c=(b1*a22-b2*a12)/det; T=(a11*b2-a12*b1)/det
pred=[c*r[0]+T*r[1] for r in X]
sse=sum((y-p)**2 for y,p in zip(Y,pred)); sst=sum((y-st.mean(Y))**2 for y in Y)
print(f"GLOBAL fit: c={c:.3f} (success episode = {c:.2f} x expert demo length), T={T:.1f}s")
print(f"  R2 = {1-sse/sst:.4f}   RMSE = {(sse/len(Y))**0.5:.2f}s   (baseline mean-only RMSE {(sst/len(Y))**0.5:.2f}s)")
# per-task fits for reference
r2s=[]
for j in range(32):
    xs=[m['sr'][j] for m in MODELS.values()]; ys=[m['dur'][j] for m in MODELS.values()]
    mx,my=st.mean(xs),st.mean(ys); sxx=sum((x-mx)**2 for x in xs); sxy=sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    b=sxy/sxx if sxx else 0; a=my-b*mx
    pr=[a+b*x for x in xs]; e=sum((y-p)**2 for y,p in zip(ys,pr)); tt=sum((y-my)**2 for y in ys)
    r2s.append(1-e/tt if tt else 0)
print(f"  per-task R2: median {st.median(r2s):.3f}, max {max(r2s):.3f}, #>0.3: {sum(1 for r in r2s if r>0.3)}/32")
# control: same fit on a synthetic set with a known timeout
import random
random.seed(0)
Xs=[];Ys=[]
for m in MODELS.values():
    for j in range(32):
        sr=m['sr'][j]/100
        ok=random.random()<sr; d=(1.35*H[j]) if ok else 60.0
        Xs.append([sr*H[j],1-sr]); Ys.append(d)
a11=sum(r[0]*r[0] for r in Xs);a12=sum(r[0]*r[1] for r in Xs);a22=sum(r[1]*r[1] for r in Xs)
b1=sum(r[0]*y for r,y in zip(Xs,Ys));b2=sum(r[1]*y for r,y in zip(Xs,Ys));det=a11*a22-a12*a12
cs=(b1*a22-b2*a12)/det; Ts=(a11*b2-a12*b1)/det
pr=[cs*r[0]+Ts*r[1] for r in Xs]; sse=sum((y-p)**2 for y,p in zip(Ys,pr)); sst=sum((y-st.mean(Ys))**2 for y in Ys)
print(f"  CONTROL (synthetic, true T=60s, c=1.35): recovered c={cs:.3f} T={Ts:.1f}s  R2={1-sse/sst:.4f}")
