"""Synthetic mechanism check for FABLE (round 63: few-shot x inference latency).

NOT benchmark evidence.  Isolates three claims used by the write-up:
  (A) a meta-prior + ridge few-shot head reaches low error with k<=20
      support episodes, versus ridge/OGD from a zero prior;
  (B) split-conformal few-shot radius has finite-sample coverage, and ACI
      recovers coverage after an abrupt distribution shift;
  (C) an anytime worst-case compiler keeps a valid conservative lower bound
      at budget 0 and only tightens with more candidates, while the deadline
      caps the refinement budget.

Generative models are declared in each function, not fitted to real data.
"""
import json
import math
import os
import random

random.seed(20261112)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def norm(a):
    return math.sqrt(dot(a, a))


def mv(A, x):
    return [dot(row, x) for row in A]


def solve_ridge(X, y, lam):
    """(X^T X + lam I)^-1 X^T y via Gaussian elimination."""
    d = len(X[0])
    A = [[sum(X[i][r] * X[i][c] for i in range(len(X))) +
          (lam if r == c else 0.0) for c in range(d)] for r in range(d)]
    b = [sum(X[i][r] * y[i] for i in range(len(X))) for r in range(d)]
    for col in range(d):
        piv = max(range(col, d), key=lambda r: abs(A[r][col]))
        A[col], A[piv] = A[piv], A[col]
        b[col], b[piv] = b[piv], b[col]
        if abs(A[col][col]) < 1e-12:
            A[col][col] = 1e-12
        inv = 1.0 / A[col][col]
        for c in range(col, d):
            A[col][c] *= inv
        b[col] *= inv
        for r in range(d):
            if r == col:
                continue
            f = A[r][col]
            if f == 0.0:
                continue
            for c in range(col, d):
                A[r][c] -= f * A[col][c]
            b[r] -= f * b[col]
    return b


def randn(scale=1.0):
    return random.gauss(0.0, scale)


def unit_vec(d):
    v = [randn() for _ in range(d)]
    n = norm(v) or 1.0
    return [x / n for x in v]


# ---------------------------------------------------------------- experiment A
def few_shot_curve(d=16, tasks=240, prior_gap=0.8, noise=0.15, lam=0.5):
    ks = [1, 2, 3, 5, 10, 20, 50]
    out = []
    for k in ks:
        e_meta, e_zero, e_ogd = 0.0, 0.0, 0.0
        for _ in range(tasks):
            w_star = [randn(1.0 / math.sqrt(d)) for _ in range(d)]
            # meta prior is offset by a fixed task-family gap
            shift = unit_vec(d)
            w_meta = [w - prior_gap * s for w, s in zip(w_star, shift)]
            X = [[randn() for _ in range(d)] for _ in range(k)]
            y = [dot(x, w_star) + randn(noise) for x in X]
            # meta-prior ridge
            y_res = [yy - dot(x, w_meta) for yy, x in zip(y, X)]
            delta = solve_ridge(X, y_res, lam)
            w_hat = [a + b for a, b in zip(w_meta, delta)]
            e_meta += norm([a - b for a, b in zip(w_hat, w_star)])
            # zero-prior ridge
            w_hat0 = solve_ridge(X, y, lam)
            e_zero += norm([a - b for a, b in zip(w_hat0, w_star)])
            # one-pass OGD from the meta prior (same data, k steps);
            # step is normalized by the feature norm to stay stable.
            w = list(w_meta)
            for x, yy in zip(X, y):
                pred = dot(x, w)
                g = [2.0 * (pred - yy) * xi for xi in x]
                eta = 0.1 / (1.0 + dot(x, x))
                w = [wi - eta * gi for wi, gi in zip(w, g)]
            e_ogd += norm([a - b for a, b in zip(w, w_star)])
        out.append({
            "k": k,
            "meta_ridge_err": round(e_meta / tasks, 4),
            "zero_ridge_err": round(e_zero / tasks, 4),
            "meta_ogd_err": round(e_ogd / tasks, 4),
        })
    return out


# ---------------------------------------------------------------- experiment B
def conformal_quantile(scores, alpha):
    n = len(scores)
    idx = math.ceil((n + 1) * (1.0 - alpha))
    if idx > n:
        return float("inf")
    return sorted(scores)[idx - 1]


def conformal_coverage(alpha, ns=(4, 9, 19, 39, 99, 199), trials=4000):
    rows = []
    for n in ns:
        covered = 0
        inf_rad = 0
        rad_sum = 0.0
        for _ in range(trials):
            cal = [abs(randn()) for _ in range(n)]
            test = abs(randn())
            q = conformal_quantile(cal, alpha)
            if math.isinf(q):
                inf_rad += 1
                covered += 1
            else:
                rad_sum += q
                if test <= q:
                    covered += 1
        finite = trials - inf_rad
        rows.append({
            "n": n,
            "target": round(1.0 - alpha, 3),
            "coverage": round(covered / trials, 4),
            "infinite_radius_rate": round(inf_rad / trials, 3),
            "mean_radius_finite": round(rad_sum / finite, 3) if finite else None,
        })
    return rows


def _emp_quantile(vals, level):
    n = len(vals)
    if n == 0:
        return float("inf")
    idx = min(n, max(1, math.ceil(level * n)))
    return sorted(vals)[idx - 1]


def aci_shift(alpha=0.10, gamma=0.02, T=3000, pre=1500, trials=200,
              window=200):
    """Adaptive conformal inference on the target level (Gibbs-Candes)."""
    fixed_cov_pre, fixed_cov_post = 0, 0
    aci_cov_post, aci_cov_tail = 0.0, 0.0
    for _ in range(trials):
        cal = [abs(randn()) for _ in range(99)]
        q_fixed = conformal_quantile(cal, alpha)
        hist = list(cal[-window:])
        a_t = alpha
        post_cov, tail_cov, tail_n = 0, 0, 0
        for t in range(T):
            scale = 1.0 if t < pre else 2.5
            s = abs(randn(scale))
            fixed_err = 1 if s > q_fixed else 0
            r_t = _emp_quantile(hist, 1.0 - a_t)
            aci_err = 1 if s > r_t else 0
            if t < pre:
                fixed_cov_pre += 1 - fixed_err
            else:
                fixed_cov_post += 1 - fixed_err
                post_cov += 1 - aci_err
                if t >= T - 500:
                    tail_cov += 1 - aci_err
                    tail_n += 1
            # ACI: miscoverage lowers the target level -> larger radius
            a_t = min(0.5, max(0.001, a_t + gamma * (alpha - aci_err)))
            hist.append(s)
            if len(hist) > window:
                hist.pop(0)
        aci_cov_post += post_cov / (T - pre)
        aci_cov_tail += tail_cov / tail_n
    n_post = trials * (T - pre)
    n_pre = trials * pre
    return {
        "target": round(1.0 - alpha, 3),
        "fixed_calibrated_pre_shift": round(fixed_cov_pre / n_pre, 4),
        "fixed_calibrated_post_shift": round(fixed_cov_post / n_post, 4),
        "aci_post_shift": round(aci_cov_post / trials, 4),
        "aci_last500": round(aci_cov_tail / trials, 4),
    }


# ---------------------------------------------------------------- experiment C
def margin(phi):
    """Safety margin with true min 0 on the unit sphere."""
    return 0.60 - 0.50 * max(abs(x) for x in phi) - 0.10 * dot(phi, phi)


def anytime_wcv(ns=(0, 1, 2, 4, 8, 16, 32), trials=400, r=1.0):
    # Lipschitz constant of the margin on the unit ball (conservative)
    L_m = 0.50 + 0.20 * r
    rows = []
    true_min = 0.0  # analytic for this declared margin
    for n in ns:
        over_sum, lb_sum = 0.0, 0.0
        for _ in range(trials):
            center = [randn(0.02) for _ in range(3)]
            # analytic certified lower bound (valid for every phi in the ball)
            lb = margin(center) - L_m * r
            # refinement samples: random directions
            cands = [center]
            for _ in range(n):
                u = unit_vec(3)
                cands.append([center[i] + r * u[i] for i in range(3)])
            m_hat = min(margin(p) for p in cands)
            # sampled min is an upper estimate of the true minimum; the
            # analytic lb is a lower certificate.  Safety uses lb, refinement
            # only shrinks the bracket [lb, m_hat].
            over_sum += max(0.0, m_hat - true_min)
            lb_sum += lb
        rows.append({
            "n_candidates": n,
            "certified_lb_minus_true": round(lb_sum / trials - true_min, 4),
            "sampled_upper_minus_true": round(over_sum / trials, 4),
        })
    return {"true_min": true_min, "rows": rows, "L_m": L_m}


def latency_budget(deadline_ms=1.0, fixed_us=150.0, olp_us=50.0,
                   dispatch_us=100.0, cand_us=30.0, jitter_us=20.0):
    rows = []
    for n in (0, 4, 8, 16, 24, 32):
        mean = fixed_us + olp_us + dispatch_us + n * cand_us
        p99 = mean + 3.0 * jitter_us
        rows.append({
            "n_candidates": n,
            "mean_us": round(mean, 1),
            "p99_us": round(p99, 1),
            "deadline_ms": deadline_ms,
            "miss": p99 > deadline_ms * 1000.0,
        })
    return rows


def main():
    result = {
        "seed": 20261112,
        "note": "synthetic mechanism check, not benchmark evidence",
        "E211_few_shot": few_shot_curve(),
        "E212_conformal_95": conformal_coverage(0.05),
        "E212_conformal_90": conformal_coverage(0.10),
        "E213_aci_shift": aci_shift(),
        "E214_anytime": anytime_wcv(),
        "E215_latency": latency_budget(),
    }
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "fable_results.json"), "w") as f:
        json.dump(result, f, indent=1, ensure_ascii=False)
    print(json.dumps(result, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
