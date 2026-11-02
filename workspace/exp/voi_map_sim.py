"""Synthetic mechanism check for VOI-MAP budget/grounding logic.

NOT benchmark evidence. Isolates one question:
under instruction noise + candidate ambiguity + a hard per-episode
compute budget, does a value-of-information scheduler beat fixed
schedules (always-servo, look-first, confidence-gated look, always-VLA)?

Generative model (declared, not fit):
  - Episodes are a 50/50 mixture: 'simple' (k=1, no ambiguity) and
    'ambiguous' (k in {2,3,4}, ASR error e).
  - ASR: with prob e corrupt the label; half true homophone (phonetic
    cannot fix), half near-miss (edit distance can fix).
  - Actions: SERVO cost 1, +1 execution progress; LOOK cost 2, resolves
    goal w.p. 0.8, at most 2; VLA cost 5, resolves w.p. 0.95, at most 1.
  - success = committed goal correct AND Bernoulli(1-exp(-progress/2.5)).
"""
import os, random, math, json, statistics

LABELS = ["cup", "bowl", "block", "pen", "cap", "ball", "black", "pan", "mug", "plate"]
HOMO = {"cup": "cap", "cap": "cup", "bowl": "ball", "ball": "bowl",
        "block": "black", "black": "block", "pen": "pan", "pan": "pen"}
NEAR = {"cup": ["cub", "cupp", "cop"], "bowl": ["bowel", "bawl", "boll"],
        "block": ["blok", "blokc", "bloc"], "pen": ["penn", "phen", "pen"],
        "cap": ["capp", "kap", "cab"], "ball": ["bal", "bawl", "boll"],
        "black": ["blak", "blacc", "bleck"], "pan": ["pann", "pam", "pna"],
        "mug": ["mugg", "muh", "mag"], "plate": ["plait", "plte", "plat"]}
COST = {"servo": 1.0, "look": 2.0, "vla": 5.0}

def lev(a, b):
    if a == b: return 0
    dp = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, dp[0] = dp[0], i
        for j, cb in enumerate(b, 1):
            cur = dp[j]
            dp[j] = min(dp[j] + 1, dp[j-1] + 1, prev + (ca != cb))
            prev = cur
    return dp[-1]

def asr(label, e, rng):
    if rng.random() >= e: return label
    if label in HOMO and rng.random() < 0.5: return HOMO[label]
    return rng.choice(NEAR.get(label, [label + "x"]))

def belief_from_obs(obs, cands, method):
    if method == "exact":
        exact = [i for i, c in enumerate(cands) if c == obs]
        if exact:
            w = [0.05] * len(cands)
            for i in exact: w[i] = 10.0
        else:
            w = [1.0] * len(cands)
    else:
        w = [math.exp(-lev(obs, c) / 0.7) + 0.05 for c in cands]
    s = sum(w); return [wi / s for wi in w]

def pexec(p): return 1.0 - math.exp(-p / 2.5)
def onehot(i, n):
    b = [0.0] * n; b[i] = 1.0; return b

def run_episode(cands, true, belief, policy, rng, B):
    n = len(cands); belief = list(belief); c = max(belief)
    progress = spent = looks = vlas = 0.0
    q_look, q_vla = 0.8, 0.95
    if policy == "oracle": belief, c = onehot(true, n), 1.0
    while spent < B - 1e-9:
        if progress >= 8 and c >= 0.95: break
        if policy == "servo":
            progress += 1; spent += 1; continue
        if policy == "look_first":
            if looks < 1 and spent + COST["look"] <= B:
                looks += 1; spent += COST["look"]
                if rng.random() < q_look: belief, c = onehot(true, n), 1.0
                continue
            progress += 1; spent += 1; continue
        if policy == "look_gate":
            if looks < 1 and c < 0.90 and spent + COST["look"] <= B:
                looks += 1; spent += COST["look"]
                if rng.random() < q_look: belief, c = onehot(true, n), 1.0
                continue
            progress += 1; spent += 1; continue
        if policy == "always_vla":
            if vlas < 1 and spent + COST["vla"] <= B:
                vlas += 1; spent += COST["vla"]
                if rng.random() < q_vla: belief, c = onehot(true, n), 1.0
                continue
            progress += 1; spent += 1; continue
        # VOI-MAP: myopic marginal expected success per unit cost
        opts = [("servo", c * (pexec(progress + 1) - pexec(progress)), COST["servo"])]
        if looks < 2 and spent + COST["look"] <= B:
            c_after = q_look + (1 - q_look) * c
            opts.append(("look", (c_after - c) * pexec(progress), COST["look"]))
        if vlas < 1 and spent + COST["vla"] <= B:
            c_after = q_vla + (1 - q_vla) * c
            opts.append(("vla", (c_after - c) * pexec(progress), COST["vla"]))
        act = max(opts, key=lambda o: o[1] / o[2])
        if act[1] <= 1e-9: break
        if act[0] == "servo":
            progress += 1; spent += 1
        elif act[0] == "look":
            looks += 1; spent += COST["look"]
            if rng.random() < q_look: belief, c = onehot(true, n), 1.0
        else:
            vlas += 1; spent += COST["vla"]
            if rng.random() < q_vla: belief, c = onehot(true, n), 1.0
    correct = (max(range(n), key=lambda i: belief[i]) == true)
    return (1 if (correct and rng.random() < pexec(progress)) else 0), spent, progress

def experiment(seed=11, trials=5000):
    rng = random.Random(seed); rows = []
    names = ["oracle", "servo", "look_first", "look_gate", "always_vla", "voi"]
    for B in (5.0, 8.0, 11.0, 14.0):
        for e in (0.10, 0.25, 0.40):
            for k in (2, 4):
                res = {p: [] for p in names}; cost = {p: [] for p in names}
                g_acc = {"exact": [], "phonetic": []}
                for _ in range(trials):
                    simple = rng.random() < 0.5
                    kk = 1 if simple else k
                    cands = rng.sample(LABELS, kk)
                    true = rng.randrange(kk)
                    obs = asr(cands[true], 0.0 if simple else e, rng)
                    for method in ("exact", "phonetic"):
                        b = belief_from_obs(obs, cands, method)
                        g_acc[method].append(1 if max(range(kk), key=lambda i: b[i]) == true else 0)
                    b = belief_from_obs(obs, cands, "phonetic")
                    for p in names:
                        r, sp, pr = run_episode(cands, true, b, p, rng, B)
                        res[p].append(r); cost[p].append(sp)
                row = {"budget": B, "asr_error": e, "k_ambig": k,
                       "map_acc_exact": round(statistics.mean(g_acc["exact"]), 3),
                       "map_acc_phonetic": round(statistics.mean(g_acc["phonetic"]), 3)}
                for p in names:
                    row[p] = {"succ": round(statistics.mean(res[p]), 3),
                              "cost": round(statistics.mean(cost[p]), 2),
                              "succ_per_cost": round(statistics.mean(res[p]) /
                                                     max(statistics.mean(cost[p]), 1e-9), 3)}
                rows.append(row)
    return rows

if __name__ == "__main__":
    rows = experiment()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voi_map_results.json")
    json.dump(rows, open(out, "w"), indent=2)
    print(f"{'B':>4} {'e':>5} {'k':>2} | {'exact':>5} {'phon':>5} | " +
          " | ".join(f"{p:>15}" for p in ["servo","look_first","look_gate","always_vla","voi"]))
    for r in rows:
        print(f"{r['budget']:>4} {r['asr_error']:>5} {r['k_ambig']:>2} | {r['map_acc_exact']:>5} {r['map_acc_phonetic']:>5} | " +
              " | ".join(f"{r[p]['succ']:.3f}/{r[p]['cost']:.1f}/{r[p]['succ_per_cost']:.3f}" for p in ["servo","look_first","look_gate","always_vla","voi"]))
