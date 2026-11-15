"""STEPGAUGE-RAS synthetic mechanism check (NOT benchmark evidence).

Three checks:
  A. Step-credit selective certification separates "lucky-safe" from
     process-justified safety (outcome-only cannot rank).
  B. Anytime-valid e-process keeps false-commit <= delta under optional
     stopping, where repeated per-step confidence tests inflate.
  C. Risk-bounded commitment gating (wait / ask) vs fixed endpointing on a
     streaming safety-relevant (GO vs STOP) recognition toy.

Usage:
  python exp/stepgauge_sim.py --out exp/stepgauge_results.json
"""
import argparse
import json

import numpy as np


def auc(scores, labels):
    """AUC via rank statistic (labels in {0,1})."""
    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels, dtype=int)
    pos = scores[labels == 1]
    neg = scores[labels == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    order = np.argsort(np.concatenate([pos, neg]), kind="mergesort")
    ranks = np.empty(len(order), dtype=float)
    ranks[order] = np.arange(1, len(order) + 1)
    rank_pos = ranks[: len(pos)].sum()
    return float((rank_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def part_a(n=40000, t_steps=8, seed=20261114):
    rng = np.random.default_rng(seed)
    valid = rng.random((n, t_steps)) < 0.90
    # Evidence score: calibrated posterior P(step valid | x), known Beta
    # likelihoods (oracle-calibrated; the point is the *structure* not the net).
    x = np.where(valid,
                 rng.beta(6.0, 2.0, (n, t_steps)),
                 rng.beta(2.0, 6.0, (n, t_steps)))
    prior = 0.90
    lik1 = np.exp(
        (5.0 * np.log(np.clip(x, 1e-12, 1.0))
         + 1.0 * np.log(np.clip(1.0 - x, 1e-12, 1.0)))
        + np.log(7.0)
    )
    lik0 = np.exp(
        (1.0 * np.log(np.clip(x, 1e-12, 1.0))
         + 5.0 * np.log(np.clip(1.0 - x, 1e-12, 1.0)))
        + np.log(7.0)
    )
    post = prior * lik1 / (prior * lik1 + (1.0 - prior) * lik0)
    step_min = post.min(axis=1)               # bottleneck step score
    step_prod = post.prod(axis=1)             # e-product style score
    process_valid = valid.all(axis=1)

    # Outcome: good process can still fail (exogenous shock); bad process can
    # be rescued by an unmodeled safety layer (luck).
    shock = rng.random(n) < 0.08
    rescue = rng.random(n) < 0.50
    unsafe = np.where(process_valid, shock, ~rescue)
    safe = ~unsafe

    out = {}
    out["luck_rate"] = float(np.mean(safe & ~process_valid))
    out["desert_rate"] = float(np.mean(unsafe & process_valid))
    out["auc_step_min_vs_process"] = auc(step_min, process_valid)
    out["auc_step_prod_vs_process"] = auc(step_prod, process_valid)
    out["auc_outcome_vs_process"] = auc(safe.astype(float), process_valid)

    # Outcome-only "certification" (safe episodes) vs step-credit withholding.
    out["outcome_only_cert_rate"] = float(np.mean(safe))
    out["outcome_only_false_cert_rate"] = float(
        np.mean(~process_valid & safe) / max(np.mean(safe), 1e-9))
    thresholds = [0.3, 0.5, 0.7, 0.9]
    curve = []
    for th in thresholds:
        cert = step_min >= th
        cov = float(np.mean(cert))
        sel_risk = float(np.mean(unsafe[cert])) if cert.any() else float("nan")
        false_cert = float(np.mean(~process_valid[cert])) if cert.any() else float("nan")
        lucky_withheld = float(np.mean(step_min[safe & ~process_valid] < th))
        curve.append(dict(theta=th, coverage=cov, selective_risk=sel_risk,
                          false_cert_rate=false_cert,
                          lucky_safe_withheld=lucky_withheld))
    out["selective_curve"] = curve
    return out


def part_b(n=60000, k=50, delta=0.05, kappa=0.5, seed=20261115):
    """p-value to e-value: e(p)=kappa*p^(kappa-1), valid for p~U(0,1)."""
    rng = np.random.default_rng(seed)
    # H0: p ~ U(0,1) each look (independent evidence batches).
    def run(p):
        e = kappa * np.power(np.clip(p, 1e-15, 1.0), kappa - 1.0)
        m = np.cumprod(e, axis=1)
        return m.max(axis=1)

    p0 = rng.random((n, k))
    max0 = run(p0)
    false_eproc = float(np.mean(max0 >= 1.0 / delta))
    false_peek = float(np.mean((p0 <= delta).any(axis=1)))

    # H1: p stochastically smaller (Beta(0.4,1)); expected commit step.
    p1 = rng.beta(0.40, 1.0, (n, k))
    m1 = np.cumprod(kappa * np.power(np.clip(p1, 1e-15, 1.0), kappa - 1.0), axis=1)
    committed = m1 >= 1.0 / delta
    hit = committed.any(axis=1)
    first = np.where(hit, committed.argmax(axis=1) + 1, k)
    return dict(
        delta=delta,
        eprocess_false_commit_at_h0=false_eproc,
        repeated_peek_false_commit_at_h0=false_peek,
        h1_commit_rate=float(np.mean(hit)),
        h1_median_steps=float(np.median(first)),
    )


def part_c(n=40000, k=40, seed=20261116):
    rng = np.random.default_rng(seed)
    y = rng.integers(0, 2, n)                 # 1 = GO, 0 = STOP
    sgn = np.where(y == 1, 1.0, -1.0)
    # Informativeness rises with audio length (streaming ASR).
    mu = 0.10 + 0.55 * (np.arange(1, k + 1) / k) ** 1.4
    x = sgn[:, None] * mu[None, :] + rng.normal(0.0, 1.0, (n, k))
    llr = np.cumsum(x, axis=1)
    p_go = 1.0 / (1.0 + np.exp(-llr))

    def evaluate(commit_mask):
        decided = commit_mask.any(axis=1)
        idx = np.where(decided, commit_mask.argmax(axis=1), k - 1)
        chosen = p_go[np.arange(n), idx] > 0.5
        ok = chosen == (y == 1)
        err = float(np.mean(~ok[decided])) if decided.any() else float("nan")
        return decided, idx, ok, err

    fixed = {}
    for k0 in (8, 12, 20, 30):
        mask = np.zeros((n, k), dtype=bool)
        mask[:, k0 - 1] = True
        _, idx, ok, err = evaluate(mask)
        fixed[f"k{k0}"] = dict(error=err, mean_frames=float(np.mean(idx + 1)))

    # Risk-bounded gate: commit when posterior confidence and safety margin
    # are both high; else keep listening; ask after a patience window.
    conf = np.maximum(p_go, 1.0 - p_go)
    margin = np.abs(p_go - 0.5)
    ready = (conf >= 0.99) & (margin >= 0.45)
    patience = 26
    ready[:, patience:] = True             # ask decision point at patience
    gate = np.zeros((n, k), dtype=bool)
    gate[:, :patience] = ready[:, :patience]
    gate[:, patience - 1] = True           # forced resolve (ask) at patience

    decided, idx, ok, err_gate = evaluate(gate)
    # 'ask' resolved by clarification with prob .95; residual error otherwise.
    asked = (conf[:, patience - 1] < 0.99) | (margin[:, patience - 1] < 0.45)
    resolve = rng.random(n) < 0.95
    err_ask_before = ~ok
    ok_after = np.where(asked, ok | resolve, ok)
    err_after = float(np.mean(~ok_after))
    return dict(
        fixed=fixed,
        gate=dict(error_before_resolve=err_gate,
                  error_after_resolve=err_after,
                  ask_rate=float(np.mean(asked)),
                  mean_frames=float(np.mean(idx + 1))),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="exp/stepgauge_results.json")
    args = ap.parse_args()
    res = dict(
        seed=20261114,
        note="synthetic mechanism check, not benchmark evidence",
        part_a_step_credit=part_a(),
        part_b_optional_stopping=part_b(),
        part_c_commitment_gating=part_c(),
    )
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
