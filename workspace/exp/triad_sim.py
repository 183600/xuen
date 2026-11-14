"""Synthetic mechanism check for TRIAD-RAS (round 72: 3D perception x indicator system).

NOT benchmark evidence.  Isolates four claims:
  A. The R71 reward-event dual cannot separate a *spatially wrong but
     event-identical* change (same 2D motion signature at another 3D
     location / scale) from an honest one.  Adding a 3D metric witness
     separates them, but only through the witness observability kappa.
  B. A non-compensatory (meet) indicator aggregation cannot be bought off by
     good task scores or by imputing a missing witness; a weighted sum can.
  C. Spatial view actions chosen by value-of-spatial-information (VoSI)
     cover more safety-relevant witness mass per unit cost than random views.
  D. A witness schema that checks only the letter of the task (pose at the
     target) certifies a "hover" hack; adding the support witness closes it,
     but only where the support witness is observable.

Pure numpy/scipy, deterministic seed.  Run with:
  PYTHONPATH=.pylibs python exp/triad_sim.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.stats import rankdata

SEED = 20261114
N = 60000
rng = np.random.default_rng(SEED)


def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """Mann-Whitney AUC with average ranks for ties."""
    allv = np.concatenate([pos, neg])
    ranks = rankdata(allv)
    n1, n0 = len(pos), len(neg)
    return float((ranks[:n1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def generation(kappa: float, n: int = N):
    """Equal-size honest / hallucination / spatial-spoof / metric-alias."""
    per = n // 4
    labels = np.array(["honest"] * per + ["hallucination"] * per
                      + ["spatial_spoof"] * per + ["metric_alias"] * per)
    rng.shuffle(labels)

    event_res = np.empty(n)
    loc_res = np.empty(n)
    scale_res = np.empty(n)
    for i, c in enumerate(labels):
        if c == "honest":
            event_res[i] = abs(rng.normal(0.0, 1.0))
            loc_res[i] = abs(rng.normal(0.0, 1.0))
            scale_res[i] = abs(rng.normal(0.0, 1.0))
        elif c == "hallucination":          # reward on, no physical change
            event_res[i] = abs(rng.normal(4.0, 1.0))
            loc_res[i] = abs(rng.normal(4.0, 1.0))
            scale_res[i] = abs(rng.normal(4.0, 1.0))
        elif c == "spatial_spoof":          # event is real, place is wrong
            event_res[i] = abs(rng.normal(0.0, 1.0))
            loc_res[i] = abs(rng.normal(3.5, 1.0))
            scale_res[i] = abs(rng.normal(0.0, 1.0))
        else:                               # metric_alias: right place, wrong scale
            event_res[i] = abs(rng.normal(0.0, 1.0))
            loc_res[i] = abs(rng.normal(0.0, 1.0))
            scale_res[i] = abs(rng.normal(3.5, 1.0))

    observed = rng.random(n) < kappa
    witness_res = np.maximum(loc_res, scale_res)
    # Unobserved witness is treated as *unverified*: it contributes no
    # evidence, so TRIAD falls back to the R71 event residual.
    triad_score = event_res + observed * witness_res
    return labels, event_res, triad_score


def detection_table():
    rows = []
    for kappa in (1.0, 0.7, 0.4, 0.0):
        labels, r71, triad = generation(kappa)
        honest = labels == "honest"
        row = {"kappa": kappa}
        for cls in ("hallucination", "spatial_spoof", "metric_alias"):
            pos = labels == cls
            row[cls] = {
                "r71_auc": round(auc(r71[pos], r71[honest]), 3),
                "triad_auc": round(auc(triad[pos], triad[honest]), 3),
            }
        rows.append(row)
    return rows


def aggregation_table():
    """Certification when the critical safety witness is missing.

    Weighted sum imputes a missing witness as a neutral 0.5; meet treats it
    as bottom.  Task indicator is good with prob 0.8.  A weighted score can
    cross its threshold on the strength of the task term alone; the meet
    cannot.  We report the probability of certifying a scene whose critical
    witness is *missing* (the compensation failure).
    """
    rows = []
    n = 200000
    for p_miss in (0.0, 0.1, 0.3, 0.5):
        missing = rng.random(n) < p_miss
        task = rng.random(n) < 0.8
        w_safety = np.where(missing, 0.5, 1.0)
        weighted = 0.3 * w_safety + 0.7 * task.astype(float)
        weighted_pass = weighted > 0.60
        meet_pass = ~missing
        rows.append({
            "p_missing": p_miss,
            "weighted_cert_despite_missing": round(float(np.mean(weighted_pass & missing)), 3),
            "meet_cert_despite_missing": round(float(np.mean(meet_pass & missing)), 3),
        })
    return rows


def view_table(trials: int = 2000, patches: int = 20, views: int = 8, k: int = 3):
    """Set-cover: 3D view actions cover weighted unobserved witness mass."""
    greedy_cov, random_cov = [], []
    set_rng = np.random.default_rng(SEED + 1)
    for _ in range(trials):
        w = set_rng.random(patches) + 0.1
        cover = set_rng.random((views, patches)) < 0.30
        cost = 1.0 + 2.0 * set_rng.random(views)

        chosen = set()
        covered = np.zeros(patches, dtype=bool)
        for _ in range(k):
            best, best_score = None, -1.0
            for v in range(views):
                if v in chosen:
                    continue
                gain = float(w[~covered & cover[v]].sum())
                score = gain / cost[v]
                if score > best_score:
                    best, best_score = v, score
            chosen.add(best)
            covered |= cover[best]
        greedy_cov.append(float(w[covered].sum() / w.sum()))

        chosen = set(set_rng.choice(views, size=k, replace=False).tolist())
        covered = np.zeros(patches, dtype=bool)
        for v in chosen:
            covered |= cover[v]
        random_cov.append(float(w[covered].sum() / w.sum()))
    return {
        "greedy_mean_coverage": round(float(np.mean(greedy_cov)), 3),
        "random_mean_coverage": round(float(np.mean(random_cov)), 3),
        "trials": trials,
    }


def schema_table():
    """Hover hack: pose at target, but no support contact."""
    rows = []
    n = 50000
    for kappa in (1.0, 0.7, 0.4, 0.0):
        observed = rng.random(n) < kappa
        # S1: pose only -> always certifies the hover hack.
        s1 = np.ones(n, dtype=bool)
        # S2: pose + support -> rejects when support witness is observed;
        # when it is unobserved, it cannot reject (unverified is reported,
        # but the schema-only pipeline treats it as pass here to show the gap).
        s2 = ~observed
        rows.append({
            "kappa_support": kappa,
            "s1_pose_only_cert": round(float(np.mean(s1)), 3),
            "s2_pose_plus_support_cert": round(float(np.mean(s2)), 3),
            "unverified_rate": round(float(np.mean(~observed)), 3),
        })
    return rows


def main() -> None:
    out = {
        "seed": SEED,
        "n_trials_detection": N,
        "note": "synthetic mechanism check; not benchmark evidence",
        "detection": detection_table(),
        "aggregation": aggregation_table(),
        "view_cover": view_table(),
        "schema": schema_table(),
    }
    path = Path(__file__).with_name("triad_results.json")
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
