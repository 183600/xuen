#!/usr/bin/env python3
"""DEIXIS-RAS toy simulations (round R70).

Three cheap, self-contained checks behind the round's claims:
  A. semantic vs indexical channel routing (ask / move / verify)
  B. referent-set safety certificate vs MAP-referent execution
  C. bounded map corruption under spatial provenance guard (cap + gate + ledger)

Not a benchmark; a sanity check that the qualitative claims hold in a
minimal generative model. Reproduce: python deixis_sim.py > deixis_results.json
"""
import json
import math
import random
import statistics

random.seed(0)


def phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# ---------------------------------------------------------------- A. routing
def sim_routing():
    """Two referents, angular separation delta (deg). Pose error sigma_x is
    common-mode (does not average out by re-asking); gesture noise sigma_g
    averages out. Ask yields a semantic name with prob p_sem, else a repeated
    deictic gesture. Move shrinks sigma_x. Verify = move + look, costly."""
    sigma_g = 2.0
    p_sem = 0.35
    rows = []
    for delta in (5.0, 10.0, 20.0, 40.0):
        for sigma_x in (1.0, 3.0, 8.0, 15.0):
            s_ask = math.sqrt(sigma_x ** 2 + sigma_g ** 2 / 2.0)
            p_target_ask = phi(delta / (2.0 * s_ask))
            ask = p_sem * 1.0 + (1.0 - p_sem) * p_target_ask

            s_move = math.sqrt((0.25 * sigma_x + 0.5) ** 2 + sigma_g ** 2)
            move = phi(delta / (2.0 * s_move))

            # R69: ask whenever ambiguous, never move for SLAM.
            # DEIXIS: route to argmax expected success per equal cost; if the
            # best single action is still weak, pay for verify.
            best = max(ask, move)
            if best < 0.80:
                routed, cost, chosen = 0.95, 2.0, "verify"
            elif move > ask:
                routed, cost, chosen = move, 1.0, "move"
            else:
                routed, cost, chosen = ask, 1.0, "ask"
            rows.append({
                "delta_deg": delta, "sigma_x_deg": sigma_x,
                "p_correct_ask": round(ask, 4),
                "p_correct_move": round(move, 4),
                "p_correct_routed": round(routed, 4),
                "cost": cost, "chosen": chosen,
                "r69_p_correct": round(ask, 4),
            })
    # aggregate over the grid, weighting all cells equally
    agg = {
        "r69_mean_success": round(statistics.mean(r["r69_p_correct"] for r in rows), 4),
        "r69_mean_cost": 1.0,
        "deixis_mean_success": round(statistics.mean(r["p_correct_routed"] for r in rows), 4),
        "deixis_mean_cost": round(statistics.mean(r["cost"] for r in rows), 4),
        "cells_where_move_beats_ask": sum(r["p_correct_move"] > r["p_correct_ask"] for r in rows),
        "cells_total": len(rows),
    }
    return {"grid": rows, "aggregate": agg}


# ------------------------------------------------------------ B. safety set
def sim_referent_safety():
    """A = safe referent, B = dangerous referent, bearings separated by delta.
    Symmetric prior; gaussian pointing likelihood in 1D. Compare MAP-referent
    execution at a confidence threshold with the referent-set certificate."""
    delta = 20.0
    trials = 20000
    alpha = 0.10
    # RSC: execute only when P(B|o) <= alpha (i.e. the alpha-referent set is
    # entirely on the safe side). Otherwise verify (no violation, no success).
    map_threshold = 0.80
    out = {"alpha": alpha, "trials": trials, "delta_deg": delta, "by_sigma": {}}
    for sigma in (4.0, 6.0, 8.0, 12.0):
        res = {}
        for policy in ("map", "rsc"):
            viol = execute_b = execute_a = n_a = verify = 0
            for _ in range(trials):
                true_b = random.random() < 0.5
                n_a += int(not true_b)
                mean = delta if true_b else 0.0
                o = random.gauss(mean, sigma)
                # log-likelihood ratio B vs A
                llr = ((o - 0.0) ** 2 - (o - delta) ** 2) / (2.0 * sigma ** 2)
                p_b = 1.0 / (1.0 + math.exp(-llr))
                if policy == "map":
                    if max(p_b, 1 - p_b) < map_threshold:
                        verify += 1
                    elif p_b >= 0.5:          # execute toward B (hazard)
                        execute_b += 1
                    else:                      # execute toward A
                        execute_a += 1
                else:
                    if p_b <= alpha:
                        execute_a += 1         # alpha-set entirely safe
                    else:
                        verify += 1            # never execute toward B
            res[policy] = {
                # unsafe regardless of what the human actually meant
                "execute_hazard_rate": round(execute_b / trials, 4),
                # correct execution conditional on the intended referent A
                "success_given_safe_A": round(execute_a / n_a, 4),
                "verify_rate": round(verify / trials, 4),
            }
        out["by_sigma"][str(sigma)] = res
    return out


# -------------------------------------------------- C. bounded map corruption
def sim_map_corruption():
    """One landmark estimate under a stream of gesture-derived constraints.
    Malicious fraction f is biased by b; compare uncapped averaging, capped
    influence, cap+chi2 gate, and the ephemeral ledger (unverified gestures
    never promoted)."""
    trials = 4000
    T = 60
    f_mal = 0.2
    bias = 5.0
    noise = 0.5
    w0 = 0.5
    w_cap = 0.08
    gate = 2.0
    out = {}
    for policy in ("uncapped", "cap", "cap_gate", "ledger"):
        errs = []
        for _ in range(trials):
            x = random.gauss(0.0, 1.0)  # true landmark at 0
            for _ in range(T):
                mal = random.random() < f_mal
                m = (bias if mal else 0.0) + random.gauss(0.0, noise)
                if policy == "uncapped":
                    x += w0 * (m - x)
                elif policy == "cap":
                    x += w_cap * (m - x)
                elif policy == "cap_gate":
                    if abs(m - x) <= gate:
                        x += w_cap * (m - x)
                else:  # ledger: only corroborated (non-malicious) constraints
                    if not mal:
                        x += w_cap * (m - x)
            errs.append(abs(x))
        out[policy] = {
            "rmse": round(math.sqrt(statistics.mean(e * e for e in errs)), 4),
            "p95_abs_err": round(sorted(errs)[int(0.95 * len(errs))], 4),
            "max_abs_err": round(max(errs), 4),
        }
    out["settings"] = {"T": T, "malicious_fraction": f_mal, "bias": bias,
                       "w0": w0, "w_cap": w_cap, "gate": gate}
    return out


if __name__ == "__main__":
    result = {
        "A_routing": sim_routing(),
        "B_referent_safety": sim_referent_safety(),
        "C_map_corruption": sim_map_corruption(),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
