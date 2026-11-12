"""Toy calibration for the non-compensatory ethics-review shield.

This is NOT a robot experiment.  It is a small synthetic stratified CMDP used
to check that the proposed selection rules are computable and to illustrate the
difference between average-optimal, shield-only, and shield+worst-group
selection.  Run with:  PYTHONPATH=.pylibs python exp/ethics_review_sim.py
"""
import json
import numpy as np

rng = np.random.default_rng(7)

# (difficulty, vulnerable) for 8 strata
STRATA = [(0.15, 0), (0.35, 1), (0.35, 0), (0.55, 1),
          (0.55, 0), (0.75, 1), (0.80, 0), (0.95, 1)]
NAMES = ['easy_normal', 'easy_vuln', 'med_normal', 'med_vuln',
         'hard_normal', 'hard_vuln', 'veryhard_normal', 'veryhard_vuln']
PUBLIC_W = np.array([0.58, 0.02, 0.25, 0.02, 0.10, 0.01, 0.01, 0.01])
HIDDEN_W = np.array([0.03, 0.12, 0.05, 0.15, 0.08, 0.18, 0.09, 0.30])
PUBLIC_W = PUBLIC_W / PUBLIC_W.sum()
HIDDEN_W = HIDDEN_W / HIDDEN_W.sum()


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def simulate_policy(aggression, competence, noise=0.0):
    p, h, ss = [], [], []
    for d, v in STRATA:
        pi = sigmoid(0.8 + 1.1 * competence - 1.7 * d
                     + 1.8 * aggression * (1 - v) - 0.5 * aggression * v)
        hi = sigmoid(-6.5 + 2.2 * aggression * (0.05 + 0.95 * v)
                     + 1.4 * d - 0.5 * competence)
        si = 100.0 * (0.30 + 0.45 * pi + 0.20 * sigmoid(competence))
        if noise:
            pi = np.clip(pi + rng.normal(0, noise), 0, 1)
            hi = np.clip(hi + rng.normal(0, noise / 3), 0, 1)
        p.append(pi); h.append(hi); ss.append(si)
    return np.array(p), np.array(h), np.array(ss)


def shield(p, h, ss, alpha=0.02, cost=0.55):
    """Cap harm at alpha; pay a success/step-score cost for the reduction."""
    h_new = np.minimum(h, alpha)
    reduction = np.maximum(h - alpha, 0)
    p_new = np.clip(p - cost * reduction, 0, 1)
    ss_new = np.clip(ss - 60.0 * reduction, 0, 100)
    return p_new, h_new, ss_new


def expected_score(p, h, ss, w):
    return float(np.sum(w * ((1 - h) * (100.0 * p + ss))))


def worst_group_success(p, h):
    return float(np.min((1 - h) * p))


def eval_public(aggression, competence):
    p, h, ss = simulate_policy(aggression, competence, noise=0.04)
    return p, h, ss


N = 500
CANDIDATES = [(rng.beta(2.5, 2.0), rng.normal(0, 1)) for _ in range(N)]


def select_avg():
    return max(range(N), key=lambda i: expected_score(
        *eval_public(*CANDIDATES[i]), PUBLIC_W))


def select_lagrangian(lam):
    def objective(i):
        p, h, ss = eval_public(*CANDIDATES[i])
        return expected_score(p, h, ss, PUBLIC_W) - lam * float(np.sum(PUBLIC_W * h))
    return max(range(N), key=objective)


def select_shield_avg(alpha=0.02):
    def value(i):
        p, h, ss = eval_public(*CANDIDATES[i])
        p, h, ss = shield(p, h, ss, alpha)
        return expected_score(p, h, ss, PUBLIC_W)
    return max(range(N), key=value)


def select_shield_justice(alpha=0.02, gamma=0.30):
    feasible = []
    for i in range(N):
        p, h, ss = eval_public(*CANDIDATES[i])
        p, h, ss = shield(p, h, ss, alpha)
        succ = (1 - h) * p
        n = 80
        lcb = succ - 1.64 * np.sqrt(np.maximum(succ * (1 - succ), 1e-6) / n)
        if lcb.min() >= gamma:
            feasible.append((expected_score(p, h, ss, PUBLIC_W), i))
    return max(feasible)[1] if feasible else select_shield_avg(alpha)


SELECTORS = {
    'avg_public': select_avg,
    'lagrangian_lam10': lambda: select_lagrangian(10.0),
    'shield_only': select_shield_avg,
    'shield_justice': select_shield_justice,
}


def evaluate(index, use_shield):
    a, c = CANDIDATES[index]
    p, h, ss = simulate_policy(a, c)
    if use_shield:
        p, h, ss = shield(p, h, ss, 0.02)
    return {
        'public_score': round(expected_score(p, h, ss, PUBLIC_W), 2),
        'hidden_score': round(expected_score(p, h, ss, HIDDEN_W), 2),
        'hidden_success': round(float(np.sum(HIDDEN_W * (1 - h) * p)), 3),
        'hidden_worst_stratum': round(worst_group_success(p, h), 3),
        'hidden_harm_rate': round(float(np.sum(HIDDEN_W * h)), 4),
        'aggressiveness': round(float(a), 3),
        'per_stratum_success': {n: round(float(x), 3)
                                for n, x in zip(NAMES, (1 - h) * p)},
    }


def main():
    out = {}
    for name, fn in SELECTORS.items():
        idx = fn()
        use_shield = name.startswith('shield')
        out[name] = evaluate(idx, use_shield)
    out['_meta'] = {
        'kind': 'synthetic toy calibration; not robot data',
        'n_candidates': N,
        'public_weights': PUBLIC_W.round(4).tolist(),
        'hidden_weights': HIDDEN_W.round(4).tolist(),
        'strata': NAMES,
        'seed': 7,
    }
    with open('exp/ethics_review_results.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
