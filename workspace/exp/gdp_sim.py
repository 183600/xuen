#!/usr/bin/env python3
"""GDP/TPL synthetic mechanism check (declared toy model).

Question: under the challenge's documented REGRESSIVE human interference,
does *anticipating* the interfering hand gesture (GDP) plus a *dependency-aware
minimal rollback ledger* (TPL) beat (a) no recovery, (b) full restart,
(c) reactive redo of the whole suffix, and (d) reactive minimal rollback?

All outcomes are generative. Rubric weights and chain/set topology labels come
from public task metadata already stored in this repo; per-subgoal competence
p=0.6 and the attempt budget are declared synthetic values.
"""
import json, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 20261113
N_EP = 40000
P_SUB = 0.60
D_DEFEND = 0.75
LAMBDA_FLAG = 0.45
LAMBDA_OTHER = 0.08
DELTA_REACT = 0.80

prof = json.load(open(os.path.join(HERE, "r16_task_profile.json")))["tasks"]
audit = {t["task"]: t for t in json.load(open(os.path.join(HERE, "mats_stepscore_audit.json")))["tasks"]}
REGRESS = {"T05","T08","T10","T11","T12","T14","T16","T17","T19","T24","T25","T26","T27","T29"}

TASKS = []
for tid, t in prof.items():
    topo = audit.get(t["name"], {}).get("topo", "chain")
    TASKS.append(dict(id=tid, w=np.array(t["w"], float), n=len(t["w"]), topo=topo,
                      reg=(tid in REGRESS)))

def closure(t, j):
    if t["topo"] == "set":
        return [j]
    if t["topo"] == "chain+set":
        return list(range(j, t["n"])) if (j % 2 == 0) else [j]
    return list(range(j, t["n"]))

def attempt(t, idx, done, rng, budget):
    """One physical attempt on subgoal idx. Returns (success, used_delta)."""
    done[idx] = rng.random() < P_SUB
    return done[idx]

def run(t, policy, rng, g_ant=0.0):
    n = t["n"]; budget = int(round(2.2 * n)); used = 0
    done = np.zeros(n, bool)
    lam = LAMBDA_FLAG if t["reg"] else LAMBDA_OTHER
    disturbed = False
    # ---- sequential execution of the ordered rubric
    while used < budget and not done.all():
        j = int(np.flatnonzero(~done)[0])
        used += 1
        if not (rng.random() < P_SUB):
            break                       # ordered rubric: cannot skip a failure
        done[j] = True
        if disturbed or rng.random() >= lam:
            continue
        disturbed = True
        # ---- human gesture begins: choose a target among completed subgoals
        completed = [int(k) for k in np.flatnonzero(done)]
        target = int(completed[-1] if rng.random() < 0.7 else rng.choice(completed))
        invalid = [k for k in closure(t, target) if k in completed]
        naive = [k for k in completed if k >= min(invalid)]
        # ---- GDP: gesture is observable for a short lead window
        prevented = False
        if policy == "gap_tpl" and rng.random() < g_ant * D_DEFEND:
            prevented = True
            used += 1                   # one defensive action
        if prevented:
            continue
        # ---- undo executes
        for k in invalid:
            done[k] = False
        if policy == "none":
            break
        if policy == "restart":
            done[:] = False
            continue
        if rng.random() >= DELTA_REACT:
            break                       # undetected undo: credit lost, stop
        redo = naive if policy == "react_naive" else invalid
        for k in redo:
            if used >= budget:
                break
            used += 1
            if not (rng.random() < P_SUB):
                break                   # failed recovery: episode ends
            done[k] = True
    score = float((t["w"] * done).sum())
    return score, bool(done.all()), used

def evaluate(policy, g_ant=0.0, seed=1):
    rng = np.random.default_rng(seed)
    sc, su, us = [], [], []
    for _ in range(N_EP):
        t = TASKS[rng.integers(len(TASKS))]
        a, b, c = run(t, policy, rng, g_ant)
        sc.append(a); su.append(b); us.append(c)
    return dict(step=round(float(np.mean(sc)),2), succ=round(float(np.mean(su)),4),
                attempts=round(float(np.mean(us)),2))

def evaluate_subset(policy, topo, seed=2):
    rng = np.random.default_rng(seed)
    ts = [t for t in TASKS if t["topo"] == topo]
    return round(float(np.mean([run(ts[rng.integers(len(ts))], policy, rng, 0.0)[0]
                                for _ in range(N_EP)])), 2)

res = {"meta": {"date":"2026-11-13","seed":SEED,"n_ep":N_EP,"p_sub":P_SUB,
                "budget":"2.2*n attempts/episode","note":"declared generative toy"}}
res["policies"] = {p: evaluate(p, seed=SEED) for p in
                   ["none","restart","react_naive","react_tpl"]}
res["gesture_sweep"] = [{"g_ant": g, **evaluate("gap_tpl", g, SEED)}
                        for g in [0.0,0.25,0.5,0.75,0.9,1.0]]
res["topology"] = {topo: {p: evaluate_subset(p, topo) for p in ["react_naive","react_tpl"]}
                   for topo in ["chain","set","chain+set"]}
json.dump(res, open(os.path.join(HERE,"gdp_sim_results.json"),"w"), indent=1, ensure_ascii=False)

print("policy        step   succ  attempts")
for k,v in res["policies"].items():
    print(f"{k:12s} {v['step']:5.1f} {v['succ']:.3f} {v['attempts']:6.2f}")
print("\ngesture anticipation sweep (gap_tpl):")
for r in res["gesture_sweep"]:
    print(f"  g={r['g_ant']:.2f}  step={r['step']:5.1f}  succ={r['succ']:.3f}  att={r['attempts']:.2f}")
print("\nTPL vs naive by topology (step score):")
for topo,d in res["topology"].items():
    print(f"  {topo:9s} naive={d['react_naive']:5.1f}  tpl={d['react_tpl']:5.1f}  delta={d['react_tpl']-d['react_naive']:+.1f}")
