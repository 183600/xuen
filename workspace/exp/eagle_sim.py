#!/usr/bin/env python3
"""EAGLE round-61 simulation (pure python, no numpy).

Three synthetic experiments backing the round-61 claims:
  A. DCF  : correlated agent errors -> "consensus hallucination";
            n_eff gate suppresses false consensus.
  B. QEC  : quorum/replication durability under independent node failure,
            and Byzantine forgery acceptance.
  C. LASE : accurate-but-late vs fast-but-sufficient under time-to-contact.
All numbers are synthetic and reproducible (fixed seed).
"""
import json
import math
import random

random.seed(20261112)


def gauss(mu=0.0, sigma=1.0):
    return random.gauss(mu, sigma)


def mean(xs):
    return sum(xs) / len(xs)


# ---------------------------------------------------------------- A. DCF
def sim_dcf(k=5, s=1.5, sigma_i=1.0, sigma_c=1.0,
            n_calib=2000, n_test=20000, n_min=2.0):
    def sample(n):
        rows = []
        for _ in range(n):
            z = 1 if random.random() < 0.5 else 0
            common = gauss(0.0, sigma_c)
            logits = [s * (2 * z - 1) + common + gauss(0.0, sigma_i)
                      for _ in range(k)]
            rows.append((z, logits))
        return rows

    calib = sample(n_calib)
    test = sample(n_test)

    # estimate pairwise error correlation on calibration set
    errs = [[((1 if logits[i] > 0 else 0) != z) for z, logits in calib]
            for i in range(k)]

    def corr(a, b):
        ma, mb = mean(a), mean(b)
        va = sum((x - ma) ** 2 for x in a)
        vb = sum((x - mb) ** 2 for x in b)
        if va == 0 or vb == 0:
            return 0.0
        cov = sum((a[i] - ma) * (b[i] - mb) for i in range(len(a)))
        return cov / math.sqrt(va * vb)

    rhos = []
    for i in range(k):
        for j in range(i + 1, k):
            rhos.append(corr(errs[i], errs[j]))
    rho_bar = mean(rhos) if rhos else 0.0
    n_eff = k / (1.0 + (k - 1) * max(0.0, rho_bar))

    def stats(rows):
        acc1 = accf = 0
        agree = false_cons = 0
        conf = 0.0
        covered = cov_correct = 0
        for z, logits in rows:
            d = [1 if lg > 0 else 0 for lg in logits]
            fused = mean(logits)
            df = 1 if fused > 0 else 0
            acc1 += (d[0] == z)
            accf += (df == z)
            conf += abs(fused)
            if len(set(d)) == 1:
                agree += 1
                if df != z:
                    false_cons += 1
            if n_eff >= n_min:
                covered += 1
                cov_correct += (df == z)
        n = len(rows)
        return {
            "single_agent_acc": acc1 / n,
            "fused_acc": accf / n,
            "all_agree_rate": agree / n,
            "false_consensus_rate": false_cons / n,
            "mean_abs_confidence": conf / n,
            "gate_coverage": covered / n,
            "gated_acc_on_covered": (cov_correct / covered) if covered else None,
        }

    out = {"k": k, "rho_bar": rho_bar, "n_eff": n_eff, "n_min": n_min}
    out.update(stats(test))
    return out


# ---------------------------------------------------------------- B. QEC
def binom_tail_ge(n, q, p):
    """P(X >= q) with X ~ Binomial(n, 1-p) = at least q alive (fail prob p)."""
    # X alive ~ Binomial(n, 1-p)
    s = 0.0
    for x in range(q, n + 1):
        s += math.comb(n, x) * ((1 - p) ** x) * (p ** (n - x))
    return s


def sim_qec():
    out = []
    for p in (0.01, 0.05, 0.10):
        row = {"p_fail": p, "replicas": []}
        for r in (1, 2, 3, 4, 5):
            # simple majority quorum among r copies
            q = r // 2 + 1
            survive = binom_tail_ge(r, q, p)
            row["replicas"].append({
                "r": r, "q": q, "survival_prob": survive,
                "loss_prob": 1 - survive,
            })
        out.append(row)

    # Byzantine: n=3f+1, quorum 2f+1; forged entry accepted iff adversary
    # (f nodes) can supply >= q matching copies. q=2f+1 > f always -> 0.
    byz = []
    for f in range(0, 5):
        n = 3 * f + 1
        q = 2 * f + 1
        byz.append({"f": f, "n": n, "quorum_q": q,
                    "forgery_accept_prob": 0.0 if q > f else 1.0})
    return {"crash": out, "byzantine": byz}


# ---------------------------------------------------------------- C. LASE
def sim_lase():
    models = {
        "slow_accurate": {"acc": 0.98, "latency_ms": 180},
        "fast_sufficient": {"acc": 0.90, "latency_ms": 40},
        "local_cheap": {"acc": 0.82, "latency_ms": 12},
    }
    enforce_ms = 20
    margin_ms = 10
    rows = []
    for t_c in (60, 100, 150, 200, 300):
        row = {"T_c_ms": t_c, "models": []}
        for name, m in models.items():
            admissible = (m["latency_ms"] + enforce_ms + margin_ms) <= t_c
            # if inadmissible, the controller must fall back to the safest
            # enforceable model; approximate safe-success by the best
            # admissible model's accuracy, and mark deadline risk otherwise.
            row["models"].append({
                "model": name, "acc": m["acc"],
                "latency_ms": m["latency_ms"], "admissible": admissible,
                "on_time": admissible,
            })
        adm = [m for m in row["models"] if m["admissible"]]
        row["best_admissible_acc"] = max((m["acc"] for m in adm), default=None)
        # "naive most-accurate" policy: always pick slow_accurate
        slow = row["models"][0]
        row["naive_most_accurate_on_time"] = slow["on_time"]
        rows.append(row)
    return {"enforce_ms": enforce_ms, "margin_ms": margin_ms, "rows": rows}


if __name__ == "__main__":
    dcf = []
    for sc in (0.0, 0.5, 1.0, 2.0, 3.0):
        dcf.append(sim_dcf(sigma_c=sc))
    result = {"dcf": dcf, "qec": sim_qec(), "lase": sim_lase()}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    with open("/home/runner/work/xuen/xuen/workspace/exp/eagle_results.json",
              "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
