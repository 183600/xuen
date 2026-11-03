#!/usr/bin/env python3
"""Round-A synthesis experiment: LADDER roadmap vs uniform multi-task BC.

Stylised, declared-generative model of why *skill factorisation* + a
*locomotion-style sim-to-real coverage* + *few-shot adaptation* change the
UniBot success curve under a fixed real-demo budget.

This is a mechanism check (B-level), not benchmark evidence.  Everything is
declared below; nothing is fit to the leaderboard except the per-skill
difficulty ordering, which is taken from roadmap_lb_analysis.py.
"""
import json, math, os, random

HERE = os.path.dirname(os.path.abspath(__file__))
rng = random.Random(20261102)

N_DEMO = 1000  # per task, matches the released datasets (~970-1530)

# ---- tasks and skill compositions (same rubric as roadmap_lb_analysis) ----
TASKS = {
 "Hang the Cup":            {"reach_grasp":3, "place_stack":2, "bimanual_carry":1},
 "Fruit Basket Collection": {"reach_grasp":3, "place_stack":2, "sort_select":1},
 "Pack the Doll":           {"reach_grasp":2, "place_stack":2, "deform":1},
 "Fruit Sorting":           {"reach_grasp":3, "sort_select":3, "place_stack":1},
 "Disconnect Ethernet":     {"reach_grasp":3, "insert_align":2, "articulate":1},
 "Color Arrangement":       {"reach_grasp":3, "sort_select":2, "place_stack":2},
 "Place Photo Frames":      {"reach_grasp":3, "place_stack":2},
 "Organize Bookshelf":      {"reach_grasp":3, "place_stack":2, "sort_select":1},
 "Toolbox Storage":         {"reach_grasp":3, "place_stack":2, "sort_select":1},
 "Plug Charger":            {"reach_grasp":2, "insert_align":3, "press_toggle":1},
 "Pick Out Battery":        {"reach_grasp":2, "insert_align":1, "sort_select":2},
 "Unlock":                  {"reach_grasp":2, "articulate":3, "press_toggle":1},
 "Arrange Test Tubes":      {"reach_grasp":3, "insert_align":2, "place_stack":2},
 "Open Pill Bottle":        {"reach_grasp":2, "articulate":2, "press_toggle":2},
 "Organize Tools":          {"reach_grasp":3, "place_stack":2, "sort_select":1},
 "Fold Towel":              {"deform":3, "bimanual_carry":2, "reach_grasp":1},
 "Organize Stationery":     {"reach_grasp":3, "sort_select":2, "place_stack":2},
 "Pack Bag":                {"reach_grasp":2, "place_stack":2, "bimanual_carry":2, "deform":1},
 "Zip Up":                  {"deform":3, "bimanual_carry":2, "press_toggle":1},
 "Paper Cup Stacking":      {"reach_grasp":3, "place_stack":3},
 "Clear Plates":            {"reach_grasp":3, "place_stack":2, "bimanual_carry":1},
 "Spell robot":             {"reach_grasp":3, "place_stack":2, "sort_select":2},
 "Store Racket":            {"reach_grasp":2, "place_stack":2, "insert_align":1},
 "Conveyor Food Sorting":   {"reach_grasp":3, "sort_select":3, "bimanual_carry":1},
 "Stack Cups":              {"reach_grasp":3, "place_stack":3},
 "Plug In Ethernet":        {"reach_grasp":2, "insert_align":3, "press_toggle":1},
 "Stack Bowls":             {"reach_grasp":3, "place_stack":3},
 "Store Earphones":         {"reach_grasp":2, "place_stack":2, "deform":1},
 "Pack Phone":              {"reach_grasp":2, "place_stack":2, "insert_align":1},
 "Remove Pinned Note":      {"reach_grasp":2, "articulate":2, "press_toggle":1},
 "Organize Pencil Case":    {"reach_grasp":3, "place_stack":2, "insert_align":1},
 "Syringe Water Transfer":  {"reach_grasp":2, "fluid":3, "bimanual_carry":1},
}
# per-skill data scale tau (demos for ~63% competence) and difficulty.
# ordering follows the leaderboard: precision/articulated/press/deform are hard.
TAU = {
 "reach_grasp": 400, "place_stack": 500, "sort_select": 650, "bimanual_carry": 900,
 "insert_align": 2600, "articulate": 2800, "press_toggle": 2200, "deform": 3200,
 "fluid": 1500,
}
# eval novelty demand per task (unseen object/appearance/position/disturbance),
# a declared per-task scalar; harder/contact tasks are more novelty sensitive.
# calibrated so that a uniform multi-task BC baseline lands near the published
# top-8 leaderboard band (~18-30%).
NOVELTY = {t: 0.60 + 0.05 * (len(TASKS[t]) - 2) +
               (0.18 if any(s in TASKS[t] for s in ("insert_align", "articulate", "deform")) else 0.0)
           for t in TASKS}
GAP = 0.90  # demo/sim -> real execution gap that no training lever removes

def competence(eff_data, tau, cap=0.95):
    return cap * (1.0 - math.exp(-eff_data / tau))

def effective_data(factorized, curriculum, interference=0.55):
    E = {s: 0.0 for s in TAU}
    n_tasks = {s: 0 for s in TAU}
    for t, row in TASKS.items():
        for s, w in row.items():
            E[s] += N_DEMO * w
            n_tasks[s] += 1
    if not factorized:
        # task-conditioned trunk fragments per-skill data
        for s in E:
            E[s] /= (1.0 + interference * (n_tasks[s] - 1))
    if curriculum:
        # sequence by frequency: high-frequency skills saturate first -> small boost
        freq = {s: n_tasks[s] for s in E}
        fmax = max(freq.values())
        for s in E:
            E[s] *= (1.0 + 0.10 * freq[s] / fmax)
    return E

def train_success(E):
    out = {}
    for t, row in TASKS.items():
        W = sum(row.values())
        # weighted geometric mean -> soft weakest-link
        logp = sum((w / W) * math.log(max(1e-6, competence(E[s], TAU[s]))) for s, w in row.items())
        out[t] = GAP * math.exp(logp)
    return out

def eval_success(train, C_sim=0.0, K_shot=0, adapt_gain=0.22, adapt_K0=6.0,
                 residual_floor=0.10):
    """C_sim in [0,1]: sim-to-real coverage of appearance/object/position novelty.
    K_shot: support demos per task at test time."""
    adapt = adapt_gain * (1.0 - math.exp(-K_shot / adapt_K0))
    out = {}
    for t, p in train.items():
        residual = NOVELTY[t] * (1.0 - C_sim) * (1.0 - adapt)
        residual = max(residual_floor * NOVELTY[t], residual)
        out[t] = p * (1.0 - residual)
    return out

def summarize(succ):
    vals = list(succ.values())
    return sum(vals) / len(vals), min(vals)

def run():
    grid = []
    # real training strategies
    strategies = [
        ("uniform BC",            dict(factorized=False, curriculum=False), 0.0, 0, 1.0),
        ("factorized",            dict(factorized=True,  curriculum=False), 0.0, 0, 1.0),
        ("factorized+curriculum", dict(factorized=True,  curriculum=True),  0.0, 0, 1.0),
        ("+few-shot(K=5)",        dict(factorized=True,  curriculum=True),  0.0, 5, 1.0),
        ("+few-shot(K=20)",       dict(factorized=True,  curriculum=True),  0.0, 20, 1.0),
        ("+sim-to-real(C=.5)",    dict(factorized=True,  curriculum=True),  0.5, 5, 1.0),
        ("+sim-to-real(C=1.0)",   dict(factorized=True,  curriculum=True),  1.0, 5, 1.0),
    ]
    print(f"{'strategy':24s} {'mean':>6s} {'worst':>6s} {'cost':>6s}")
    for name, kw, C, K, cost in strategies:
        E = effective_data(**kw)
        tr = train_success(E)
        ev = eval_success(tr, C_sim=C, K_shot=K)
        mean, worst = summarize(ev)
        c = cost + 0.0005 * K * 32 / 32  # few-shot support cost negligible
        row = dict(name=name, mean=mean, worst=worst, cost=c)
        grid.append(row)
        print(f"{name:24s} {mean*100:6.1f} {worst*100:6.1f} {c:6.2f}")

    # ---- sensitivity: does skill-sharing help when eval is novelty-dominated? ----
    print("\n== sensitivity: mean eval success (rows=factorized, cols=sim coverage) ==")
    for fact in (False, True):
        line = []
        for C in (0.0, 0.25, 0.5, 1.0):
            E = effective_data(factorized=fact, curriculum=True)
            ev = eval_success(train_success(E), C_sim=C, K_shot=0)
            line.append(summarize(ev)[0] * 100)
        print(f"factorized={str(fact):5s} " + "  ".join(f"C={C}:{v:5.1f}" for C, v in zip((0,.25,.5,1.0), line)))

    # ---- per-skill competence: where does factorisation pay? ----
    print("\n== per-skill competence: uniform vs factorized ==")
    Eu = effective_data(factorized=False, curriculum=False)
    Ef = effective_data(factorized=True, curriculum=True)
    rows = sorted(TAU, key=lambda s: TAU[s], reverse=True)
    for s in rows:
        print(f"{s:15s} tau={TAU[s]:5d}  uniform={competence(Eu[s],TAU[s])*100:5.1f}  "
              f"factorized={competence(Ef[s],TAU[s])*100:5.1f}")

    # ---- worst-task improvement detail ----
    Eu = effective_data(factorized=False, curriculum=False)
    Ef = effective_data(factorized=True, curriculum=True)
    ev_u = eval_success(train_success(Eu), C_sim=0.5, K_shot=5)
    ev_f = eval_success(train_success(Ef), C_sim=0.5, K_shot=5)
    print("\n== per-task eval success: uniform -> factorized+few-shot+sim(.5) ==")
    for t in sorted(TASKS, key=lambda t: ev_u[t]):
        print(f"{t:24s} {ev_u[t]*100:5.1f} -> {ev_f[t]*100:5.1f}  (+{(ev_f[t]-ev_u[t])*100:4.1f})")

    json.dump(dict(grid=grid), open(os.path.join(HERE, "roadmap_results.json"), "w"), indent=1)
    print("\nwrote roadmap_results.json")

if __name__ == "__main__":
    run()
