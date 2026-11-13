#!/usr/bin/env python3
"""Round-3 sanity simulation (stdlib only).

Two questions:
  Q1  Does *paired scenario sampling* + *stratified task allocation* recover the
      true policy ranking with fewer episodes than independent uniform sampling?
      (rank fidelity, not score-MSE)
  Q2  With only N test robots / ports, does lower per-episode variance raise the
      probability of winning a pairwise comparison at equal (or slightly lower) mean?

This is a stylised decision-theoretic sanity check. It is NOT robot evidence.
"""
import json, math, random, statistics

TASKS = ([[50, 50]] * 11 + [[30, 30, 40]] * 14 +
         [[25, 25, 25, 25]] * 5 + [[20] * 5] * 2)
assert len(TASKS) == 32
T = len(TASKS)
CATS = 8
K = 8


def sigmoid(z):
    if z < -30: return 1e-13
    if z > 30: return 1 - 1e-13
    return 1.0 / (1.0 + math.exp(-z))


def cat(t, s):
    return (3 * t + 5 * s + t % 7) % CATS


def build_world(seed=7):
    rng = random.Random(seed)
    diff = [[rng.gauss(0.0, 0.5) for _ in TASKS[t]] for t in range(T)]
    policies = []
    for p in range(K):
        g = rng.gauss(0.9, 0.55)
        sk = [rng.gauss(0.0, 0.95) for _ in range(CATS)]
        commit = rng.uniform(0.40, 0.80)       # 1 -> progress cannot be reverted
        policies.append((g, sk, commit))
    q = [[[0.0] * len(TASKS[t]) for t in range(T)] for _ in range(K)]
    for p, (g, sk, commit) in enumerate(policies):
        for t in range(T):
            for s in range(len(TASKS[t])):
                z = g + sk[cat(t, s)] - diff[t][s]
                q[p][t][s] = min(0.985, max(0.015, sigmoid(z) * (1 - 0.30 * (1 - commit))))
    return q


def ground_truth(q):
    step, succ, comp = [0.0] * K, [0.0] * K, [0.0] * K
    for p in range(K):
        st = sum(sum(w * q[p][t][s] for s, w in enumerate(TASKS[t])) for t in range(T)) / T
        sc = sum(math.prod(q[p][t]) for t in range(T)) / T
        step[p], succ[p] = st, sc
        comp[p] = 0.5 * (st / 100.0) + 0.5 * sc
    return step, succ, comp


def episode(t, p, q, shared_D=None, rng=None):
    n = len(TASKS[t])
    D = shared_D if shared_D is not None else [rng.random() for _ in range(n)]
    ok, step = True, 0
    for s in range(n):
        c = D[s] < q[p][t][s]
        if c:
            step += TASKS[t][s]
        else:
            ok = False
    return 0.5 * (step / 100.0) + 0.5 * (1.0 if ok else 0.0)


def task_var(q):
    """Neyman proxy: average across policies of Var(step contribution) per task."""
    out = []
    for t in range(T):
        vals = []
        for p in range(K):
            v = sum((w ** 2) * q[p][t][s] * (1 - q[p][t][s])
                    for s, w in enumerate(TASKS[t])) / (100.0 ** 2)
            vals.append(v)
        out.append(max(1e-9, sum(vals) / K))
    return out


def alloc(B, tv, stratified):
    if not stratified:
        base = [B // T] * T
        for i in range(B - sum(base)):
            base[i] += 1
        return base
    w = [math.sqrt(v) for v in tv]
    sw = sum(w)
    n = [max(1, int(round(B * x / sw))) for x in w]
    while sum(n) < B:
        i = max(range(T), key=lambda j: w[j] / n[j])
        n[i] += 1
    while sum(n) > B:
        i = max((j for j in range(T) if n[j] > 1), key=lambda j: n[j] / w[j])
        n[i] -= 1
    return n


def estimate(q, B, protocol, tv, rng):
    est = [0.0] * K
    if protocol == "indep":
        for p in range(K):
            n = alloc(B, tv, False)
            acc = 0.0
            for t in range(T):
                for _ in range(n[t]):
                    acc += episode(t, p, q, None, rng)
            est[p] = acc / B
    else:
        n = alloc(B, tv, protocol == "strat")
        for t in range(T):
            acc = [0.0] * K
            for _ in range(n[t]):
                D = [rng.random() for _ in range(len(TASKS[t]))]
                for p in range(K):
                    acc[p] += episode(t, p, q, D, rng)
            for p in range(K):
                est[p] += acc[p] / n[t]
        est = [x / T for x in est]
    return est


def kendall(a, b):
    n, c, d = len(a), 0, 0
    for i in range(n):
        for j in range(i + 1, n):
            s = (a[i] - a[j]) * (b[i] - b[j])
            if s > 0: c += 1
            elif s < 0: d += 1
    return (c - d) / (c + d) if (c + d) else 1.0


def pair_acc(est, gt):
    c = tot = 0
    for i in range(K):
        for j in range(i + 1, K):
            s = (est[i] - est[j]) * (gt[i] - gt[j])
            if s != 0:
                tot += 1
                c += 1 if s > 0 else 0
    return c / tot if tot else 1.0


def top1(est, gt):
    return int(max(range(K), key=lambda p: est[p]) == max(range(K), key=lambda p: gt[p]))


def q1(seed=11, reps=240, budgets=(32, 64, 128, 256, 512)):
    q = build_world()
    _, _, gt = ground_truth(q)
    tv = task_var(q)
    rng = random.Random(seed)
    rows = {}
    for proto in ("indep", "pair", "strat"):
        rows[proto] = []
        for B in budgets:
            taus, pas, t1 = [], [], []
            for _ in range(reps):
                est = estimate(q, B, proto, tv, rng)
                taus.append(kendall(est, gt))
                pas.append(pair_acc(est, gt))
                t1.append(top1(est, gt))
            rows[proto].append({
                "budget_per_policy": B,
                "kendall_tau": round(statistics.mean(taus), 4),
                "pairwise_acc": round(statistics.mean(pas), 4),
                "top1_acc": round(statistics.mean(t1), 4),
            })
    return {"ground_truth_rank": sorted(range(K), key=lambda p: -gt[p]),
            "ground_truth_score": [round(x, 4) for x in gt],
            "results": rows}



def q1b_correlation(seed=31, n=4000):
    """Estimate average pairwise correlation of per-episode scores under a
    shared scenario draw. CRN diff-variance is (1-rho) x independent."""
    q = build_world()
    rng = random.Random(seed)
    samples = [[] for _ in range(K)]
    for _ in range(n):
        t = rng.randrange(T)
        D = [rng.random() for _ in range(len(TASKS[t]))]
        for p in range(K):
            samples[p].append(episode(t, p, q, D, rng))
    rhos = []
    for i in range(K):
        for j in range(i + 1, K):
            a, b = samples[i], samples[j]
            ma, mb = sum(a) / len(a), sum(b) / len(b)
            cov = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / len(a)
            va = sum((x - ma) ** 2 for x in a) / len(a)
            vb = sum((y - mb) ** 2 for y in b) / len(b)
            rhos.append(cov / math.sqrt(va * vb))
    rho = sum(rhos) / len(rhos)
    return {"mean_pairwise_score_correlation": round(rho, 4),
            "implied_crn_efficiency_1/(1-rho)": round(1.0 / (1.0 - rho), 3)}

def q2(seed=23, reps=120000):
    """Policy-side outcome variance vs rank. Normal per-port scores."""
    rng = random.Random(seed)
    cases = {
        "control_equal_mean": ((0.60, 0.02), (0.60, 0.10)),
        "A_lowvar_mean_-0.005": ((0.595, 0.02), (0.60, 0.10)),
        "A_lowvar_mean_+0.010": ((0.610, 0.02), (0.60, 0.10)),
        "A_highvar_mean_+0.010": ((0.610, 0.10), (0.60, 0.02)),
    }
    out = {}
    for name, (A, B) in cases.items():
        out[name] = {}
        for N in (1, 3, 10, 32):
            winA = 0
            for _ in range(reps):
                ma = sum(rng.gauss(A[0], A[1]) for _ in range(N)) / N
                mb = sum(rng.gauss(B[0], B[1]) for _ in range(N)) / N
                winA += 1 if ma > mb else 0
            out[name][f"N={N}"] = round(winA / reps, 4)
    return out


if __name__ == "__main__":
    res = {"Q1_rank_fidelity": q1(), "Q1b_correlation": q1b_correlation(), "Q2_win_probability": q2()}
    path = "/home/runner/work/xuen/xuen/workspace/tmp/r3_rank_sim.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))
