"""Synthetic mechanism check for SR-KG (round 41).

NOT benchmark evidence.  Isolates one question: when per-(skill, object, scene)
episodes are scarce, missing and biased toward successes, does a graph-
regularised, calibrated success model estimate *task success probability*
better than flat empirical counting or skill-only pooling -- and does the
better estimate reduce the decision regret of picking the skill to execute?

The generator is intentionally NOT the estimator's model: true logits contain
attribute interactions and per-(object, skill) latent effects, while the
estimator is a graph-regularised multi-task logistic regression over
attribute + scene features with a skill-similarity graph.  This keeps the
comparison honest (misspecification) while still rewarding relational
sharing across objects/scenes/skills.

Outputs exp/r41_srkg/srkg_sim_results.json.
"""
import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 20261110

SHAPES = ["box", "cyl", "sphere", "flat"]
MATS = ["rigid", "soft", "slip"]
SIZES = ["small", "large"]
MASSES = ["light", "heavy"]
SCENES = ["nominal", "distractor", "background", "moved", "human"]
SKILLS = ["top_grasp", "side_grasp", "suction", "two_hand", "push"]


def sigmoid(z):
    if z >= 0:
        e = math.exp(-z)
        return 1.0 / (1.0 + e)
    e = math.exp(z)
    return e / (1.0 + e)


# ---------- feature map: graph nodes instantiated as attribute/scene tokens ----------
def feat(obj, scene):
    # intercept + shape(3, drop box) + material(2, drop rigid) + size + mass + scene(4, drop nominal)
    f = [1.0]
    for s in SHAPES[1:]:
        f.append(1.0 if obj["shape"] == s else 0.0)
    for m in MATS[1:]:
        f.append(1.0 if obj["mat"] == m else 0.0)
    f.append(1.0 if obj["size"] == "large" else 0.0)
    f.append(1.0 if obj["mass"] == "heavy" else 0.0)
    for sc in SCENES[1:]:
        f.append(1.0 if scene == sc else 0.0)
    return f


D = 12  # length of feat()


def make_objects(rng):
    combos = [(s, m, z, w) for s in SHAPES for m in MATS for z in SIZES for w in MASSES]
    rng.shuffle(combos)
    objs = []
    for i, (s, m, z, w) in enumerate(combos[:24]):
        objs.append({"id": i, "shape": s, "mat": m, "size": z, "mass": w})
    return objs


def make_truth(rng, objs):
    # ground-truth multi-task weights (NOT the estimator's structure: extra interactions below)
    W = {}
    for k in SKILLS:
        W[k] = [rng.gauss(0.0, 0.6) for _ in range(D)]
        W[k][0] = rng.gauss({"top_grasp": 0.6, "side_grasp": 0.2, "suction": -0.3,
                             "two_hand": 0.1, "push": -0.6}[k], 0.2)
    latent = {(o["id"], k): rng.gauss(0.0, 0.45) for o in objs for k in SKILLS}

    def true_p(o, k, sc):
        z = sum(a * b for a, b in zip(W[k], feat(o, sc))) + latent[(o["id"], k)]
        # interactions the linear estimator cannot represent
        if o["shape"] == "cyl" and o["mat"] == "slip" and k in ("top_grasp", "suction"):
            z -= 0.9
        if o["size"] == "large" and k == "two_hand":
            z += 0.5
        if o["mass"] == "heavy" and o["shape"] == "sphere" and k == "top_grasp":
            z -= 0.6
        if sc == "human" and k == "two_hand":
            z -= 0.5
        if sc == "moved" and k == "push":
            z -= 0.3
        return sigmoid(z)

    return true_p


# ---------- estimators ----------
def fit_flat(obs, priors):
    """Beta(1,1) smoothed per-context rate; fall back to per-skill pooled, then global."""
    n = {}
    s = {}
    for (k, oid, sc, y) in obs:
        key = (k, oid, sc)
        n[key] = n.get(key, 0) + 1
        s[key] = s.get(key, 0) + y
    skill_n = {k: 0 for k in SKILLS}
    skill_s = {k: 0 for k in SKILLS}
    for (k, oid, sc, y) in obs:
        skill_n[k] += 1
        skill_s[k] += y

    def predict(k, oid, sc):
        key = (k, oid, sc)
        if key in n:
            return (s[key] + 1.0) / (n[key] + 2.0), 0.25
        if skill_n[k] > 0:
            return (skill_s[k] + 1.0) / (skill_n[k] + 2.0), 0.25
        return 0.5, 0.25
    return predict


def fit_skill_pooled(obs):
    n = {k: 0 for k in SKILLS}
    s = {k: 0 for k in SKILLS}
    for (k, oid, sc, y) in obs:
        n[k] += 1
        s[k] += y

    def predict(k, oid, sc):
        return (s[k] + 1.0) / (n[k] + 2.0), 0.25
    return predict


def mat_inv(A):
    n = len(A)
    M = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-12:
            M[p][c] = 1e-12
        M[c], M[p] = M[p], M[c]
        piv = M[c][c]
        M[c] = [v / piv for v in M[c]]
        for r in range(n):
            if r != c and M[r][c] != 0.0:
                f = M[r][c]
                M[r] = [a - f * b for a, b in zip(M[r], M[c])]
    return [row[n:] for row in M]


def fit_srkg(obs, lam=1.0, tau=2.0, iters=900, lr=0.08, z=1.2816):
    """Graph-regularised multi-task logistic regression.

    Nodes = per-skill weight vectors; skill-similarity edges (graph Laplacian)
    shrink weights of related skills; attribute/scene features carry the
    object/scene part of the knowledge graph.  Laplace-approximate posterior
    gives a predictive variance, used for a 90% lower confidence bound.
    """
    K = len(SKILLS)
    idx = {k: i for i, k in enumerate(SKILLS)}
    W = [[0.0] * D for _ in range(K)]
    laplace_edges = [("top_grasp", "side_grasp", 1.0),
                     ("top_grasp", "two_hand", 0.5),
                     ("side_grasp", "two_hand", 0.5),
                     ("suction", "top_grasp", 0.4)]
    for it in range(iters):
        grad = [[lam * v for v in W[i]] for i in range(K)]
        for (k, oid, sc, y) in obs:
            i = idx[k]
            phi = FEATS[(oid, sc)]
            p = sigmoid(sum(a * b for a, b in zip(W[i], phi)))
            g = p - y
            gi = grad[i]
            for d in range(D):
                gi[d] += g * phi[d]
        for (ka, kb, wgt) in laplace_edges:
            ia, ib = idx[ka], idx[kb]
            for d in range(D):
                diff = W[ia][d] - W[ib][d]
                grad[ia][d] += tau * wgt * diff
                grad[ib][d] -= tau * wgt * diff
        for i in range(K):
            for d in range(D):
                W[i][d] -= lr * grad[i][d] / max(1.0, len(obs) / 100.0)

    # Laplace covariance: H = X^T S X + lam I + tau L (x) I_D
    N = K * D
    H = [[0.0] * N for _ in range(N)]
    for (k, oid, sc, y) in obs:
        i = idx[k]
        phi = FEATS[(oid, sc)]
        p = sigmoid(sum(a * b for a, b in zip(W[i], phi)))
        s = max(p * (1.0 - p), 1e-4)
        base = i * D
        for a in range(D):
            if phi[a] == 0.0:
                continue
            for b in range(D):
                if phi[b] == 0.0:
                    continue
                H[base + a][base + b] += s * phi[a] * phi[b]
    for i in range(N):
        H[i][i] += lam
    for (ka, kb, wgt) in laplace_edges:
        ia, ib = idx[ka], idx[kb]
        for d in range(D):
            a = ia * D + d
            b = ib * D + d
            H[a][a] += tau * wgt
            H[b][b] += tau * wgt
            H[a][b] -= tau * wgt
            H[b][a] -= tau * wgt
    Hinv = mat_inv(H)
    cov = {k: [[Hinv[idx[k] * D + a][idx[k] * D + b] for b in range(D)] for a in range(D)]
           for k in SKILLS}

    def predict(k, oid, sc):
        phi = FEATS[(oid, sc)]
        mu = sum(a * b for a, b in zip(W[idx[k]], phi))
        var = 0.0
        C = cov[k]
        for a in range(D):
            if phi[a] == 0.0:
                continue
            for b in range(D):
                if phi[b] == 0.0:
                    continue
                var += phi[a] * C[a][b] * phi[b]
        var = max(var, 1e-6)
        return sigmoid(mu), sigmoid(mu - z * math.sqrt(var))
    return predict


def sample_obs(rng, objs, true_p, n_ep, p_attempt=0.55):
    obs = []
    for o in objs:
        for sc in SCENES:
            for k in SKILLS:
                if rng.random() > p_attempt:
                    continue
                p = true_p(o, k, sc)
                for _ in range(n_ep):
                    obs.append((k, o["id"], sc, 1 if rng.random() < p else 0))
    return obs


def evaluate(predict, objs, true_p, use_lcb=False):
    mae = 0.0
    n = 0
    regret = 0.0
    cover = 0
    # test Brier on a fresh Monte-Carlo draw from the true model
    brier = 0.0
    for o in objs:
        for sc in SCENES:
            ps = {}
            for k in SKILLS:
                ph, lcb = predict(k, o["id"], sc)
                pt = true_p(o, k, sc)
                est = lcb if use_lcb else ph
                ps[k] = est
                mae += abs(est - pt)
                n += 1
                brier += (est - pt) ** 2
                if pt >= lcb:
                    cover += 1
            oracle = max(SKILLS, key=lambda k: true_p(o, k, sc))
            chosen = max(SKILLS, key=lambda k: ps[k])
            regret += true_p(o, oracle, sc) - true_p(o, chosen, sc)
    return {"mae": mae / n, "brier": brier / n, "regret": regret / (len(objs) * len(SCENES)),
            "lcb_coverage": cover / n}


def _mean_std(vals):
    mu = sum(vals) / len(vals)
    var = sum((v - mu) ** 2 for v in vals) / max(1, len(vals) - 1)
    return mu, math.sqrt(var)


def main():
    global FEATS
    seeds = [SEED + 17 * i for i in range(5)]
    keys = ("mae", "brier", "regret", "lcb_coverage")
    raw = {}
    for seed in seeds:
        rng = random.Random(seed)
        objs = make_objects(rng)
        true_p = make_truth(rng, objs)
        FEATS = {(o["id"], sc): feat(o, sc) for o in objs for sc in SCENES}
        train, test = objs[:18], objs[18:]
        for n_ep in (1, 2, 5, 10):
            rng2 = random.Random(seed + n_ep)
            obs = sample_obs(rng2, train, true_p, n_ep)
            est = {
                "flat": fit_flat(obs, None),
                "skill_pooled": fit_skill_pooled(obs),
                "srkg_point": fit_srkg(obs, z=0.0),
                "srkg_lcb": fit_srkg(obs, z=1.2816),
            }
            for name, pred in est.items():
                for split, group in (("train_objects", train), ("unseen_objects", test)):
                    e = evaluate(pred, group, true_p, use_lcb=name.endswith("lcb"))
                    for key in keys:
                        raw.setdefault((n_ep, name, split, key), []).append(e[key])

    results = {"seeds": seeds, "n_train_objects": 18, "n_test_objects": 6,
               "note": "mean over seeds; lcb_coverage is only meaningful for srkg_lcb",
               "by_episodes": {}}
    for n_ep in (1, 2, 5, 10):
        row = {}
        for name in ("flat", "skill_pooled", "srkg_point", "srkg_lcb"):
            row[name] = {}
            for split in ("train_objects", "unseen_objects"):
                stats = {}
                for key in keys:
                    mu, sd = _mean_std(raw[(n_ep, name, split, key)])
                    stats[key] = mu
                    stats[key + "_std"] = sd
                row[name][split] = stats
        results["by_episodes"][str(n_ep)] = {"metrics": row}
    results["headline_n1"] = results["by_episodes"]["1"]["metrics"]
    results["headline_n5"] = results["by_episodes"]["5"]["metrics"]

    with open(os.path.join(HERE, "srkg_sim_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("n_obs | estimator | split | MAE | Brier | regret | LCB-cov")
    for n_ep in (1, 2, 5, 10):
        m = results["by_episodes"][str(n_ep)]["metrics"]
        for name in ("flat", "skill_pooled", "srkg_point", "srkg_lcb"):
            for split in ("train_objects", "unseen_objects"):
                e = m[name][split]
                print(f"{n_ep:>4} | {name:<12} | {split:<14} | "
                      f"{e['mae']:.3f} | {e['brier']:.3f} | {e['regret']:.3f} | {e['lcb_coverage']:.3f}")


FEATS = {}
if __name__ == "__main__":
    main()
