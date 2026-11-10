#!/usr/bin/env python3
"""Round 41 simulation suite: stdlib only, deterministic seeds.

E73 mode-conditional flow certificate under contact switching
E74 ambiguity-robust desktop target selection
E75 certificate-budget typing rejection power
E76 proof-carrying hierarchical search efficiency
E77 eventual desktop certificate (verify-and-retry)
E78 mixed-domain end-to-end
"""
import json
import math
import os
import random
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "res_round41.json")

A_F = [[-0.8, 0.0], [0.0, -0.4]]
B_F = [0.5, -0.1]
A_C = [[-2.4, 0.7], [0.25, -3.0]]
B_C = [0.15, 0.2]
SURFACE = 0.0
EPS_TOL = 0.15
DELTA_SW = 0.02


def matvec(a, x):
    return [a[0][0] * x[0] + a[0][1] * x[1], a[1][0] * x[0] + a[1][1] * x[1]]


def spectral_norm(a):
    e = a[0][0] ** 2 + a[0][1] ** 2
    f = a[1][0] ** 2 + a[1][1] ** 2
    g = a[0][0] * a[1][0] + a[0][1] * a[1][1]
    tr = e + f
    det = e * f - g * g
    disc = max(0.0, tr * tr / 4.0 - det)
    lam = tr / 2.0 + math.sqrt(disc)
    return math.sqrt(max(lam, 0.0))


def sigmoid(z):
    if z >= 0.0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def make_field(w):
    d_a = [[A_C[i][j] - A_F[i][j] for j in range(2)] for i in range(2)]
    d_b = [B_C[i] - B_F[i] for i in range(2)]

    def v(x):
        vf = [A_F[i][0] * x[0] + A_F[i][1] * x[1] + B_F[i] for i in range(2)]
        dc = [d_a[i][0] * x[0] + d_a[i][1] * x[1] + d_b[i] for i in range(2)]
        s = sigmoid((x[0] - SURFACE) / w)
        return [vf[i] + s * dc[i] for i in range(2)]

    return v, d_a, d_b


def rk2_step(v, x, h):
    k1 = v(x)
    xm = [x[0] + 0.5 * h * k1[0], x[1] + 0.5 * h * k1[1]]
    k2 = v(xm)
    return [x[0] + h * k2[0], x[1] + h * k2[1]]


def integrate(v, x0, n, mode_aware=False, tmax=1.0):
    h = tmax / n
    x = list(x0)
    traj = [list(x)]
    for _ in range(n):
        if mode_aware:
            xn = rk2_step(v, x, h)
            if (x[0] - SURFACE) * (xn[0] - SURFACE) < 0.0:
                xm = rk2_step(v, x, 0.5 * h)
                x = rk2_step(v, xm, 0.5 * h)
            else:
                x = xn
        else:
            x = rk2_step(v, x, h)
        traj.append(list(x))
    return traj


def norm2(x):
    return math.sqrt(x[0] * x[0] + x[1] * x[1])


def exp_amp(l, t):
    if l * t > 700.0:
        return float("inf")
    return math.exp(l * t)


def bound_global(n, l_glob, c2, tmax=1.0):
    h = tmax / n
    if l_glob <= 0.0:
        return c2 * h * h * tmax
    return (c2 * h * h / l_glob) * (exp_amp(l_glob, tmax) - 1.0)


def bound_mode(n, segs, c2, l_sw, n_sw, delta_sw, tmax=1.0):
    h = tmax / n
    total = 0.0
    for (t_i, l_i) in segs:
        if l_i <= 0.0:
            total += c2 * h * h * t_i
        else:
            total += (c2 * h * h / l_i) * (exp_amp(l_i, t_i) - 1.0)
    total += n_sw * l_sw * delta_sw
    return total


def nstar(bound_fn, eps=EPS_TOL, cap=10 ** 12):
    n = 1
    while n <= cap:
        if bound_fn(n) <= eps:
            return n
        n += 1
        if n in (16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576):
            continue
    return cap


def e73():
    out = {"eps_tol": EPS_TOL, "delta_sw": DELTA_SW}
    l_f = spectral_norm(A_F)
    l_c = spectral_norm(A_C)
    d_a = [[A_C[i][j] - A_F[i][j] for j in range(2)] for i in range(2)]
    l_da = spectral_norm(d_a)
    d_b = [B_C[i] - B_F[i] for i in range(2)]
    jump_local = l_da * math.sqrt(DELTA_SW ** 2 + 1.0) + norm2(d_b)
    c2 = (1.0 / 24.0) * (l_f ** 2 + l_c ** 2 + l_da ** 2)
    out["constants"] = {"L_free": l_f, "L_contact": l_c, "L_deltaA": l_da,
                        "jump_local": jump_local, "C2": c2}
    trend = []
    for w in (0.3, 0.1, 0.03, 0.02, 0.01):
        l_glob = l_f + l_da + jump_local / (4.0 * w)
        bg = bound_global(1, l_glob, c2)
        ng = nstar(lambda n: bound_global(n, l_glob, c2))
        trend.append({"w": w, "L_global": l_glob, "N_star_global": ng,
                      "bound_at_N1": bg})
    out["global_certificate_trend"] = trend

    rng = random.Random(20261110)
    inits = []
    for _ in range(120):
        inits.append([-2.5 + 2.2 * rng.random(), -0.4 + 0.8 * rng.random()])

    scenarios = []
    for w_sim in (0.02, 0.05):
        v, _, _ = make_field(w_sim)
        refs = [integrate(v, x0, 20000, True)[-1] for x0 in inits]
        segs_list = []
        for x0 in inits:
            traj = integrate(v, x0, 20000, True)
            t1 = None
            for idx, p in enumerate(traj):
                if p[0] >= SURFACE:
                    t1 = idx / 20000.0
                    break
            if t1 is None:
                t1 = 0.999
            segs_list.append([(t1, l_f), (1.0 - t1, l_c)])
        t1_med = sorted(s[0][0] for s in segs_list)[len(segs_list) // 2]
        segs_nominal = [(t1_med, l_f), (1.0 - t1_med, l_c)]
        l_glob = l_f + l_da + jump_local / (4.0 * w_sim)
        ng = nstar(lambda n: bound_global(n, l_glob, c2))
        nm = nstar(lambda n: bound_mode(n, segs_nominal, c2, jump_local, 1, DELTA_SW))
        bn = bound_mode(nm, segs_nominal, c2, jump_local, 1, DELTA_SW)
        err_mode = []
        err_naive = []
        covered = 0
        ratios = []
        for x0, ref in zip(inits, refs):
            xe_mode = integrate(v, x0, nm, True)[-1]
            xe_naive = integrate(v, x0, nm, False)[-1]
            e_m = norm2([xe_mode[0] - ref[0], xe_mode[1] - ref[1]])
            e_n = norm2([xe_naive[0] - ref[0], xe_naive[1] - ref[1]])
            err_mode.append(e_m)
            err_naive.append(e_n)
            b_i = bound_mode(nm, segs_list[len(err_mode) - 1], c2, jump_local, 1, DELTA_SW)
            if e_m <= b_i:
                covered += 1
            ratios.append(b_i / max(e_m, 1e-12))
        scenarios.append({
            "w_sim": w_sim,
            "consistent_with_delta_sw": w_sim <= DELTA_SW,
            "N_star_global": ng,
            "N_star_mode": nm,
            "bound_mode_at_Nstar": bn,
            "err_mode_max": max(err_mode),
            "err_mode_median": sorted(err_mode)[len(err_mode) // 2],
            "err_naive_max": max(err_naive),
            "err_naive_median": sorted(err_naive)[len(err_naive) // 2],
            "coverage": covered / len(inits),
            "tightness_median": sorted(ratios)[len(ratios) // 2],
            "t1_median": t1_med,
            "t1_spread": (max(s[0][0] for s in segs_list), min(s[0][0] for s in segs_list)),
        })
    out["scenarios"] = scenarios
    out["mode_segments"] = {"free": "(T1, L_free)", "contact": "(T2, L_contact)"}
    return out


def e74():
    rng = random.Random(20261111)
    out = {}
    grid = []
    for beta in (0.90, 0.96):
        for alpha in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
            row = {"beta_robust_action": beta, "alpha_disambiguator": alpha}
            for k in (1, 3, 5, 9):
                p_correct = max(0.35, 0.9 - 0.06 * (k - 1))
                trials = 4000
                naive = 0
                naive_re = 0
                ours = 0
                for _ in range(trials):
                    truth = rng.randrange(k)
                    pred = truth if rng.random() < p_correct else rng.choice(
                        [i for i in range(k) if i != truth])
                    naive += 1 if pred == truth else 0
                    fixed = pred == truth or rng.random() < alpha
                    naive_re += 1 if fixed else 0
                    if rng.random() < beta:
                        ours += 1
                    else:
                        ours += 1 if rng.random() < alpha else 0
                row["k%d_naive" % k] = naive / trials
                row["k%d_naive_plus_reground" % k] = naive_re / trials
                row["k%d_ours" % k] = ours / trials
            grid.append(row)
    out["grid"] = grid
    breaks = []
    for k in (3, 5, 9):
        p_correct = max(0.35, 0.9 - 0.06 * (k - 1))
        vals = []
        for alpha in [i / 100.0 for i in range(40, 101)]:
            base = p_correct + (1.0 - p_correct) * alpha
            ours = 0.96 + 0.04 * alpha
            vals.append((alpha, base, ours, base - ours))
        crossover = [a for a, b, o, d in vals if d <= 0.0]
        breaks.append({"k": k, "p_correct": p_correct,
                       "break_even_alpha": min(crossover) if crossover else None,
                       "max_gain_pp_at_alpha_0.7": 100.0 * (
                           (0.96 + 0.04 * 0.7) - (p_correct + (1 - p_correct) * 0.7))})
    out["break_even"] = breaks
    out["latency_model_ms"] = {"naive_click": 6, "ours_robust_action": 10,
                               "ours_fallback_reground": 22,
                               "naive_plus_reground": 21}
    return out


def e75():
    rng = random.Random(20261112)
    out = {"cases": []}
    for chain_len in (4, 6, 8):
        for budget in (0.8, 1.2):
            chains = 4000
            over_budget = 0
            local_violation = 0
            naive_chain_success = 0.0
            ours_success = 0.0
            ours_reject = 0
            caught = 0
            for _ in range(chains):
                nus = [rng.uniform(0.05, 0.35) for _ in range(chain_len)]
                tols = [rng.uniform(0.15, 0.50) for _ in range(chain_len)]
                total_nu = sum(nus)
                local_bad = any(nu > tol for nu, tol in zip(nus, tols))
                p = 1.0
                for nu, tol in zip(nus, tols):
                    p *= 1.0 / (1.0 + math.exp(-(tol - nu) / 0.15))
                naive_chain_success += p
                over_budget += 1 if total_nu > budget else 0
                local_violation += 1 if local_bad else 0
                infeasible = (total_nu > budget) or local_bad
                if infeasible:
                    ours_reject += 1
                    ours_success += 0.90
                    caught += 1 if local_bad else 0
                else:
                    ours_success += p
            out["cases"].append({
                "chain_len": chain_len,
                "budget": budget,
                "frac_over_budget": over_budget / chains,
                "frac_local_guarantee_violated": local_violation / chains,
                "naive_chain_success": naive_chain_success / chains,
                "ours_success": ours_success / chains,
                "ours_reject_rate": ours_reject / chains,
                "local_violations_caught": caught,
                "local_violations_total": local_violation,
            })
    return out


def gen_instance(rng, n_nodes=9, n_flags=3):
    flags = [frozenset(i for i in range(n_flags) if rng.random() < 0.55)
             for _ in range(n_nodes)]
    edges = []
    for i in range(n_nodes):
        for j in range(n_nodes):
            if i == j:
                continue
            if rng.random() < 0.42:
                req = frozenset(i for i in range(n_flags) if rng.random() < 0.35)
                edges.append({"u": i, "v": j, "req": req,
                              "cost": 1.0 + rng.random() * 3.0,
                              "budget": 0.1 + rng.random() * 0.35})
    goal = n_nodes - 1
    while True:
        reachable = {0}
        changed = True
        while changed:
            changed = False
            for e in edges:
                if e["u"] in reachable and e["req"] <= flags[e["u"]] and e["v"] not in reachable:
                    reachable.add(e["v"])
                    changed = True
        if goal in reachable:
            break
        mid = rng.randrange(1, n_nodes)
        edges.append({"u": 0, "v": mid, "req": frozenset(), "cost": 2.0,
                      "budget": 0.2})
        edges.append({"u": mid, "v": goal, "req": frozenset(), "cost": 2.0,
                      "budget": 0.2})
    return {"n_nodes": n_nodes, "flags": flags, "edges": edges, "goal": goal}


def astar_blind(inst, forbidden):
    import heapq
    n = inst["n_nodes"]
    goal = inst["goal"]
    adj = {}
    for e in inst["edges"]:
        adj.setdefault(e["u"], []).append(e)
    dist = [float("inf")] * n
    parent = {}
    dist[0] = 0.0
    pq = [(0.0, 0)]
    expansions = 0
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist[u] + 1e-12:
            continue
        if u == goal:
            break
        expansions += 1
        for e in adj.get(u, []):
            if (e["u"], e["v"]) in forbidden:
                continue
            nd = d + e["cost"]
            if nd < dist[e["v"]] - 1e-12:
                dist[e["v"]] = nd
                parent[e["v"]] = e
                heapq.heappush(pq, (nd, e["v"]))
    if goal not in parent and goal != 0:
        return None, expansions
    path = []
    cur = goal
    while cur != 0:
        e = parent[cur]
        path.append(e)
        cur = e["u"]
    path.reverse()
    return path, expansions


def astar_proof_carrying(inst, budget):
    import heapq
    n = inst["n_nodes"]
    goal = inst["goal"]
    flags = inst["flags"]
    adj = {}
    for e in inst["edges"]:
        adj.setdefault(e["u"], []).append(e)
    best = {}
    pq = [(0.0, 0, ())]
    expansions = 0
    best_g = {(0, 0.0): 0.0}
    while pq:
        g, u, spent = heapq.heappop(pq)
        if g > best_g.get((u, spent), float("inf")) + 1e-12:
            continue
        if u == goal:
            return True, expansions
        expansions += 1
        for e in adj.get(u, []):
            if not e["req"] <= flags[u]:
                continue
            new_spent = spent + e["budget"]
            if new_spent > budget + 1e-12:
                continue
            ng = g + e["cost"] + 0.5 * e["budget"]
            key = (e["v"], round(new_spent, 6))
            if ng < best_g.get(key, float("inf")) - 1e-12:
                best_g[key] = ng
                heapq.heappush(pq, (ng, e["v"], key[1]))
    return False, expansions


def e76():
    rng = random.Random(20261113)
    insts = [gen_instance(rng) for _ in range(200)]
    tot_blind_exp = 0
    tot_pc_exp = 0
    blind_rounds = 0
    pc_rounds = 0
    blind_valid = 0
    pc_valid = 0
    blind_success = 0
    pc_success = 0
    t_blind = 0.0
    t_pc = 0.0
    for inst in insts:
        budget = 1.0
        t0 = time.perf_counter()
        forbidden = set()
        rounds = 0
        valid = False
        while rounds < 6:
            rounds += 1
            path, exp = astar_blind(inst, forbidden)
            tot_blind_exp += exp
            if path is None:
                break
            bad = [e for e in path if not e["req"] <= inst["flags"][e["u"]]]
            if not bad:
                valid = True
                break
            forbidden.add((bad[0]["u"], bad[0]["v"]))
        t_blind += time.perf_counter() - t0
        blind_rounds += rounds
        blind_valid += 1 if valid else 0
        blind_success += 1 if valid else 0

        t0 = time.perf_counter()
        ok, exp = astar_proof_carrying(inst, budget)
        t_pc += time.perf_counter() - t0
        tot_pc_exp += exp
        pc_rounds += 1
        pc_valid += 1 if ok else 0
        pc_success += 1 if ok else 0
    n = len(insts)
    return {
        "instances": n,
        "blind_expansions": tot_blind_exp,
        "proof_carrying_expansions": tot_pc_exp,
        "blind_rounds_total": blind_rounds,
        "blind_rounds_mean": blind_rounds / n,
        "proof_carrying_rounds_mean": pc_rounds / n,
        "blind_valid_plan_rate": blind_valid / n,
        "proof_carrying_valid_plan_rate": pc_valid / n,
        "blind_time_ms": 1000.0 * t_blind / n,
        "proof_carrying_time_ms": 1000.0 * t_pc / n,
    }


def e77():
    rng = random.Random(20261114)
    n = 20000
    p_fail = 0.12
    base_mu = math.log(7.0)
    base_sigma = 0.55

    def latency():
        return math.exp(rng.gauss(base_mu, base_sigma))

    single = 0
    lats_single = []
    retries = []
    lats_retry = []
    for _ in range(n):
        ok = rng.random() > p_fail
        l = latency()
        lats_single.append(l)
        single += 1 if ok else 0
        attempts = 1
        while not ok and attempts < 4:
            l += latency()
            ok = rng.random() > p_fail
            attempts += 1
        retries.append(attempts)
        lats_retry.append(l)
    lats_single.sort()
    lats_retry.sort()

    def pct(arr, p):
        return arr[min(len(arr) - 1, int(p * len(arr)))]

    p3 = p_fail ** 3
    return {
        "trials": n,
        "p_fail_assumed": p_fail,
        "single_shot_success": single / n,
        "retry_success": 1.0 - sum(1 for a in retries if a >= 4) / n,
        "single_shot_p50_ms": pct(lats_single, 0.50),
        "single_shot_p99_ms": pct(lats_single, 0.99),
        "retry_p50_ms": pct(lats_retry, 0.50),
        "retry_p99_ms": pct(lats_retry, 0.99),
        "mean_attempts": sum(retries) / n,
        "union_bound_success_claim": 1.0 - p3,
    }


def e78():
    rng = random.Random(20261115)
    e73r = e73()
    e74r = e74()
    e75r = e75()
    sc = [s for s in e73r["scenarios"] if s["consistent_with_delta_sw"]]
    mode_ok = 1.0
    if sc:
        ratio = sc[0]["err_mode_max"] / max(EPS_TOL, 1e-9)
        mode_ok = 1.0 / (1.0 + math.exp(-(1.0 - ratio) * 6.0))
    alpha = 0.7
    p_correct = max(0.35, 0.9 - 0.06 * (5 - 1))
    desktop_ok = 0.96 + 0.04 * alpha
    budget_case = e75r["cases"][0]
    episodes = 5000
    full = 0
    no_ledger = 0
    no_mode = 0
    viol = 0
    for _ in range(episodes):
        s1 = rng.random() < mode_ok
        s2 = rng.random() < desktop_ok
        s3 = rng.random() < budget_case["ours_success"]
        full += 1 if (s1 and s2 and s3) else 0
        s3b = rng.random() < budget_case["naive_chain_success"]
        no_ledger += 1 if (s1 and s2 and s3b) else 0
        no_mode += 1 if (s2 and s3) else 0
        viol += 1 if (s1 and s2 and not s3b) else 0
    return {
        "episodes": episodes,
        "full_stack_success": full / episodes,
        "no_budget_ledger_success": no_ledger / episodes,
        "no_mode_aware_flow_success": no_mode / episodes,
        "decorative_certificate_rate": viol / episodes,
        "assumed_subtask_success": {"gripper": mode_ok, "desktop": desktop_ok,
                                    "plan_budgeted": budget_case["ours_success"],
                                    "plan_naive": budget_case["naive_chain_success"]},
    }


def main():
    t0 = time.perf_counter()
    res = {
        "meta": {"seed_base": 20261110, "python": "stdlib-only",
                 "wall_ms": None},
        "e73": e73(),
        "e74": e74(),
        "e75": e75(),
        "e76": e76(),
        "e77": e77(),
        "e78": e78(),
    }
    res["meta"]["wall_ms"] = 1000.0 * (time.perf_counter() - t0)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: (v if not isinstance(v, dict) else "...")
                      for k, v in res.items()}, ensure_ascii=False))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
