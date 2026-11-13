"""Synthetic mechanism check for BRIDGE (round 66: sim-to-real x UniBot-V1).

NOT benchmark evidence.  Isolates four claims used by the write-up:
  (A) a Lipschitz/conformal transfer certificate is sound (no false transfer)
      while naive sim-to-real transfer becomes unsafe as the gap grows;
  (B) a virtual probe auction (VPA) reduces expensive real probes and real
      risk when the twin is trustworthy, and falls back safely when it is not;
  (C) a common-cause bias that fools the twin and the real world in the same
      direction cannot be detected by sim-real comparison alone; an
      independent channel is required and is explicitly modelled;
  (D) open-set attribution flags a composite/unknown fault instead of forcing
      it into the nearest closed-set hypothesis.

Generative models are declared in each function, not fitted to real data.
"""
import json
import math
import os

import numpy as np

rng = np.random.default_rng(20261113)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "bridge_results.json")


# ---------------------------------------------------------------- utilities
def softmax(logits):
    z = np.asarray(logits, dtype=float)
    z = z - z.max()
    e = np.exp(z)
    return e / e.sum()


def logsumexp(x):
    x = np.asarray(x, dtype=float)
    m = x.max()
    return m + math.log(np.exp(x - m).sum())


def gaussian_loglik(obs, mean, mask, sigma):
    idx = np.where(mask)[0]
    if len(idx) == 0:
        return 0.0
    d = obs[idx] - mean[idx]
    return -0.5 * float(d @ d) / (sigma ** 2) - len(idx) * math.log(sigma)


# ---------------------------------------------- (A) transfer certificate
def run_transfer(n=4000, n_cal=600):
    """Linear safety margin m(theta)=m0-w.theta.

    Sim knows theta_sim.  Real theta = theta_sim + gap.  Paired calibration
    gives a noisy estimate of each gap component; a split-conformal quantile
    turns the residual into a one-sided bound.  BRIDGE transfers only when
    m_sim - bound >= 0; naive transfer always accepts.
    """
    m0 = 0.70
    w = np.array([0.5, 0.3, 0.4, 0.6])
    theta_sim = np.array([0.3, 0.2, 0.25, 0.15])
    m_sim = m0 - float(w @ theta_sim)
    sigma_gap = 0.06

    def sample_gap(delta_max, n_samples):
        delta = rng.uniform(0.0, delta_max, n_samples)
        u = rng.normal(size=(n_samples, 4))
        u /= np.linalg.norm(u, axis=1, keepdims=True)
        g = delta[:, None] * u
        g_hat = g + rng.normal(scale=sigma_gap, size=g.shape)
        return g, g_hat

    def conformal_q(delta_max):
        g, g_hat = sample_gap(delta_max, n_cal)
        r = np.abs((g - g_hat) @ w)
        k = min(n_cal, int(math.ceil((n_cal + 1) * 0.95)))
        return float(np.sort(r)[k - 1])

    rows = []
    for delta_max in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
        q = conformal_q(delta_max)
        g, g_hat = sample_gap(delta_max, n)
        m_true = m_sim - g @ w
        bound = np.abs(g_hat @ w) + q
        m_lb = m_sim - bound
        transfer_bridge = m_lb >= 0.0
        transfer_naive = np.ones(n, dtype=bool)
        # oracle: bound using the true gap direction
        transfer_oracle = (m_sim - np.abs(g @ w)) >= 0.0
        rows.append({
            "delta_max": delta_max,
            "conformal_q": round(q, 4),
            "naive_transfer_rate": round(float(transfer_naive.mean()), 4),
            "naive_unsafe_rate": round(float((m_true < 0).mean()), 4),
            "naive_false_safe_rate": round(float(((m_true < 0) &
                                                  transfer_naive).mean()), 4),
            "bridge_transfer_rate": round(float(transfer_bridge.mean()), 4),
            "bridge_unsafe_rate": round(float((m_true < 0).mean()), 4),
            "bridge_false_safe_rate": round(float(((m_true < 0) &
                                                   transfer_bridge).mean()), 4),
            "bridge_mean_lower_bound": round(float(m_lb.mean()), 4),
            "bridge_mean_true_margin_transferred": round(
                float(m_true[transfer_bridge].mean())
                if transfer_bridge.any() else float("nan"), 4),
            "oracle_transfer_rate": round(float(transfer_oracle.mean()), 4),
            "oracle_false_safe_rate": round(float(((m_true < 0) &
                                                   transfer_oracle).mean()), 4),
        })
    return rows


# ---------------------------------------------- (B) virtual probe auction
HYP = ("H0", "H_geo", "H_force", "H_model", "H_gap")

MEANS = np.array([
    [0.0, 0.0, 0.0, 0.0, 0.0],     # H0
    [2.0, -1.0, 0.0, 0.0, 0.0],    # H_geo
    [0.0, 0.0, 0.0, 2.2, 0.0],     # H_force
    [0.0, 1.0, 2.0, 0.0, 0.0],     # H_model
    [0.0, 0.0, 0.0, 0.0, 2.0],     # H_gap
])

PROBES = {
    "press":       (np.array([1, 1, 0, 0, 0], dtype=bool), 1.0),
    "rub":         (np.array([0, 1, 1, 0, 0], dtype=bool), 1.2),
    "tap":         (np.array([1, 0, 1, 0, 0], dtype=bool), 0.8),
    "null_test":   (np.array([0, 0, 0, 1, 0], dtype=bool), 0.05),
    "visual_probe": (np.array([0, 0, 0, 0, 1], dtype=bool), 0.02),
}
PHYSICAL = tuple(PROBES)
SIGMA = 0.7


def post_update(post, obs, mask, sigma, bias=None):
    logs = []
    for i, h in enumerate(HYP):
        m = MEANS[i].copy()
        if bias is not None:
            m = m + bias
        logs.append(math.log(post[i] + 1e-15) +
                    gaussian_loglik(obs, m, mask, sigma))
    z = np.array(logs)
    z -= logsumexp(z)
    return np.exp(z)


def entropy(post):
    p = post[post > 0]
    return float(-(p * np.log(p)).sum())


def expected_info(post, mask, sigma):
    """Gaussian approximation of the entropy reduction of a probe."""
    idx = np.where(mask)[0]
    if len(idx) == 0:
        return 0.0
    mu = MEANS
    C = np.einsum("h,hi,hj->ij", post, mu, mu) - np.outer(mu.T @ post,
                                                          mu.T @ post)
    C = C + 1e-6 * np.eye(5)
    C_post = np.linalg.inv(np.linalg.inv(C) +
                           (1.0 / sigma ** 2) * np.diag(mask.astype(float)))
    sign1, ld1 = np.linalg.slogdet(C)
    sign2, ld2 = np.linalg.slogdet(C_post)
    return max(0.0, 0.5 * (ld1 - ld2)) if sign1 > 0 and sign2 > 0 else 0.0


def simulate_trial(true_h, gap, strategy):
    post = np.ones(len(HYP)) / len(HYP)
    real_probes = 0
    risk = 0.0
    steps = 0
    # a calibration estimate of the gap (noisy, as in a paired calibration set)
    gap_hat = abs(gap + rng.normal(scale=0.08))
    reliability = max(0.0, 1.0 - gap_hat / 1.5)
    bias = gap * np.array([1.0, -0.5, 0.0, 0.0, 0.0])

    if strategy == "random":
        for _ in range(3):
            name = PHYSICAL[rng.integers(len(PHYSICAL))]
            mask, r = PROBES[name]
            obs = MEANS[true_h] + rng.normal(scale=SIGMA, size=5)
            post = post_update(post, obs, mask, SIGMA)
            real_probes += 1
            risk += r
            steps += 1
        return int(np.argmax(post) == true_h), real_probes, risk, entropy(post)

    if strategy == "sim_only":
        for _ in range(3):
            obs = MEANS[true_h] + bias + rng.normal(scale=SIGMA, size=5)
            post = post_update(post, obs, np.ones(5, dtype=bool),
                               SIGMA / max(reliability, 0.15))
            steps += 1
        return int(np.argmax(post) == true_h), real_probes, risk, entropy(post)

    if strategy == "real_only":
        for _ in range(5):
            if post.max() >= 0.9:
                break
            best, best_info = None, -1.0
            for name, (mask, r) in PROBES.items():
                info = expected_info(post, mask, SIGMA)
                if info > best_info:
                    best, best_info = name, info
            mask, r = PROBES[best]
            obs = MEANS[true_h] + rng.normal(scale=SIGMA, size=5)
            post = post_update(post, obs, mask, SIGMA)
            real_probes += 1
            risk += r
            steps += 1
        return int(np.argmax(post) == true_h), real_probes, risk, entropy(post)

    if strategy == "vpa":
        # Stage 1: virtual probing.  Reliability gates how much we listen.
        for _ in range(2):
            obs = MEANS[true_h] + bias + rng.normal(scale=SIGMA, size=5)
            post = post_update(post, obs, np.ones(5, dtype=bool),
                               SIGMA / max(reliability, 0.15))
            steps += 1
        if reliability < 0.30:
            # twin not trustworthy: fall back to real-only selection
            for _ in range(5):
                if post.max() >= 0.9:
                    break
                best, best_info = None, -1.0
                for name, (mask, r) in PROBES.items():
                    info = expected_info(post, mask, SIGMA)
                    if info > best_info:
                        best, best_info = name, info
                mask, r = PROBES[best]
                obs = MEANS[true_h] + rng.normal(scale=SIGMA, size=5)
                post = post_update(post, obs, mask, SIGMA)
                real_probes += 1
                risk += r
                steps += 1
            return int(np.argmax(post) == true_h), real_probes, risk, entropy(post)
        # Stage 2: only pay for a real probe if virtual evidence left doubt.
        for _ in range(2):
            if post.max() >= 0.9:
                break
            best, best_info = None, -1.0
            for name, (mask, r) in PROBES.items():
                info = expected_info(post, mask, SIGMA) * (1.0 + 0.5 * r)
                if info > best_info:
                    best, best_info = name, info
            mask, r = PROBES[best]
            obs = MEANS[true_h] + rng.normal(scale=SIGMA, size=5)
            post = post_update(post, obs, mask, SIGMA)
            real_probes += 1
            risk += r
            steps += 1
        return int(np.argmax(post) == true_h), real_probes, risk, entropy(post)

    raise ValueError(strategy)


def run_vpa(n=500):
    rows = []
    strategies = ("random", "real_only", "sim_only", "vpa")
    for gap in (0.0, 0.5, 1.0):
        for strategy in strategies:
            acc = 0
            probes = 0.0
            risk = 0.0
            ent = 0.0
            for _ in range(n):
                true_h = int(rng.integers(len(HYP)))
                ok, p, r, e = simulate_trial(true_h, gap, strategy)
                acc += ok
                probes += p
                risk += r
                ent += e
            rows.append({
                "gap": gap,
                "strategy": strategy,
                "accuracy": round(acc / n, 4),
                "mean_real_probes": round(probes / n, 3),
                "mean_real_risk": round(risk / n, 3),
                "mean_final_entropy": round(ent / n, 4),
            })
    return rows


# ---------------------------------------------- (C) common-cause gap
def run_common_cause(n=4000):
    """A shared bias b_c affects sim and real evidence identically.

    Paired sim-real comparison cancels b_c, so a paired-only estimate of the
    gap is ~0.  An independent channel observes b_c with probability p_indep.
    BRIDGE with that channel flags unknown/rejects; without it, it is fooled.
    """
    rows = []
    m_sim = 0.6
    for b_common in (0.0, 0.2, 0.4, 0.6, 0.8):
        gap_effect = np.abs(rng.normal(scale=0.12, size=n))   # true sim-real gap
        # paired difference sees gap_effect only; common bias cancels
        gap_hat = gap_effect + rng.normal(scale=0.03, size=n)
        q = 0.10
        transfer_naive = np.ones(n, dtype=bool)
        transfer_paired = (m_sim - gap_hat - q) >= 0.0
        # independent channel detects common bias with p=0.9 when b>0.15
        p_indep = np.where(b_common > 0.15, 0.95, 0.0)
        detected = rng.random(n) < p_indep
        transfer_bridge = transfer_paired & (~detected)
        m_true = m_sim - b_common - gap_effect
        rows.append({
            "b_common": b_common,
            "naive_false_safe_rate": round(float(((m_true < 0) &
                                                  transfer_naive).mean()), 4),
            "paired_only_false_safe_rate": round(float(((m_true < 0) &
                                                        transfer_paired).mean()), 4),
            "bridge_false_safe_rate": round(float(((m_true < 0) &
                                                   transfer_bridge).mean()), 4),
            "bridge_transfer_rate": round(float(transfer_bridge.mean()), 4),
        })
    return rows


# ---------------------------------------------- (D) open-set fault
def run_open_set(n=4000):
    """Closed-set VISTA vs open-set BRIDGE on a composite unseen fault."""
    known = MEANS.copy()
    # composite fault: geo + force + model, not in the hypothesis set
    unknown_mean = np.array([3.0, -2.0, 2.5, 3.0, 2.0])
    # threshold: 95th percentile of the negative log-likelihood of known faults
    cal_scores = []
    for _ in range(2000):
        h = int(rng.integers(len(HYP)))
        obs = known[h] + rng.normal(scale=SIGMA, size=5)
        ll = max(gaussian_loglik(obs, known[i], np.ones(5, dtype=bool), SIGMA)
                 for i in range(len(HYP)))
        cal_scores.append(-ll)
    threshold = float(np.quantile(cal_scores, 0.95))

    def closed_set_outcome(obs):
        lls = [gaussian_loglik(obs, known[i], np.ones(5, dtype=bool), SIGMA)
               for i in range(len(HYP))]
        return int(np.argmax(lls))

    def bridge_outcome(obs):
        # broad unknown component
        lls = [gaussian_loglik(obs, known[i], np.ones(5, dtype=bool), SIGMA)
               for i in range(len(HYP))]
        lls.append(gaussian_loglik(obs, np.zeros(5), np.ones(5, dtype=bool), 5.0))
        post = softmax(lls)
        best_known = int(np.argmax(post[:-1]))
        if post[-1] > 0.5:
            return "unknown"
        return best_known

    rows = []
    # composite/unknown fault
    det = 0
    mis = 0
    for _ in range(n):
        obs = unknown_mean + rng.normal(scale=SIGMA, size=5)
        c = closed_set_outcome(obs)
        b = bridge_outcome(obs)
        det += (b == "unknown")
        mis += (c != "unknown" and c >= 0)
    # known faults should not be over-flagged
    false_unknown = 0
    correct_known = 0
    for _ in range(n):
        h = int(rng.integers(len(HYP)))
        obs = known[h] + rng.normal(scale=SIGMA, size=5)
        b = bridge_outcome(obs)
        false_unknown += (b == "unknown")
        correct_known += (b == h)
    rows.append({
        "unknown_detection_rate": round(det / n, 4),
        "closed_set_forced_misattribution_rate": round(mis / n, 4),
        "known_fault_accuracy": round(correct_known / n, 4),
        "known_false_unknown_rate": round(false_unknown / n, 4),
        "calibration_threshold": round(threshold, 4),
    })
    return rows


def main():
    result = {
        "seed": 20261113,
        "note": "synthetic mechanism check, not benchmark evidence",
        "A_transfer_certificate": run_transfer(),
        "B_virtual_probe_auction": run_vpa(),
        "C_common_cause": run_common_cause(),
        "D_open_set": run_open_set(),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
