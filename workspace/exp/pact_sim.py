"""Synthetic mechanism check for PACT (round 66: intent understanding x HRI).

NOT benchmark evidence, NOT a human-subject study. It only checks that four
proposed quantities are well-defined and behave as claimed on declared
generative models:

  A. Decision-relevant intent quotient (DRI)
     Intent entropy is high while decision uncertainty is low, so "resolve the
     intent" over-queries; the quotient over safety predicates is sufficient.

  B. Consent-gated / revocable prefix (RVC)
     Under open-loop commitment k, response latency is k*dt + tau_H. If tau_H
     has a heavy upper tail, a prefix certified with the mean reaction time is
     unsafe; a quantile (consent-gated) horizon restores the guarantee.

  C. Trust calibration monitor (TCM)
     "Maximize human trust" lowers supervision and raises residual-fault harm;
     honest reliability reporting raises supervision (cost) and lowers harm.
     This is a tradeoff, not a free lunch; it is reported as a Pareto table.

  D. Socially-aware attribution (SAA)
     Under an asymmetric loss (false blame of the human is costlier than
     self-blame), Bayes-optimal reporting reduces false-human-blame relative
     to 0-1 argmax at a small accuracy cost.

All numbers are from synthetic simulation and must not be read as robot or
human-factors evidence.
"""
import json
import os

import numpy as np

SEED = 17
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pact_results.json")


def sim_a(trials=800, seed=SEED):
    rng = np.random.default_rng(seed)
    M, C, A, J = 12, 3, 4, 6
    intent_class = np.repeat(np.arange(C), M // C).astype(int)
    p_psi = rng.uniform(0.05, 0.85, size=(C, A))
    p_psi[:, 0] = [0.02, 0.10, 0.80]          # action 0: decision threshold 0.05
    p_psi[:, 1] = [0.01, 0.02, 0.03]          # action 1: safe for every class
    # classes 0 and 2 are hard to tell apart, and straddle the safety threshold;
    # class 1 is behaviourally distinct. Within-class intents are equivalent
    # for the safety predicate but distinguishable in behaviour.
    q = np.array([[0.20, 0.80, 0.30, 0.70, 0.40, 0.60],
                  [0.80, 0.20, 0.70, 0.30, 0.60, 0.40],
                  [0.25, 0.75, 0.30, 0.65, 0.45, 0.55]])
    eta = rng.normal(scale=0.02, size=(M, J))  # within-class intent idio-syncrasy

    C_HARM, C_TASK = 20.0, 1.0
    ent_i, ent_c = [], []
    evpi = [[], []]
    wasted_query = [0, 0]
    false_confidence = 0
    full_pred, quot_pred = [[], []], [[], []]

    for _ in range(trials):
        c_true = rng.integers(C)
        i_true = rng.choice(np.flatnonzero(intent_class == c_true))
        n_obs = rng.integers(6, 15)
        x = rng.random((n_obs, J)) < np.clip(q[c_true] + eta[i_true], 0.01, 0.99)
        loglik = np.zeros(M)
        for i in range(M):
            rate = np.clip(q[intent_class[i]] + eta[i], 1e-3, 1 - 1e-3)
            loglik[i] = np.sum(x * np.log(rate) + (1 - x) * np.log(1 - rate))
        loglik -= loglik.max()
        post_i = np.exp(loglik)
        post_i /= post_i.sum()
        post_c = np.array([post_i[intent_class == c].sum() for c in range(C)])

        hi = -np.sum(post_i * np.log(post_i + 1e-12))
        hc = -np.sum(post_c * np.log(post_c + 1e-12))
        ent_i.append(hi)
        ent_c.append(hc)

        p_harm = [float(post_c @ p_psi[:, a]) for a in (0, 1)]
        v = []
        for a in (0, 1):
            loss_allow = p_harm[a] * C_HARM
            loss_deny = C_TASK
            loss_cur = min(loss_allow, loss_deny)
            loss_perfect = sum(post_c[c] * min(p_psi[c, a] * C_HARM, C_TASK)
                               for c in range(C))
            v.append(max(0.0, loss_cur - loss_perfect))
            if hi > 1.0 and v[-1] < 0.01:
                wasted_query[a] += 1
        evpi[0].append(v[0])
        evpi[1].append(v[1])
        if hi < 0.5 and v[0] > 0.05:
            false_confidence += 1

        for a in (0, 1):
            full_pred[a].append(p_harm[a])
            quot_pred[a].append(float(sum(post_c[c] * p_psi[c, a] for c in range(C))))

    ent_i, ent_c = np.asarray(ent_i), np.asarray(ent_c)
    evpi = [np.asarray(e) for e in evpi]
    full_pred = [np.asarray(p) for p in full_pred]
    quot_pred = [np.asarray(p) for p in quot_pred]

    # finite-sample calibration: same total samples, per-intent vs per-class
    n_per_intent = 10
    p_hat_i, p_hat_c, mse_i, mse_c = [], [], 0.0, 0.0
    for c in range(C):
        for i in np.flatnonzero(intent_class == c):
            s = rng.random(n_per_intent) < p_psi[c, 0]
            p_hat_i.append(s.mean())
        s_c = rng.random(n_per_intent * (M // C)) < p_psi[c, 0]
        p_hat_c.append(s_c.mean())
    for c in range(C):
        mse_c += (p_hat_c[c] - p_psi[c, 0]) ** 2 / C
        for i in np.flatnonzero(intent_class == c):
            mse_i += (p_hat_i[i] - p_psi[c, 0]) ** 2 / M

    return {
        "M_intents": M,
        "C_behaviour_classes": C,
        "mean_H_intent_nats": float(ent_i.mean()),
        "mean_H_quotient_nats": float(ent_c.mean()),
        "log_M": float(np.log(M)),
        "action_0_mean_EVPI": float(evpi[0].mean()),
        "action_1_mean_EVPI": float(evpi[1].mean()),
        "wasted_clarification_rate_action0": float(wasted_query[0] / trials),
        "wasted_clarification_rate_action1": float(wasted_query[1] / trials),
        "false_confidence_rate": float(false_confidence / trials),
        "corr_H_intent_EVPI_action0": float(np.corrcoef(ent_i, evpi[0])[0, 1]),
        "full_vs_quotient_decision_agreement":
            [float(np.mean(np.abs(full_pred[a] - quot_pred[a]) < 1e-9)) for a in (0, 1)],
        "calibration_mse_per_intent": float(mse_i),
        "calibration_mse_per_class": float(mse_c),
        "calibration_mse_ratio": float(mse_c / max(mse_i, 1e-12)),
    }


def sim_b(episodes=40000, seed=SEED + 1):
    rng = np.random.default_rng(seed)
    dt, v, d0 = 0.10, 0.30, 0.30
    t_contact = d0 / v
    tau = np.clip(rng.normal(0.35, 0.08, episodes), 0.05, None)
    p_threat = 0.15
    ks = [1, 2, 3, 4, 5, 6, 8, 12, 16]
    curve = []
    for k in ks:
        # worst-case open-loop latency = full committed prefix + human reaction
        response = k * dt + tau
        harm_cond = float(np.mean(response > t_contact))
        curve.append({
            "k": k,
            "latency_mean_s": float(k * dt + tau.mean()),
            "harm_given_threat": harm_cond,
            "harm_rate": p_threat * harm_cond,
        })

    # certification using mean vs 90th-percentile reaction time
    tau_mean = float(tau.mean())
    tau_q90 = float(np.quantile(tau, 0.90))
    k_mean = int(np.floor((t_contact - tau_mean) / dt))
    k_q90 = int(np.floor((t_contact - tau_q90) / dt))

    def rate_at(k):
        return p_threat * float(np.mean(k * dt + tau > t_contact))

    return {
        "t_contact_s": t_contact,
        "tau_mean_s": tau_mean,
        "tau_q90_s": tau_q90,
        "k_from_mean_reaction": k_mean,
        "k_from_q90_reaction": k_q90,
        "harm_at_mean_horizon": rate_at(max(k_mean, 1)),
        "harm_at_q90_horizon": rate_at(max(k_q90, 1)),
        "harm_fixed_k16": rate_at(16),
        "relative_harm_reduction_q90_vs_k16": float(
            1.0 - rate_at(max(k_q90, 1)) / max(rate_at(16), 1e-12)),
        "curve": curve,
    }


def sim_c(seed=SEED + 2):
    r_true, p_fault, residual = 0.70, 0.30, 0.30
    rows = []
    for name, target in [("overclaim", 0.98), ("calibrated", r_true), ("underclaim", 0.40)]:
        # supervision falls as trust rises
        m = 1.0 / (1.0 + np.exp(-6.0 * (0.8 - target)))
        harm = p_fault * residual * (1.0 - m)
        unnecessary_override = m * (1.0 - p_fault * residual)
        rows.append({
            "policy": name,
            "reported_trust": target,
            "trust_error_abs": abs(target - r_true),
            "monitoring_prob": float(m),
            "harm_rate": float(harm),
            "unnecessary_override_rate": float(unnecessary_override),
        })
    return {
        "true_reliability": r_true,
        "fault_rate": p_fault,
        "residual_fault_given_fault": residual,
        "rows": rows,
    }


def sim_d(trials=30000, seed=SEED + 3):
    rng = np.random.default_rng(seed)
    names = ["H_robot", "H_human_intent", "H_human_slip", "H_comm", "H_env"]
    H = len(names)
    true = rng.integers(H, size=trials)
    logits = np.eye(H)[true] * 2.2 + rng.normal(scale=1.0, size=(trials, H))
    logits -= logits.max(axis=1, keepdims=True)
    post = np.exp(logits)
    post /= post.sum(axis=1, keepdims=True)

    human_idx = [1, 2]

    def loss_matrix(ratio):
        # L[true, reported]; falsely blaming a human costs `ratio` times self-blame
        L = np.ones((H, H))
        np.fill_diagonal(L, 0.0)
        for t in range(H):
            for r in human_idx:
                if t != r and t not in human_idx:
                    L[t, r] = ratio
        for t in human_idx:
            for r in range(H):
                if r not in human_idx:
                    L[t, r] = 1.0
        return L

    def stats(pred):
        acc = float(np.mean(pred == true))
        false_blame = float(np.mean(np.isin(pred, human_idx) & ~np.isin(true, human_idx)))
        false_self = float(np.mean(~np.isin(pred, human_idx) & np.isin(true, human_idx)))
        return acc, false_blame, false_self

    pred01 = post.argmax(axis=1)
    acc01, fb01, fs01 = stats(pred01)
    out = {
        "hypotheses": names,
        "argmax_accuracy": acc01,
        "argmax_false_human_blame": fb01,
        "argmax_false_self_blame": fs01,
        "by_loss_ratio": [],
    }
    for ratio in (1.5, 2.0, 3.0, 5.0):
        L = loss_matrix(ratio)
        # expected loss under posterior is sum_t p(t) L[t,r] = (L.T @ post)[r]
        pred = np.array([int(np.argmin(L.T @ post[i])) for i in range(trials)])
        acc, fb, fs = stats(pred)
        out["by_loss_ratio"].append({
            "loss_ratio": ratio,
            "accuracy": acc,
            "false_human_blame": fb,
            "false_self_blame": fs,
            "false_blame_relative_reduction": float(1.0 - fb / max(fb01, 1e-12)),
        })
    return out


def main():
    res = {
        "meta": {
            "purpose": "synthetic mechanism check, NOT benchmark or human-subject evidence",
            "seed": SEED,
        },
        "A_decision_relevant_intent": sim_a(),
        "B_consent_gated_prefix": sim_b(),
        "C_trust_calibration": sim_c(),
        "D_social_attribution": sim_d(),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
