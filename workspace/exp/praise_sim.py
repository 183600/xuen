"""Synthetic mechanism check for PRAISE-VLA (round 16).

NOT benchmark evidence. Isolates five questions that decide whether a single
*designed potential-based reward* should be used (a) to rerank sampled action
chunks at inference and (b) to filter simulator rollouts for a lightweight
offline refit:

  A. reward-guided best-of-K vs likelihood-guided vs top-1, as K grows;
  B. reward misspecification / proxy hacking: how much a spurious reward term
     hurts selection;
  C. adaptive-K: compute (E[K]) vs success tradeoff;
  D. offline reward-filtered refit: iterated filtering under a correct vs a
     misspecified reward (does the policy improve, or get hacked?);
  E. instruction-paraphrase shortcut: does paraphrase augmentation close the
     seen-string vs held-out-paraphrase gap?

Generative model (declared, not fit):
  A/B/C. per episode, q* ~ U[0.4,1.0] is the reachable quality; the policy
    samples K candidate chunks whose true quality is Q_i = clip(q* - E_i),
    E_i ~ Exp(1.3) (more samples -> better best). The model's own likelihood is
    miscalibrated (m_i = Q_i + N(0,sigma_m)); the designed reward is
    r_i = Q_i + N(0,sigma_r) + beta*h_i with h_i an independent hacking feature.
    success iff selected quality >= tau.
  D. policy state = (mu_base, s_policy); rollouts have base ~ N(mu_base, .15)
    and shortcut s ~ U[0,1]; true success quality = base - c*s; the reward
    observes r = base + N(0,.3) + L*s (it *likes* the shortcut and ignores its
    true cost). Filtered BC keeps the top rho by r and refits mu_base, s_policy.
  E. 32 tasks; grounding ability g, exact-string memorization M; paraphrase
    augmentation with A templates/task moves held-out success from g toward the
    augmented ceiling with rate 1/A0. Declared illustrative model.
"""
import math
import json
import random
import statistics

TAU = 0.42  # chosen so the top-1 baseline lands near the ~0.30 public leaderboard


def clip01(x):
    return max(0.0, min(1.0, x))


def argmax(xs):
    return max(range(len(xs)), key=lambda i: xs[i])


# ---------------- A/B: decoding-selection ----------------
def exp_decoding(rng, K, mode, n=20000, sigma_m=1.0, sigma_r=0.35, beta=0.0):
    succ = 0
    qsum = 0.0
    for _ in range(n):
        qstar = rng.uniform(0.4, 1.0)
        Q = [clip01(qstar - rng.expovariate(1.3)) for _ in range(K)]
        if mode == "top1":
            sel = Q[0]
        elif mode == "like":
            m = [Q[i] + rng.gauss(0.0, sigma_m) for i in range(K)]
            sel = Q[argmax(m)]
        elif mode == "reward":
            r = [Q[i] + rng.gauss(0.0, sigma_r) + beta * rng.gauss(0.0, 1.0)
                 for i in range(K)]
            sel = Q[argmax(r)]
        elif mode == "oracle":
            sel = max(Q)
        else:
            raise ValueError(mode)
        if sel >= TAU:
            succ += 1
        qsum += sel
    return succ / n, qsum / n


# ---------------- C: adaptive-K ----------------
def exp_adaptive_k(rng, gap, k_batch=2, k_max=16, n=20000,
                   sigma_m=1.0, sigma_r=0.35):
    """Sample in batches; stop when best reward beats 2nd best by `gap`."""
    succ = 0
    ksum = 0
    for _ in range(n):
        qstar = rng.uniform(0.4, 1.0)
        best_q = -1.0
        best_r = -1e9
        second_r = -1e9
        k = 0
        while k < k_max:
            Q = [clip01(qstar - rng.expovariate(1.3)) for _ in range(k_batch)]
            R = [Q[i] + rng.gauss(0.0, sigma_r) for i in range(k_batch)]
            for q, r in zip(Q, R):
                if r > best_r:
                    second_r = best_r
                    best_r = r
                    best_q = q
                elif r > second_r:
                    second_r = r
            k += k_batch
            if best_r - second_r >= gap:
                break
        if best_q >= TAU:
            succ += 1
        ksum += k
    return succ / n, ksum / n


# ---------------- D: offline reward-filtered refit ----------------
def exp_refit(rng, L, rounds=10, n=4000, rho=0.2, c=0.30, seed_reg=0.01):
    mu = 0.35          # initial mean base skill
    s_pol = 0.5        # initial mean shortcut usage
    traj = []
    for _ in range(rounds):
        base = [rng.gauss(mu, 0.15) for _ in range(n)]
        s = [rng.random() for _ in range(n)]
        r = [base[i] + rng.gauss(0.0, 0.30) + L * s[i] for i in range(n)]
        keep = int(rho * n)
        idx = sorted(range(n), key=lambda i: -r[i])[:keep]
        sel_base = statistics.mean(base[i] for i in idx)
        sel_s = statistics.mean(s[i] for i in idx)
        mu = 0.7 * mu + 0.3 * sel_base + seed_reg
        s_pol = 0.7 * s_pol + 0.3 * sel_s
        true_q = mu - c * s_pol
        succ = 0.5 * (1.0 + math.erf((true_q - TAU) / (0.15 * math.sqrt(2.0))))
        traj.append({"round": _ + 1, "mu": round(mu, 4),
                     "shortcut": round(s_pol, 4),
                     "true_q": round(true_q, 4), "success": round(succ, 4)})
    return traj


# ---------------- E: paraphrase shortcut ----------------
def exp_paraphrase(g=0.35, M=0.55, A0=8.0, n_tasks=32):
    """Held-out paraphrase success vs augmentation templates per task."""
    rows = []
    for A in [0, 1, 2, 4, 8, 16, 32]:
        heldout = g + (1.0 - g) * (1.0 - math.exp(-A / A0))
        seen_ceiling = 1.0 - (1.0 - g) * (1.0 - M)
        seen = seen_ceiling + (1.0 - seen_ceiling) * (1.0 - math.exp(-(A + 1) / A0))
        rows.append({"aug_templates": A, "seen_success": round(seen, 4),
                     "heldout_success": round(heldout, 4),
                     "shortcut_gap": round(seen - heldout, 4)})
    return rows


def main():
    seed = 20261102
    rng = random.Random(seed)
    out = {"seed": seed, "tau": TAU, "note": "synthetic, not benchmark"}

    # A. decoding selection
    A_tab = {}
    for mode in ["top1", "like", "reward", "oracle"]:
        A_tab[mode] = {}
        for K in [1, 4, 8, 16]:
            succ, q = exp_decoding(rng, K, mode)
            A_tab[mode][K] = {"success": round(succ, 4),
                              "mean_quality": round(q, 4)}
    out["A_decoding_selection"] = A_tab

    # B. reward misspecification (beta sweep) at K=8
    B_tab = {}
    for beta in [0.0, 0.1, 0.25, 0.5, 1.0, 2.0]:
        succ, q = exp_decoding(rng, 8, "reward", beta=beta)
        B_tab[str(beta)] = {"success": round(succ, 4),
                            "mean_quality": round(q, 4)}
    out["B_reward_hacking"] = B_tab

    # C. adaptive-K
    C_tab = {}
    for gap in [0.0, 0.2, 0.4, 0.7, 1.0]:
        succ, ek = exp_adaptive_k(rng, gap)
        C_tab[str(gap)] = {"success": round(succ, 4), "expected_K": round(ek, 3)}
    out["C_adaptive_k"] = C_tab

    # D. reward-filtered refit
    D_tab = {}
    for L in [0.0, 0.5, 1.5]:
        D_tab[str(L)] = exp_refit(rng, L)
    out["D_filtered_refit"] = D_tab

    # E. paraphrase shortcut
    out["E_paraphrase"] = exp_paraphrase()

    path = "/home/runner/work/xuen/xuen/workspace/exp/praise_results.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
