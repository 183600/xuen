#!/usr/bin/env python3
"""Round 16 (research line) / inspiration-loop round 1 synthetic experiments: ATLAS-VLA.

Three parts, all declared generative models, fixed seeds, oracle controls:
  A. Leaderboard task-family analysis (real data, A-level source, B-level aggregation).
  B. E1: cross-head consistency (language-grounding head vs action intent) as an
     OOD-G detector -- attacks round 15's declared blind spot by breaking the
     "shared prior" premise with an independently-supervised teacher.
  C. E2: learned contact head (sim physics teacher) + admittance switching for
     insertion, in a no-force-sensor API.

Not real-robot evidence. Outputs: exp/atlas_results.json
"""
import json
import numpy as np

rng = np.random.default_rng(20261104)
OUT = {}

# ---------------------------------------------------------------- Part A ----
LB_PATH = "/home/runner/work/xuen/xuen/workspace/exp/lb_2026_11_04.json"
lb = json.load(open(LB_PATH))
tasks = lb["tasks"]
teams = lb["models"]

FAM_INSERT = ["Disconnect Ethernet", "Plug Charger", "Pick Out Battery",
              "Unlock", "Open Pill Bottle", "Plug In Ethernet"]
FAM_CONTACT = ["Zip Up", "Syringe Water Transfer", "Fold Towel", "Remove Pinned Note"]
idx = {t: i for i, t in enumerate(tasks)}
FAM_REST = [t for t in tasks if t not in FAM_INSERT + FAM_CONTACT]

def fam_mean(row, fam):
    return float(np.mean([row["per_task"][idx[t]] for t in fam]))

fam_rows = []
for m in teams:
    r = {"team": m["model_name"], "avg": m["avg_success_rate"],
         "insert": fam_mean(m, FAM_INSERT),
         "contact": fam_mean(m, FAM_CONTACT),
         "rest": fam_mean(m, FAM_REST)}
    r["contact_gap"] = r["rest"] - r["contact"]
    r["insert_gap"] = r["rest"] - r["insert"]
    fam_rows.append(r)

pooled = {
    "insert_pooled": float(np.mean([r["insert"] for r in fam_rows])),
    "contact_pooled": float(np.mean([r["contact"] for r in fam_rows])),
    "rest_pooled": float(np.mean([r["rest"] for r in fam_rows])),
}
pooled["insert_gap"] = pooled["rest_pooled"] - pooled["insert_pooled"]
pooled["contact_gap"] = pooled["rest_pooled"] - pooled["contact_pooled"]

m0 = teams[0]
worst5 = sorted(zip(tasks, m0["per_task"]), key=lambda x: x[1])[:5]

# per-task best across teams (headroom = 100 - best)
best_per_task = {t: max(m["per_task"][idx[t]] for m in teams) for t in tasks}
fam_best_insert = float(np.mean([best_per_task[t] for t in FAM_INSERT]))
fam_best_contact = float(np.mean([best_per_task[t] for t in FAM_CONTACT]))
fam_best_rest = float(np.mean([best_per_task[t] for t in FAM_REST]))

OUT["partA_leaderboard"] = {
    "source": lb["_source"],
    "retrieved": "2026-11-04",
    "top8": [(m["model_name"], m["avg_success_rate"]) for m in teams],
    "family_rows": fam_rows,
    "pooled": pooled,
    "rank1_worst5": worst5,
    "best_per_task_family_means": {
        "insert": fam_best_insert, "contact": fam_best_contact, "rest": fam_best_rest},
}

# ---------------------------------------------------------------- Part B ----
# Scene: true object at 0; distractor at x_D ~ U(0.7, 1.3).
# Grounding head (independently supervised referential teacher):
#   p_g = x_lang + N(0, s_g) w.p. 1-phi ; p_g = x_D + N(0, s_g) w.p. phi (teacher confusion)
# Action intent: ID: x_T + N(0, s_a); noisy-ID: x_T + N(0, s_an);
#                OOD-ES: x_T + N(0, s_an); OOD-G: x_D + N(0, s_a)
# kappa = |p_g - mu_a|.  tau = 90th pct of kappa on ID calibration.

S_A, S_AN = 0.20, 0.50
S_XD = 0.15
N_EP = 24000
N_CAL = 12000

def gen_episodes(n, s_g, phi, force_type=None):
    types = rng.choice(
        ["ID", "noisyID", "OOD-ES", "OOD-G"],
        p=[0.5525, 0.0975, 0.175, 0.175], size=n) if force_type is None else \
        np.full(n, force_type)
    xD = rng.uniform(0.7, 1.3, n)
    mu_a = np.zeros(n)
    teacher_confused = rng.random(n) < phi
    # grounding-head referent prediction
    lang_ref = np.where(teacher_confused, xD, 0.0)
    p_g = lang_ref + rng.normal(0, s_g, n)
    # action intent
    is_g = types == "OOD-G"
    sa = np.where(types == "noisyID", S_AN, S_A)
    sa = np.where(types == "OOD-ES", S_AN, sa)
    mu_a = np.where(is_g, xD, 0.0) + rng.normal(0, 1, n) * sa
    kappa = np.abs(p_g - mu_a)
    return types, kappa, xD

def auroc(pos, neg):
    s = np.concatenate([pos, neg])
    r = s.argsort().argsort().astype(float) + 1.0
    # average ranks for ties
    order = s.argsort()
    ss = s[order]
    ranks = np.empty_like(r)
    i = 0
    while i < len(ss):
        j = i
        while j + 1 < len(ss) and ss[j + 1] == ss[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j + 2) / 2.0
        i = j + 1
    np_pos, np_neg = len(pos), len(neg)
    return float((ranks[:np_pos].sum() - np_pos * (np_pos + 1) / 2) / (np_pos * np_neg))

ALPHA = 0.10
Q_CORR_BASE = 0.85
B_BUD, P_NEED = 10, 3

e1 = []
for s_g in [0.15, 0.30, 0.45]:
    for phi in [0.10, 0.25]:
        types_c, k_c, _ = gen_episodes(N_CAL, s_g, phi)
        tau = float(np.quantile(k_c, 1 - ALPHA))
        types, k, xD = gen_episodes(N_EP, s_g, phi)
        mask_g = types == "OOD-G"
        auc = auroc(k[mask_g], k[~mask_g])
        id_far = float(np.mean(k[~mask_g] > tau))
        tpr = float(np.mean(k[mask_g] > tau))
        # downstream policy sim on ID/noisyID/OOD-G only
        sel = (types != "OOD-ES")
        t2, k2, xD2 = types[sel], k[sel], xD[sel]
        n2 = len(t2)
        succ = {"P0": [], "P1": [], "P2": []}
        cost = {"P0": [], "P1": [], "P2": []}
        for pol in succ:
            prog = np.zeros(n2)
            budget = np.full(n2, B_BUD, float)
            corrected = np.zeros(n2, bool)
            if pol in ("P1", "P2"):
                flagged = k2 > tau if pol == "P1" else (t2 == "OOD-G")
                q_corr = np.where(t2 == "OOD-G", (1 - phi) * Q_CORR_BASE, 1.0)
                budget -= 2.0 * flagged
                corrected = flagged & (rng.random(n2) < q_corr)
            alive = np.ones(n2, bool)
            for step in range(int(B_BUD)):
                act = alive & (budget >= 1.0)
                if not act.any():
                    break
                c = np.where(t2 == "OOD-G", 0.4, 0.9)
                c = np.where(corrected, 0.9, c)
                p_inc = (rng.random(n2) < 0.9 * c) & act
                prog += p_inc
                budget -= act * 1.0
                alive = act & (prog < P_NEED)
                if not alive.any():
                    break
            ok = (prog >= P_NEED) & ~((t2 == "OOD-G") & ~corrected)
            succ[pol] = float(np.mean(ok))
            cost[pol] = float(np.mean(B_BUD - np.maximum(budget, 0)))
        e1.append({"s_g": s_g, "phi": phi, "tau": round(tau, 3),
                   "auroc_OODG": round(auc, 3), "id_false_alarm": round(id_far, 3),
                   "oodg_detect_at_tau": round(tpr, 3),
                   "succ_P0": round(succ["P0"], 3), "succ_P1": round(succ["P1"], 3),
                   "succ_P2": round(succ["P2"], 3),
                   "gain_P1_vs_P0_pp": round(100 * (succ["P1"] - succ["P0"]), 2)})
OUT["partB_E1_crosshead"] = e1

# ---------------------------------------------------------------- Part C ----
# Insertion toy: lateral error delta ~ U(-1,1); tol=0.15; budget 10.
# Blind: approach steps 1-2, then contact. Each contact-advance step:
#   fail (wedge) w.p. min(1, 0.5|delta|); else chamfer halves delta w.p. 0.35.
#   advancing with |delta|<tol: success w.p. 0.9 (else keep trying).
# Contact-head policy: detection prob q per contact step (fp 0.08/approach step);
#   on detection: SPIRAL up to 4 steps, delta *= 0.4 w.p. 0.9 each; then advance.
TOL, B2, FP = 0.15, 10, 0.08
N2 = 12000

def run_insert(q):
    res = {"succ": 0, "damage": 0, "timeout": 0}
    for _ in range(N2):
        delta = rng.uniform(-1, 1)
        step = 0
        contact = False
        spiral_left = 0
        while step < B2:
            step += 1
            if not contact:
                # approach; blind policy reaches contact at step 3
                if q is None:
                    if step >= 3:
                        contact = True
                else:
                    if rng.random() < FP:
                        spiral_left = 4  # false-positive spiral (harmless, wasted)
                    if step >= 3:
                        contact = True
                        if rng.random() < q:
                            spiral_left = 4
                if spiral_left > 0:
                    spiral_left -= 1
                    if rng.random() < 0.9:
                        delta *= 0.4
                    continue
                continue
            # in contact
            if q is not None and spiral_left == 0 and rng.random() < q:
                spiral_left = 4
                continue
            if spiral_left > 0:
                spiral_left -= 1
                if rng.random() < 0.9:
                    delta *= 0.4
                continue
            if abs(delta) < TOL:
                if rng.random() < 0.9:
                    res["succ"] += 1
                    break
            else:
                if rng.random() < min(1.0, 0.5 * abs(delta)):
                    res["damage"] += 1
                    break
                if rng.random() < 0.35:
                    delta *= 0.5
        else:
            res["timeout"] += 1
    res = {k: round(v / N2, 3) for k, v in res.items()}
    return res

e2 = [{"policy": "blind_P0", **run_insert(None)}]
for q in [0.6, 0.7, 0.8, 0.9, 1.0]:
    e2.append({"policy": f"head_q{q}", **run_insert(q)})
OUT["partC_E2_contact_admittance"] = e2

json.dump(OUT, open("/home/runner/work/xuen/xuen/workspace/exp/atlas_results.json", "w"),
          indent=1, ensure_ascii=False)

# ------- print digest -------
print("== A: family gap (pooled) ==")
print(json.dumps(pooled, indent=1))
print("best-per-task family means:", OUT["partA_leaderboard"]["best_per_task_family_means"])
print("rank1 worst5:", worst5)
print("== B: cross-head consistency ==")
for r in e1:
    print(r)
print("== C: contact head + admittance ==")
for r in e2:
    print(r)
