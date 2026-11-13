#!/usr/bin/env python3
"""Round-3 synthetic mechanism check (stdlib only).

NOT robot evidence. Two separable claims:

A. Causal attribution (UIP-17 CAD) vs naive temporal-difference (v2 detector):
   when some 1->0 subgoal flips are *self-caused* (policy overshoot / model
   error), a detector that flags every flip as external has precision
   P(external | flagged) = 1 - pi_self.  Conditioning on an action-consistency
   residual raises precision at a measurable recall cost.

B. Ablation design (UIP-19 ABL): with genuine interactions, one-factor-at-a-time
   (OAT) and leave-one-out-from-all-on (LOO) give context-dependent effects and
   can mis-rank components.  A full 2^k factorial recovers main effects and
   interactions; OAT cannot even represent them.

All numbers are generated here and should be read as a methodology sanity check.
"""
import json
import math
import random

OUT = "/home/runner/work/xuen/xuen/workspace/tmp/r3_causal_ablation_sim.json"
SEED = 20261113


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


# ---------------------------------------------------------------- A: attribution
def part_a(rng, n=400000):
    # residual r: self-caused flips have small |r|, external retractions large r
    mu_self, sd_self = 0.0, 1.0
    mu_ext, sd_ext = 3.0, 1.0
    tau = 1.5  # CAD threshold on residual r

    rows = []
    for pi_self in (0.2, 0.4, 0.6, 0.8):
        tp = fp = fn = tn = 0
        for _ in range(n):
            self_caused = rng.random() < pi_self
            r = rng.gauss(mu_self if self_caused else mu_ext,
                          sd_self if self_caused else sd_ext)
            flagged = r > tau  # CAD: flag as external only if evidence is large
            if flagged and not self_caused:
                tp += 1
            elif flagged and self_caused:
                fp += 1
            elif (not flagged) and (not self_caused):
                fn += 1
            else:
                tn += 1
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        fpr = fp / max(fp + tn, 1)
        rows.append({
            "pi_self": pi_self,
            "td_precision": round(1.0 - pi_self, 4),
            "cad_precision": round(prec, 4),
            "cad_recall_external": round(rec, 4),
            "cad_false_positive_self": round(fpr, 4),
        })
    return {"residual_model": {"self": [mu_self, sd_self],
                               "external": [mu_ext, sd_ext],
                               "threshold": tau},
            "rows": rows}


# ---------------------------------------------------------------- B: ablation
COMPONENTS = ["CGT", "CAD", "RTH", "CFA", "MSGR"]
BETA = {"CGT": 4.0, "CAD": 3.0, "RTH": 1.0, "CFA": 5.0, "MSGR": 0.0}
INTER = {("CAD", "RTH"): 6.0, ("CGT", "CFA"): -3.0, ("RTH", "CFA"): 2.0}


def true_y(x):
    y = 1.0
    for c in COMPONENTS:
        y += BETA[c] * x[c]
    for (a, b), v in INTER.items():
        y += v * x[a] * x[b]
    return y


def all_on():
    return {c: 1 for c in COMPONENTS}


def all_off():
    return {c: 0 for c in COMPONENTS}


def part_b(rng, reps=200, sigma=1.0):
    # unbiased full-factorial main effects via balanced contrasts
    main = {c: 0.0 for c in COMPONENTS}
    inter = {f"{a}*{b}": 0.0 for (a, b) in INTER}
    cells = []
    for mask in range(1 << len(COMPONENTS)):
        x = {c: (mask >> i) & 1 for i, c in enumerate(COMPONENTS)}
        cells.append(x)
    samples = []
    for x in cells:
        for _ in range(reps):
            samples.append((x, true_y(x) + rng.gauss(0.0, sigma)))
    # main effect: mean(on) - mean(off), orthogonal in full factorial
    for c in COMPONENTS:
        on = [y for x, y in samples if x[c] == 1]
        off = [y for x, y in samples if x[c] == 0]
        main[c] = sum(on) / len(on) - sum(off) / len(off)
    # two-way interaction contrast
    for (a, b) in INTER:
        v = 0.0
        cnt = 0
        for x, y in samples:
            sign = (1 if x[a] == 1 else -1) * (1 if x[b] == 1 else -1)
            v += sign * y
            cnt += 1
        inter[f"{a}*{b}"] = v / cnt
    # OAT from all-off: effect of turning one on
    oat_off = {}
    for c in COMPONENTS:
        x = all_off(); x[c] = 1
        oat_off[c] = true_y(x) - true_y(all_off())
    # LOO from all-on: effect of turning one off
    loo_on = {}
    for c in COMPONENTS:
        x = all_on(); x[c] = 0
        loo_on[c] = true_y(all_on()) - true_y(x)
    total = true_y(all_on()) - true_y(all_off())
    return {
        "beta_true": BETA,
        "interaction_true": {f"{a}*{b}": v for (a, b), v in INTER.items()},
        "factorial_main_est": {k: round(v, 3) for k, v in main.items()},
        "factorial_inter_est": {k: round(v, 3) for k, v in inter.items()},
        "oat_from_off": {k: round(v, 3) for k, v in oat_off.items()},
        "loo_from_on": {k: round(v, 3) for k, v in loo_on.items()},
        "total_all_on_vs_off": round(total, 3),
        "sum_oat": round(sum(oat_off.values()), 3),
        "sum_loo": round(sum(loo_on.values()), 3),
        "sum_main": round(sum(main.values()), 3),
        "sum_inter": round(sum(inter.values()), 3),
        "reps_per_cell": reps,
        "sigma": sigma,
    }


def main():
    rng = random.Random(SEED)
    out = {"seed": SEED,
           "note": "synthetic mechanism check; not robot evidence",
           "A_attribution": part_a(random.Random(SEED + 1)),
           "B_ablation": part_b(random.Random(SEED + 2))}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
