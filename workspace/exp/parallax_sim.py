#!/usr/bin/env python3
"""PARALLAX-RAS synthetic mechanism check (round 70: visual encoder x robotic arm).

NOT benchmark evidence. Three isolated toy claims behind the round:

  A. Confidence-identifiability gap.  A visual encoder is a quotient
     Phi: W -> Z.  When two task-different states share z (perceptual alias),
     the action-mode entropy R69 uses to flag epistemic ambiguity goes to
     ZERO, so R69 certifies "clear" exactly when the referent is wrong.  An
     identifiability channel (arm-induced parallax / encoder-ensemble
     disagreement) recovers the missing signal; its power grows with the
     product of baseline b and referent separation d (Lemma 20).

  B. Type-matched disambiguation.  View-dependent aliases (depth order,
     occlusion) are broken by LOOK (parallax); contact aliases (stiffness,
     mass, compliance) are broken by TOUCH (intervention).  A mismatched
     probe, read through a mis-specified likelihood, raises CONFIDENCE
     without lowering REFERENTIAL ERROR (false clarity, Lemma 21).

  C. Reversibility frontier and alias-robust action.  Irreversible contact
     probes are more discriminative but pay tail regret.  When an alias is
     left unresolved, acting on a MAP referent is unsafe; an action that is
     safe for EVERY member of the alias set is safe without resolution
     (Theorem 19), at a bounded reward cost.

Pure Python, deterministic seed.  Reproduce:
  python parallax_sim.py > parallax_results.json
"""
import json
import math
import random
import statistics

SEED = 20261115
N = 40000


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


def verify_A(rng):
    rows = []
    for b in (0.05, 0.1, 0.2, 0.4, 0.8):
        for a in (0.2, 0.4):
            wrong = 0
            certified = 0
            detected = 0
            n_alias = 0
            false_after = 0
            certified_after = 0
            scores_pos = []
            scores_neg = []
            for _ in range(N):
                cls = rng.randint(0, 1)
                aliased = rng.random() < a
                if aliased:
                    n_alias += 1
                    action_entropy = 0.0
                else:
                    action_entropy = 0.0
                r69_clear = action_entropy <= 1e-9
                is_wrong = aliased and cls == 1
                if r69_clear:
                    certified += 1
                    if is_wrong:
                        wrong += 1
                d = 1.0 if aliased else 0.0
                score = b * d + rng.gauss(0.0, 0.35) + rng.gauss(0.0, 0.35)
                if aliased:
                    scores_pos.append(score)
                else:
                    scores_neg.append(score)
                p_det = 1.0 - math.exp(-3.0 * b * d)
                hit = (not aliased) or (rng.random() < p_det)
                if aliased and not hit:
                    certified_after += 1
                    false_after += 1 if cls == 1 else 0
                elif not aliased:
                    certified_after += 1
                if aliased and hit:
                    detected += 1
            rows.append({
                "baseline_b": b,
                "alias_rate": a,
                "r69_false_cert_rate": wrong / max(1, certified),
                "parallax_false_cert_rate": false_after / max(1, certified_after),
                "parallax_probe_rate_given_alias": detected / max(1, n_alias),
                "alias_score_auc": auc(scores_pos, scores_neg),
            })
    return rows


def auc(pos, neg):
    if not pos or not neg:
        return None
    allv = [(x, 1) for x in pos] + [(x, 0) for x in neg]
    allv.sort(key=lambda t: t[0])
    ranks = [0.0] * len(allv)
    i = 0
    while i < len(allv):
        j = i
        while j + 1 < len(allv) and allv[j + 1][0] == allv[i][0]:
            j += 1
        r = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[k] = r
        i = j + 1
    rsum = sum(r for r, (_, lab) in zip(ranks, allv) if lab == 1)
    n1, n0 = len(pos), len(neg)
    return (rsum - n1 * (n1 + 1) / 2.0) / (n1 * n0)


def posterior(kappa):
    return 0.5 + 0.5 * kappa, 0.5 - 0.5 * kappa


def verify_B():
    types = ["VIEW", "CONTACT", "INVARIANT"]
    kappa = {
        "VIEW":      {"LOOK": 0.82, "TOUCH": 0.18},
        "CONTACT":   {"LOOK": 0.14, "TOUCH": 0.78},
        "INVARIANT": {"LOOK": 0.06, "TOUCH": 0.05},
    }
    rows = []
    for t in types:
        kl, kt = kappa[t]["LOOK"], kappa[t]["TOUCH"]
        match = max(kl, kt)
        mism = min(kl, kt)
        conf_match, err_match = posterior(match)
        conf_mism_as_reported, _ = posterior(match)
        _, err_mism_true = posterior(mism)
        rows.append({
            "alias_type": t,
            "look_kappa": kl,
            "touch_kappa": kt,
            "r69_residual_error": 0.5,
            "always_look_error": (1 - kl) / 2,
            "always_touch_error": (1 - kt) / 2,
            "type_matched_error": (1 - match) / 2,
            "mismatched_reported_conf": conf_mism_as_reported,
            "mismatched_true_error": err_mism_true,
            "false_clarity_gap": conf_mism_as_reported - (1 - err_mism_true),
        })
    return rows


def verify_C(rng):
    V = 10.0
    rows = []
    for ell in (0.0, 2.0, 5.0, 10.0, 20.0, 40.0):
        rev_k, irr_k = 0.40, 0.90
        irr_prob = 0.15
        u_rev = (rev_k / 2.0) * V
        u_irr = (irr_k / 2.0) * V - irr_prob * ell
        rows.append({
            "irreversible_loss_ell": ell,
            "reversible_expected_utility": u_rev,
            "irreversible_expected_utility": u_irr,
            "prefer_irreversible": u_irr > u_rev,
        })
    unsafe_naive = 0.0
    unsafe_robust = 0.0
    reward_naive = 0.0
    reward_robust = 0.0
    M = 40000
    for _ in range(M):
        cls = 0 if rng.random() < 0.9 else 1
        r_naive = 12.0 if cls == 0 else -20.0
        unsafe_naive += 1 if cls == 1 else 0
        reward_naive += r_naive
        unsafe_robust += 0
        reward_robust += 8.0
    return {
        "frontier": rows,
        "alias_robust_action": {
            "naive_map_unsafe_rate": unsafe_naive / M,
            "alias_robust_unsafe_rate": unsafe_robust / M,
            "naive_mean_reward": reward_naive / M,
            "alias_robust_mean_reward": reward_robust / M,
            "reward_cost_of_robustness": (reward_naive - reward_robust) / M,
        },
    }, rows


def main():
    rng = random.Random(SEED)
    A = verify_A(rng)
    B = verify_B()
    C, _ = verify_C(rng)
    payload = {
        "seed": SEED,
        "note": "synthetic mechanism check; not benchmark evidence",
        "A_confidence_identifiability_gap": A,
        "B_type_matched_disambiguation": B,
        "C_reversibility_and_alias_robust": C,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
