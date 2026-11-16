"""Synthetic mechanism checks for RACR (research line round 10, cycle-2 round 2).

NOT benchmark evidence.  Three isolated mechanism checks, stdlib only:

  A. MONDRIAN RETRIEVAL-CONDITIONED BETA (def. 542, lemma 87).
     Residuals are heteroscedastic across domain-signature cells.  Compare a
     single global split-conformal beta with a per-cell (Mondrian) beta used
     only when enough neighbour cases exist.  Metric: per-cell test coverage at
     alpha=0.01 and mean certificate width.

  B. SURVIVORSHIP BIAS OF THE CASE BASE (def. 549, lemma 92).
     If only "clean/successful" episodes are stored, the residual distribution
     is right-censored; the retrieved beta underestimates true error.  Compare
     success-only storage vs. residual-triggered storage (store aborts /
     near-misses too) on an unbiased test stream.

  C. ROADMAP <-> DEGRADATION DUALITY (def. 547, lemma 89).
     Compile a small capability DAG: topological order must respect prereqs and
     every promotion edge must own a certified neutral-element rollback edge.
     A deliberately broken roadmap must be rejected.
"""
import json
import math
import random

ALPHA = 0.01
N_CAL = 3000
N_TEST = 20000


def conformal_quantile(xs, alpha):
    """Split-conformal upper quantile: ceil((n+1)(1-alpha))-th order stat."""
    if not xs:
        return None
    ys = sorted(xs)
    k = int(math.ceil((len(ys) + 1) * (1.0 - alpha)))
    k = min(max(k, 1), len(ys))
    return ys[k - 1]


def half_normal(scale, rng):
    return abs(rng.gauss(0.0, scale))


# ---------------------------------------------------------------- A. Mondrian
def mondrian_check(seed=7):
    rng = random.Random(seed)
    scales = [0.4, 0.6, 0.8, 1.0, 1.4, 2.0]
    cal = {c: [half_normal(s, rng) for _ in range(N_CAL)]
           for c, s in enumerate(scales)}
    test = {c: [half_normal(s, rng) for _ in range(N_TEST)]
            for c, s in enumerate(scales)}

    pooled = [r for xs in cal.values() for r in xs]
    beta_global = conformal_quantile(pooled, ALPHA)

    rows = []
    for c, s in enumerate(scales):
        beta_c = conformal_quantile(cal[c], ALPHA)
        cov_g = sum(r <= beta_global for r in test[c]) / N_TEST
        cov_c = sum(r <= beta_c for r in test[c]) / N_TEST
        rows.append({
            "cell": c, "scale": s,
            "beta_global": round(beta_global, 4),
            "beta_mondrian": round(beta_c, 4),
            "coverage_global": round(cov_g, 4),
            "coverage_mondrian": round(cov_c, 4),
        })

    return {
        "alpha": ALPHA,
        "beta_global": round(beta_global, 4),
        "min_cell_coverage_global": round(min(r["coverage_global"] for r in rows), 4),
        "min_cell_coverage_mondrian": round(min(r["coverage_mondrian"] for r in rows), 4),
        "mean_beta_global": round(beta_global, 4),
        "mean_beta_mondrian": round(sum(r["beta_mondrian"] for r in rows) / len(rows), 4),
        "cells": rows,
    }


# ------------------------------------------------------- B. Survivorship bias
def survivorship_check(seed=11):
    rng = random.Random(seed)
    scale = 1.0
    # A "clean episode" is only written to the case base when the observed
    # residual stayed below a logging threshold (proxy for task success).
    log_threshold = 1.5
    n_store = 6000
    stored_clean = []
    while len(stored_clean) < n_store:
        r = half_normal(scale, rng)
        if r <= log_threshold:
            stored_clean.append(r)
    stored_all = [half_normal(scale, rng) for _ in range(n_store)]

    beta_clean = conformal_quantile(stored_clean, ALPHA)
    beta_all = conformal_quantile(stored_all, ALPHA)

    test = [half_normal(scale, rng) for _ in range(N_TEST)]
    cov_clean = sum(r <= beta_clean for r in test) / N_TEST
    cov_all = sum(r <= beta_all for r in test) / N_TEST
    true_q = conformal_quantile(test, ALPHA)

    return {
        "scale": scale,
        "log_threshold": log_threshold,
        "true_99pct_residual": round(true_q, 4),
        "beta_from_clean_store": round(beta_clean, 4),
        "beta_from_full_store": round(beta_all, 4),
        "coverage_clean_store": round(cov_clean, 4),
        "coverage_full_store": round(cov_all, 4),
        "stored_fraction_of_tail": round(
            sum(r > log_threshold for r in test) / N_TEST, 4),
    }


# ------------------------------------------------- C. Roadmap / rollback dual
def roadmap_check():
    # stage -> (prereqs, experiments, has_rollback)
    good = {
        "L0-v6":        ([], ["E570"], True),
        "L1-v7":        (["L0-v6"], ["E556"], True),
        "L2-v8":        (["L1-v7"], ["E531"], True),
        "L3-v9-AC":     (["L2-v8"], ["E551", "E552"], True),
        "L4-v9-MW":     (["L2-v8", "L3-v9-AC"], ["E555", "E566"], True),
        "L5-v9-ID":     (["L4-v9-MW"], ["E559", "E560"], True),
        "L6-RAC-beta":  (["L3-v9-AC", "L5-v9-ID"], ["E572", "E573"], True),
        "L7-RAC-recov": (["L6-RAC-beta"], ["E574", "E589"], True),
        "L8-RC":        (["L4-v9-MW", "L6-RAC-beta"], ["E581", "E582"], True),
    }
    broken = dict(good)
    broken["L6-RAC-beta"] = (good["L6-RAC-beta"][0],
                             good["L6-RAC-beta"][1], False)

    def compile_roadmap(g):
        order = []
        seen = set()
        # Kahn topological sort
        indeg = {v: len(set(p)) for v, (p, _, _) in g.items()}
        frontier = [v for v, d in indeg.items() if d == 0]
        while frontier:
            frontier.sort()
            v = frontier.pop(0)
            order.append(v)
            seen.add(v)
            for w, (ps, _, _) in g.items():
                if v in ps:
                    indeg[w] -= 1
                    if indeg[w] == 0:
                        frontier.append(w)
        if len(order) != len(g):
            return {"ok": False, "reason": "cycle", "order": order}
        bad_edges = []
        for v, (ps, exp, rb) in g.items():
            for p in ps:
                if order.index(p) >= order.index(v):
                    bad_edges.append({"edge": f"{p}->{v}", "why": "order"})
            if not rb:
                bad_edges.append({"edge": f"{v}->{v}^-", "why": "no_rollback"})
        return {"ok": not bad_edges, "order": order, "bad_edges": bad_edges,
                "n_promotion_edges": sum(len(set(ps)) for ps, _, _ in g.values())}

    return {"good": compile_roadmap(good), "broken": compile_roadmap(broken)}


if __name__ == "__main__":
    out = {
        "note": "synthetic mechanism checks; not benchmark evidence",
        "A_mondrian_beta": mondrian_check(),
        "B_survivorship": survivorship_check(),
        "C_roadmap_duality": roadmap_check(),
    }
    with open("exp/racr_results.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(json.dumps(out, indent=2, ensure_ascii=False))
