"""Synthetic mechanism check for CERT-PROBE (round 16).

NOT benchmark evidence. Isolates one question:
when a frozen VLA completes sub-goals but the world changes underneath it
(official UniBot-V1 generalization variants move / undo objects mid-episode),
does an explicit predicate-state belief plus active physical certification
probes raise success and step score over one-shot execution, and at what
time cost?

Generative model (declared, not fit):
  - a task is a set of m weighted predicates (weights copied from the
    official score_steps of the corresponding UniBot-V1 tasks);
  - predicate truth is a hidden 2-state variable per predicate;
  - ATTEMPT (VLA action chunk) costs TA seconds, sets truth=True with
    probability c, and returns a weak hint with accuracy q (this is where
    round-15 self-supervised residuals would enter);
  - PROBE (active physical certification) costs TP seconds and reports
    truth with accuracy d; LOOK (passive re-observation) costs TL seconds
    and reports truth with accuracy dL;
  - any predicate whose truth is True can be invalidated by the human with
    per-second hazard lambda; the robot only learns this through evidence;
  - terminal score = sum of weights of predicates whose truth is True at the
    end of the time budget; success = all predicates True.

Policy family:
  - VLA-only: one attempt per predicate in order, trusts its own action,
    never re-checks (the round-10..15 default open-loop behaviour);
  - VLA-retry: up to R attempts per predicate, no belief, no probes;
  - LOOK: same value-DP as CERT but the only evidence action is passive
    re-observation with accuracy dL;
  - CERT: same value-DP, evidence action is an active probe with accuracy d;
  - ORACLE: truth is known, attempts only.

Value model: per-predicate POMDP over belief b and remaining wall-clock t,
value = expected terminal weight. DP grid: belief x time. Global allocation
is greedy on marginal score per second (documented approximation).
"""
import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))

TASKS = {
    "two_step": [50, 50],
    "three_step": [30, 30, 40],
    "four_step": [25, 25, 25, 25],
    "five_step": [20, 20, 20, 20, 20],
}

DT = 1.0
T_HORIZON = 60.0
BELIEF_GRID = [i / 50.0 for i in range(1, 50)]
TA = 8.0
TP = 2.0
TL = 1.5
Q_WEAK = 0.6


def hazard_keep(lam, dt):
    return (1.0 - lam) ** dt


def belief_after_none(b, lam, dt):
    return b * hazard_keep(lam, dt)


def posterior_hint(p_true, hint, q):
    """Bayesian update of P(state true) from a weak hint with accuracy q."""
    if hint:
        num = p_true * q
        den = num + (1.0 - p_true) * (1.0 - q)
    else:
        num = p_true * (1.0 - q)
        den = num + (1.0 - p_true) * q
    if den <= 1e-12:
        return p_true
    return min(1.0, max(0.0, num / den))


def belief_after_evidence(b, report, d):
    if report:
        num = d * b
    else:
        num = (1.0 - d) * b
    den = num + ((1.0 - d) * b if report else d * (1.0 - b))
    if den <= 0:
        return b
    return num / den


def build_dp(lam, c, d, dt_evidence, cost_evidence):
    """Per-predicate value DP over (belief, remaining time).

    V[b, t] = expected terminal weight for one predicate of unit weight.
    Actions: NONE (cost 0, hazard only), ATTEMPT (cost TA), EVIDENCE
    (cost dt_evidence, accuracy d). Terminal V[b, 0] = b.
    """
    nb = len(BELIEF_GRID)
    nt = int(T_HORIZON / DT) + 1
    V = [[0.0] * nt for _ in range(nb)]
    pol = [[None] * nt for _ in range(nb)]
    for bi in range(nb):
        V[bi][0] = BELIEF_GRID[bi]

    def interp(b, t_idx):
        if b <= 0.0:
            return V[0][t_idx]
        if b >= 1.0:
            return V[nb - 1][t_idx]
        pos = b * 50.0 - 1.0
        lo = int(math.floor(pos))
        hi = min(nb - 1, lo + 1)
        frac = pos - lo
        return V[lo][t_idx] * (1.0 - frac) + V[hi][t_idx] * frac

    for ti in range(1, nt):
        t = ti * DT
        for bi in range(nb):
            b = BELIEF_GRID[bi]
            b_none = belief_after_none(b, lam, DT)
            q_none = interp(b_none, ti - 1)

            q_att = 0.0
            ti_att = ti - int(TA / DT)
            if ti_att >= 0:
                p_true_after = (c + (1.0 - c) * b) * hazard_keep(lam, TA)
                w_hint = Q_WEAK * p_true_after + (1.0 - Q_WEAK) * (1.0 - p_true_after)
                b_hi = posterior_hint(p_true_after, True, Q_WEAK)
                b_lo = posterior_hint(p_true_after, False, Q_WEAK)
                q_att = w_hint * interp(b_hi, ti_att) + (1.0 - w_hint) * interp(b_lo, ti_att)
            else:
                q_att = -1.0

            ti_ev = ti - int(cost_evidence / DT)
            q_ev = 0.0
            if ti_ev >= 0:
                b_hi = min(1.0, d + (1.0 - d) * b)
                b_lo = max(0.0, (1.0 - d) * b)
                w_rep = d * b + (1.0 - d) * (1.0 - b)
                q_ev = w_rep * interp(b_hi, ti_ev) + (1.0 - w_rep) * interp(b_lo, ti_ev)

            cands = [(q_none, "NONE"), (q_att, "ATTEMPT")]
            if ti_ev >= 0:
                cands.append((q_ev, "EVIDENCE"))
            best_val, best_act = max(cands, key=lambda x: x[0])
            V[bi][ti] = best_val
            pol[bi][ti] = best_act
    return V, pol, interp


def simulate(policy, task_name, lam, c, d, d_look, episodes, rng, dp=None):
    weights = TASKS[task_name]
    m = len(weights)
    succ, scores, times, probes, attempts, false_belief = [], [], [], [], [], []
    if policy == "ORACLE":
        dp = None
    for _ in range(episodes):
        truth = [False] * m
        belief = [0.5] * m
        t = 0.0
        n_probe = 0
        n_att = 0
        n_tried = [0] * m
        while t < T_HORIZON - 1e-9:
            if policy == "VLA-only":
                idx = None
                for j in range(m):
                    if n_tried[j] == 0:
                        idx = j
                        break
                if idx is None:
                    break
                n_tried[idx] += 1
                n_att += 1
                truth[idx] = truth[idx] or (rng.random() < c)
                t += TA
            elif policy == "VLA-retry":
                idx = None
                for j in range(m):
                    if n_tried[j] < 3:
                        idx = j
                        break
                if idx is None:
                    break
                n_tried[idx] += 1
                n_att += 1
                truth[idx] = truth[idx] or (rng.random() < c)
                t += TA
            elif policy == "ORACLE":
                idx = None
                for j in range(m):
                    if not truth[j]:
                        idx = j
                        break
                if idx is None:
                    break
                n_att += 1
                truth[idx] = truth[idx] or (rng.random() < c)
                t += TA
            else:
                best = None
                for j in range(m):
                    ti = int((T_HORIZON - t) / DT)
                    ti = max(0, min(len(dp[0][0]) - 1, ti))
                    bi = int(min(len(dp[0]) - 1, max(0, round(belief[j] * 50.0) - 1)))
                    act = dp[1][bi][ti]
                    if act == "NONE":
                        continue
                    v_now = dp[2](belief[j], ti)
                    if act == "ATTEMPT":
                        cost = TA
                    else:
                        cost = TP if policy == "CERT" else TL
                    if policy == "LOOK" and act == "EVIDENCE":
                        d_eff = d_look
                    elif policy == "CERT" and act == "EVIDENCE":
                        d_eff = d
                    else:
                        d_eff = d
                    ti2 = ti - int(cost / DT)
                    if ti2 < 0:
                        continue
                    if act == "ATTEMPT":
                        p_true_after = (c + (1.0 - c) * belief[j]) * hazard_keep(lam, TA)
                        b_hi = posterior_hint(p_true_after, True, Q_WEAK)
                        b_lo = posterior_hint(p_true_after, False, Q_WEAK)
                        w_hint = Q_WEAK * p_true_after + (1.0 - Q_WEAK) * (1.0 - p_true_after)
                        qv = w_hint * dp[2](b_hi, ti2) + (1.0 - w_hint) * dp[2](b_lo, ti2)
                    else:
                        b_hi = min(1.0, d_eff + (1.0 - d_eff) * belief[j])
                        b_lo = max(0.0, (1.0 - d_eff) * belief[j])
                        w_rep = d_eff * belief[j] + (1.0 - d_eff) * (1.0 - belief[j])
                        qv = w_rep * dp[2](b_hi, ti2) + (1.0 - w_rep) * dp[2](b_lo, ti2)
                    gain = (qv - v_now) / cost
                    if best is None or gain > best[0]:
                        best = (gain, j, act, cost)
                if best is None:
                    t = T_HORIZON
                    break
                _, j, act, cost = best
                if act == "ATTEMPT":
                    n_att += 1
                    truth[j] = truth[j] or (rng.random() < c)
                    p_true_after = (c + (1.0 - c) * belief[j]) * hazard_keep(lam, TA)
                    p_hint_true = Q_WEAK * p_true_after + (1.0 - Q_WEAK) * (1.0 - p_true_after)
                    hint = rng.random() < p_hint_true
                    belief[j] = posterior_hint(p_true_after, hint, Q_WEAK)
                else:
                    n_probe += 1
                    d_eff = d if policy == "CERT" else d_look
                    p_rep_true = d_eff * belief[j] + (1.0 - d_eff) * (1.0 - belief[j])
                    report = rng.random() < p_rep_true
                    belief[j] = belief_after_evidence(belief[j], report, d_eff)
                t += cost
            keep = hazard_keep(lam, min(1.0, T_HORIZON - t))
            for j in range(m):
                truth[j] = truth[j] and (rng.random() < keep)
                belief[j] = belief[j] * keep
        score = sum(w for w, tr in zip(weights, truth) if tr)
        succ.append(1.0 if all(truth) else 0.0)
        scores.append(score)
        times.append(min(t, T_HORIZON))
        probes.append(n_probe)
        attempts.append(n_att)
        false_belief.append(sum(1 for b, tr in zip(belief, truth) if b >= 0.5 and not tr))
    return {
        "success": sum(succ) / len(succ),
        "step_score": sum(scores) / len(scores),
        "time": sum(times) / len(times),
        "probes": sum(probes) / len(probes),
        "attempts": sum(attempts) / len(attempts),
        "false_belief": sum(false_belief) / len(false_belief),
    }


def run(regimes, episodes, seed):
    rng = random.Random(seed)
    rows = []
    for lam, c in regimes:
        dp_cert = build_dp(lam, c, 0.9, TP, TP)
        dp_look = build_dp(lam, c, 0.55, TL, TL)
        for task_name in TASKS:
            for policy in ["VLA-only", "VLA-retry", "LOOK", "CERT", "ORACLE"]:
                if policy == "CERT":
                    dp = dp_cert
                elif policy == "LOOK":
                    dp = dp_look
                else:
                    dp = None
                res = simulate(policy, task_name, lam, c, 0.9, 0.55, episodes, rng, dp)
                res.update({"policy": policy, "task": task_name, "lambda": lam, "c": c})
                rows.append(res)
    return rows


def main():
    seed = 20261104
    episodes = 3000
    regimes = [(0.0, 0.4), (0.0, 0.6), (0.02, 0.4), (0.02, 0.6), (0.06, 0.4), (0.06, 0.6)]
    rows = run(regimes, episodes, seed)
    out = {
        "seed": seed,
        "episodes_per_cell": episodes,
        "horizon_sec": T_HORIZON,
        "TA": TA,
        "TP": TP,
        "TL": TL,
        "Q_WEAK": Q_WEAK,
        "regimes": regimes,
        "rows": rows,
    }
    path = os.path.join(HERE, "cert_probe_results.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)

    print("lam   c   task       policy      succ   step   time   probes  attempts")
    for lam, c in regimes:
        for task_name in TASKS:
            for policy in ["VLA-only", "VLA-retry", "LOOK", "CERT", "ORACLE"]:
                r = next(x for x in rows if x["policy"] == policy and x["task"] == task_name
                         and x["lambda"] == lam and x["c"] == c)
                print("{:.2f}  {:.1f}  {:9s}  {:9s}  {:.3f}  {:5.1f}  {:5.1f}  {:5.2f}  {:5.2f}".format(
                    lam, c, task_name, policy, r["success"], r["step_score"], r["time"], r["probes"], r["attempts"]))
    print("saved", path)


if __name__ == "__main__":
    main()
