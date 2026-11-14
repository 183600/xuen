"""Synthetic mechanism check for SHARED-GAUGE-RAS (round 73).

NOT benchmark evidence. Each part isolates one causal claim of the proposal.
Stdlib only; seeded; numbers are reproduced by `python shared_sim.py`.

A. Trust is non-monotone: team loss is minimized near calibrated trust
   tau ~= R_r, not at tau = 1. Over-trust makes the human a missing backup;
   guardian mode (lambda_floor rises with over-trust) recovers part of the loss.
B. Authority is subtask-level: a weighted-sum arbiter that uses average
   competence grants the robot a critical subtask it is invalid on; a
   non-compensatory competence veto removes critical failures at small cost.
   Authority ambiguity H[alpha] is itself a risk source.
C. Takeover is a real-time deadline: fixed speed violates the safety envelope
   when v * T_take > margin; a takeover-aware speed limit (P99 latency) clears
   violations at a throughput cost.
D. Authority chattering: naive noisy argmax switches constantly; hysteresis
   + dwell time cuts switches with negligible utility loss.
E. Transparency has an optimal dose: calibration gain is concave, workload
   cost convex, so "show everything" is worse than the finite optimum.
"""
import json
import math
import os
import random
import statistics

SEED = 20261114
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared_results.json")


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


# ---------------------------------------------------------------- Part A
def p_intervene(tau, r_true, complacency=0.8):
    """Human intervention prob: falls with trust, attention falls with over-trust."""
    base = 0.95 - 0.85 * tau * tau
    over = max(0.0, tau - r_true) / max(1e-9, 1.0 - r_true)
    attn = 1.0 - complacency * over
    return clamp(base * (0.5 + 0.5 * attn), 0.02, 0.98)


def robot_fail_prob(regime, lam):
    f_base = 0.03 if regime == "normal" else 0.55
    return clamp(f_base / (1.0 + 2.0 * (lam - 1.0)), 0.0, 1.0)


def part_a(n=60000):
    rng = random.Random(SEED)
    R_TRUE = 0.92
    C_FAIL = 100.0
    C_INT = 1.0
    C_SLOW = 2.0
    C_UNNEC = 1.5
    C_DISUSE = 20.0
    C_COMPL = 20.0
    H_ERR = 0.12          # human manual error under an unnecessary takeover
    p_hard = 0.15
    guardian_beta = 5.0
    taus = [round(0.30 + 0.05 * i, 2) for i in range(15)]

    rows = []
    for tau in taus:
        for mode in ("naive", "guardian"):
            fails = 0
            loss_sum = 0.0
            ints = 0
            lam_sum = 0.0
            n_ep = n // len(taus)
            for _ in range(n_ep):
                hard = rng.random() < p_hard
                lam = 1.0
                if mode == "guardian":
                    lam = 1.0 + guardian_beta * max(0.0, tau - R_TRUE)
                f = robot_fail_prob("hard" if hard else "normal", lam)
                rfail = rng.random() < f
                pint = p_intervene(tau, R_TRUE)
                human_tries = rng.random() < pint
                fail = False
                if human_tries:
                    ints += 1
                    over = max(0.0, tau - R_TRUE) / max(1e-9, 1.0 - R_TRUE)
                    p_succ = clamp(0.9 - 0.6 * over, 0.2, 0.9)  # out-of-loop penalty
                    if rfail:
                        fail = not (rng.random() < p_succ)
                    else:
                        fail = rng.random() < H_ERR       # unnecessary takeover hurts
                elif rfail:
                    fail = True
                if fail:
                    fails += 1
                    loss_sum += C_FAIL
                loss_sum += C_INT * pint + C_SLOW * (lam - 1.0)
                if human_tries and not rfail:
                    loss_sum += C_UNNEC
                loss_sum += C_DISUSE * max(0.0, R_TRUE - tau)
                loss_sum += C_COMPL * max(0.0, tau - R_TRUE)
                lam_sum += lam
            rows.append({
                "tau": tau, "mode": mode, "n": n_ep,
                "team_failure": fails / n_ep,
                "expected_loss": loss_sum / n_ep,
                "mean_intervention": ints / n_ep,
                "mean_lambda": lam_sum / n_ep,
            })
    naive = [r for r in rows if r["mode"] == "naive"]
    best = min(naive, key=lambda r: r["expected_loss"])
    trust_max = next(r for r in naive if abs(r["tau"] - 1.0) < 1e-9)
    over = next(r for r in naive if abs(r["tau"] - 0.95) < 1e-9)
    over_g = next(r for r in rows if r["mode"] == "guardian" and abs(r["tau"] - 0.95) < 1e-9)
    return {
        "R_true": R_TRUE, "p_hard": p_hard,
        "opt_tau_by_loss": best["tau"],
        "opt_loss": round(best["expected_loss"], 4),
        "trust_max_loss": round(trust_max["expected_loss"], 4),
        "loss_increase_at_tau1": round(
            (trust_max["expected_loss"] - best["expected_loss"]) / best["expected_loss"], 4),
        "overtrust": {
            "tau": 0.95,
            "naive_failure": over["team_failure"],
            "guardian_failure": over_g["team_failure"],
            "relative_failure_drop": round(
                (over["team_failure"] - over_g["team_failure"]) / over["team_failure"], 4),
            "naive_loss": round(over["expected_loss"], 4),
            "guardian_loss": round(over_g["expected_loss"], 4),
            "guardian_slowdown": round(over_g["mean_lambda"] - 1.0, 4),
        },
        "curve": [{k: round(v, 4) if isinstance(v, float) else v for k, v in r.items()}
                  for r in rows],
    }


# ---------------------------------------------------------------- Part B
def part_b(n=60000):
    rng = random.Random(SEED + 1)
    # robot: strong on ordinary, invalid on a critical subtask; human opposite-ish
    C = {
        "critical": {"robot": 0.20, "human": 0.80},
        "ordinary": {"robot": 0.90, "human": 0.50},
    }
    p_crit = 0.30
    n_ep = n
    stats = {"weighted": {"crit_fail": 0, "all_fail": 0, "crit": 0},
             "veto": {"crit_fail": 0, "all_fail": 0, "crit": 0}}
    for _ in range(n_ep):
        crit = rng.random() < p_crit
        task = "critical" if crit else "ordinary"
        for mode in ("weighted", "veto"):
            if mode == "weighted":
                # average competence over task mix -> robot looks competent
                avg_r = p_crit * C["critical"]["robot"] + (1 - p_crit) * C["ordinary"]["robot"]
                avg_h = p_crit * C["critical"]["human"] + (1 - p_crit) * C["ordinary"]["human"]
                holder = "robot" if avg_r >= avg_h else "human"
            else:
                # subtask competence veto: never assign an invalid holder
                holder = "robot" if C[task]["robot"] >= C[task]["human"] else "human"
            ok = rng.random() < C[task][holder]
            stats[mode]["all_fail"] += (not ok)
            if crit:
                stats[mode]["crit"] += 1
                stats[mode]["crit_fail"] += (not ok)
    out = {}
    for mode in ("weighted", "veto"):
        s = stats[mode]
        out[mode] = {
            "overall_failure": round(s["all_fail"] / n_ep, 4),
            "critical_failure": round(s["crit_fail"] / max(1, s["crit"]), 4),
        }
    # ambiguity: naive lambda ignores H[alpha]; A-RISK includes it
    rows = []
    for H in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
        f_naive = clamp(0.03 + 0.45 * H)
        lam = 1.0 + 3.0 * H
        f_arisk = clamp(0.03 + 0.45 * H) / (1.0 + 2.0 * (lam - 1.0))
        rows.append({"H_alpha": H, "naive_failure": round(f_naive, 4),
                     "arisk_failure": round(f_arisk, 4),
                     "lambda": round(lam, 4)})
    out["authority_ambiguity"] = rows
    return out


# ---------------------------------------------------------------- Part C
def part_c(n=120000):
    rng = random.Random(SEED + 2)
    def draw_margin():
        return rng.uniform(0.30, 1.00)

    def draw_latency():
        return rng.lognormvariate(math.log(0.35), 0.22)

    lat = [draw_latency() for _ in range(60000)]
    lat.sort()
    q99 = lat[int(0.99 * (len(lat) - 1))]
    q999 = lat[int(0.999 * (len(lat) - 1))]
    speeds = [0.3, 0.5, 0.7, 0.9, 1.1, 1.3]
    fixed = {}
    for v in speeds:
        viol = 0
        n_ep = n // len(speeds)
        for _ in range(n_ep):
            m = draw_margin()
            if v * draw_latency() > m:
                viol += 1
        fixed[str(v)] = round(viol / n_ep, 4)

    def takeover_aware(q):
        viol = 0
        v_sum = 0.0
        for _ in range(n):
            m = draw_margin()
            v = m / q
            v_sum += v
            if v * draw_latency() > m:
                viol += 1
        return {"violation": round(viol / n, 5), "mean_speed": round(v_sum / n, 4)}

    return {
        "q99_takeover_latency_s": round(q99, 4),
        "q999_takeover_latency_s": round(q999, 4),
        "fixed_speed_violation": fixed,
        "takeover_aware_q99": takeover_aware(q99),
        "takeover_aware_q999": takeover_aware(q999),
        "speed_vs_fixed_0.7": round(takeover_aware(q999)["mean_speed"] / 0.7, 4),
    }


# ---------------------------------------------------------------- Part D
def part_d(n_episodes=400, steps=200, noise=0.15, true_margin=0.25):
    rng = random.Random(SEED + 3)
    # slow two-state competence regime; estimates are noisy. Utility = correct holder.
    def run(hyst, dwell):
        holder = "robot"
        since = 0
        switches = 0
        utility = 0.0
        for _ in range(n_episodes):
            true = "robot" if rng.random() < 0.5 else "human"
            for step in range(steps):
                if step % 40 == 0 and rng.random() < 0.5:
                    true = "human" if true == "robot" else "robot"
                d = (true_margin if true == "robot" else -true_margin) + rng.gauss(0.0, noise)
                best = "robot" if d > 0 else "human"
                since += 1
                if best != holder and since >= dwell:
                    if hyst > 0 and abs(d) < hyst:
                        utility += 1.0 if holder == true else 0.0
                        continue
                    holder = best
                    since = 0
                    switches += 1
                utility += 1.0 if holder == true else 0.0
        return switches / n_episodes, utility / (n_episodes * steps)

    naive_s, naive_u = run(0.0, 1)
    hyst_s, hyst_u = run(0.10, 5)
    return {
        "naive_switches_per_episode": round(naive_s, 2),
        "naive_accuracy": round(naive_u, 4),
        "hysteresis_switches_per_episode": round(hyst_s, 2),
        "hysteresis_accuracy": round(hyst_u, 4),
        "switch_reduction": round(1 - hyst_s / max(1e-9, naive_s), 4),
        "accuracy_change": round(hyst_u - naive_u, 4),
    }


# ---------------------------------------------------------------- Part E
def part_e():
    g_max, tau_g = 1.0, 1.6
    c1, c2, e_over = 0.06, 0.035, 5.0

    def net(e):
        gain = g_max * (1.0 - math.exp(-e / tau_g))
        cost = c1 * e + c2 * max(0.0, e - e_over) ** 2
        return gain - cost, gain, cost

    es = [i * 0.1 for i in range(0, 201)]
    best_e, best_net = max(((e, net(e)[0]) for e in es), key=lambda x: x[1])
    max_net = net(12.0)[0]
    return {
        "opt_explanation_dose": round(best_e, 2),
        "opt_net": round(best_net, 4),
        "max_dose_net": round(max_net, 4),
        "overdose_penalty": round((best_net - max_net) / best_net, 4),
        "gain_at_opt": round(net(best_e)[1], 4),
        "cost_at_opt": round(net(best_e)[2], 4),
    }


def main():
    res = {
        "_meta": "synthetic mechanism check, not a benchmark; seed=%d" % SEED,
        "part_a_trust": part_a(),
        "part_b_authority": part_b(),
        "part_c_takeover": part_c(),
        "part_d_chatter": part_d(),
        "part_e_transparency": part_e(),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
