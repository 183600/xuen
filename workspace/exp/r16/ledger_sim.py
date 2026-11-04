"""R16 · IASL projection on MEASURED UniBot-V1 leaderboard parameters (2026-11-04).

Measured inputs (A-level):
  - per-task field mean success rate (8 models, leaderboard_data.json)
  - per-task k = number of scored sub-goals (official tasks_v2/*/info.json scoring_points)
Derived (B-level): p_est = field_mean^(1/k)  (per-sub-goal reliability implied by the field)
Rules (A-level): 10 runs/task, 5 generalization axes x2, 180 s hard cap per run.
"""
import json, glob, re, math, random, statistics as st, itertools

LB = json.load(open('/tmp/opencode/lb.json'))
TASKS, MODELS = LB['tasks'], LB['models']
TAB = {m['model_name']: {t['task']: t for t in m['task_metrics']} for m in MODELS}

def _load(p):
    t = open(p, encoding='utf-8', errors='replace').read(); i = t.find('{')
    try: return json.loads(t[i:t.rfind('}')+1])
    except Exception: return None
norm = lambda s: re.sub(r'[^a-z0-9]', '', s.lower())
META = {}
for p in glob.glob('/tmp/opencode/tasks/*.txt'):
    j = _load(p)
    if not j: continue
    for c in [j.get('en_name',''), j.get('zh_name',''), j.get('slug','')]:
        if c: META.setdefault(norm(c), j)
def find_meta(name):
    n = norm(name)
    if n in META: return META[n]
    for k, j in META.items():
        if k and (k in n or n in k): return j
    return None

KS = {t: len(find_meta(t)['score_steps']) for t in TASKS if find_meta(t)}
FIELD = {t: st.mean(TAB[m['model_name']][t]['success_rate'] for m in MODELS)/100 for t in TASKS}
BEST  = {t: max(TAB[m['model_name']][t]['success_rate'] for m in MODELS)/100 for t in TASKS}
PEST  = {t: FIELD[t]**(1.0/KS[t]) for t in TASKS if t in KS}
HORIZON, N_RUNS, N_HUMAN = 180.0, 10, 2          # official: 180 s cap, 10 runs, 2 human-interference runs

# ---- interference taxonomy, hand-coded from the official per-task notes (tasks_v2/*/info.json)
TAX = {
 'Hang the Cup':'move','Fruit Basket Collection':'move','Pack the Doll':'move','Sort Fruit':'move',
 'Disconnect Ethernet':'ambiguous','Color Arrangement':'move','Place Photo Frames':'move',
 'Organize Bookshelf':'invalidate','Toolbox Storage':'move','Plug Charger':'undo','Pick Out Battery':'invalidate',
 'Unlock':'remove','Arrange Test Tubes':'move','Open Pill Bottle':'undo','Organize Tools':'move',
 'Fold Towel':'undo','Organize Stationery':'undo','Pack Bag':'move','Zip Up':'undo',
 'Paper Cup Stacking':'move','Clear Plates':'invalidate','Spell robot':'move','Store Racket':'move',
 'Conveyor Food Sorting':'move','Stack Cups':'invalidate','Plug In Ethernet':'invalidate',
 'Stack Bowls':'undo','Store Earphones':'move','Pack Phone':'undo','Remove Pinned Note':'move',
 'Organize Pencil Case':'move','Syringe Water Transfer':'move'}

def episode(k, p, rng, retries=0, q_fix=0.0, t_step=8.0, horizon=HORIZON,
            p_inv=0.0, q_redo=0.0, p_false=0.0, p_damage=0.0):
    """One 180 s episode. k scored sub-goals; per-attempt reliability p."""
    used = 0.0
    for j in range(k):
        att = 0
        while True:
            used += t_step
            if used > horizon: return False
            if rng.random() < p: break
            att += 1
            if att > retries: return False
            if rng.random() > q_fix: return False
    # all sub-goals completed; human may now invalidate one of them
    if p_inv > 0 and rng.random() < p_inv:
        used += t_step
        if used > horizon: return False
        if rng.random() < p_false:            # false alarm: redo may damage a good state
            if rng.random() < p_damage: return False
        if rng.random() > q_redo: return False
    return True

def project(n=6000, seed=0, **kw):
    rng = random.Random(seed)
    return {t: sum(episode(KS[t], PEST[t], rng, **kw) for _ in range(n))/n for t in KS}

def avg(d): return st.mean(d.values())

if __name__ == '__main__':
    res = {}
    print('=== A. per-task decomposition (measured) ===')
    print(f"{'task':28s}{'k':>2s}{'field%':>7s}{'best%':>7s}{'p_est%':>8s}{'taxonomy':>12s}")
    for t in sorted(TASKS, key=lambda x: (KS.get(x,99), -FIELD[x])):
        if t in KS:
            print(f"{t:28s}{KS[t]:>2d}{FIELD[t]*100:7.2f}{BEST[t]*100:7.2f}{PEST[t]*100:8.1f}{TAX.get(t,'?'):>12s}")
    print(f"\nfield overall avg = {st.mean([m['avg_success_rate'] for m in MODELS]):.2f}%  "
          f"(re-derived from 30 tasks with k known: {avg(FIELD)*100:.2f}%)")
    print('k dist:', dict(sorted(__import__('collections').Counter(KS.values()).items())))
    def corr(a,b):
        ma,mb=st.mean(a),st.mean(b)
        return sum((x-ma)*(y-mb) for x,y in zip(a,b))/math.sqrt(sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b))
    print('corr(k, field)=%.3f   corr(k, p_est)=%.3f' % (corr([KS[t] for t in KS],[FIELD[t] for t in KS]),
                                                          corr([KS[t] for t in KS],[PEST[t] for t in KS])))

    print('\n=== B. bounded-retry projection (measured p_est only) ===')
    base = avg({t: FIELD[t] for t in KS})
    for R, q in [(0,0.0),(1,0.2),(1,0.3),(1,0.5),(1,0.7),(1,0.9),(2,0.5),(2,0.7)]:
        v = avg(project(retries=R, q_fix=q)); res[f'retry{R}_q{q}']=v
        print(f'  retries={R} q_fix={q:.1f}: {v*100:5.2f}%  ({(v-base)*100:+5.2f}pp vs field)')
    print('\n=== C. deadline sensitivity (180 s official cap) ===')
    for ts in [4,8,15,25,40]:
        v = avg(project(retries=1,q_fix=0.5,t_step=ts)); print(f'  t_step={ts:2d}s: {v*100:5.2f}%')
    print('\n=== D. invalidation handling (undo-type tasks only) ===')
    undo=[t for t in KS if TAX.get(t)=='undo']
    for p_inv,q_redo,p_false,p_dmg in [(0.3,0.7,0.0,0.0),(0.3,0.5,0.05,0.1),(0.5,0.7,0.05,0.1),(0.5,0.9,0.0,0.0)]:
        v=avg(project(retries=1,q_fix=0.5,p_inv=p_inv,q_redo=q_redo,p_false=p_false,p_damage=p_dmg))
        vu=st.mean([project(retries=1,q_fix=0.5,p_inv=p_inv,q_redo=q_redo,p_false=p_false,p_damage=p_dmg)[t] for t in undo])
        print(f'  p_inv={p_inv} q_redo={q_redo} p_false={p_false} p_dmg={p_dmg}: all={v*100:5.2f}%  undo-tasks={vu*100:5.2f}%')
    print('\n=== E. per-axis decomposition sensitivity (10 runs: 8 clean + 2 human) ===')
    print('   assumption: clean-axis per-subgoal p; human-axis success h0 (no ledger) vs h1 (ledger+redo)')
    for p in [0.65,0.70,0.75]:
        for h0 in [0.0,0.05,0.10]:
            field = st.mean([ (8*p**KS[t] + 2*h0)/10 for t in KS])
            h1 = st.mean([ p**KS[t]*(1-0.05) + 0.05*0.7 for t in KS])
            print(f'   p={p:.2f} h0={h0:.2f}: field={field*100:5.2f}%  -> with ledger h1={h1*100:5.2f}%  '
                  f'=> {(h1-field)*100:+5.2f}pp')
    print('\n=== F. priority list (where to spend the 8 tasks of engineering) ===')
    pri=[]
    for t in KS:
        gain_retry=(project(retries=1,q_fix=0.5)[t]-FIELD[t])
        undo_flag=1 if TAX.get(t) in ('undo','invalidate','remove') else 0
        pri.append((FIELD[t],KS[t],BEST[t],TAX.get(t,'?'),gain_retry,undo_flag,t))
    pri.sort(key=lambda r: -(r[4]*100 + 6*r[5]))
    print(f"{'task':28s}{'k':>2s}{'field%':>7s}{'best%':>7s}{'tax':>12s}{'retryΔpp':>9s}")
    for r in pri: print(f"{r[6]:28s}{r[1]:>2d}{r[0]*100:7.2f}{r[2]*100:7.2f}{r[3]:>12s}{r[4]*100:9.2f}")
    json.dump({'KS':KS,'FIELD':FIELD,'BEST':BEST,'PEST':PEST,'TAX':TAX,'res':res},
              open('ledger_results.json','w'),ensure_ascii=False,indent=1)
