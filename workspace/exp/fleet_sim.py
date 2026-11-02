"""Round-16 synthetic mechanism check: NEST-VLA.

Sim-aNchored, fleet-coupled, SLO-scalable serving layer for UniBot-V1.

NOT benchmark evidence. Three isolated mechanism questions.

S1  Sim-anchored paired counterfactual augmentation (SAP)
    The official simulator (unitree_sim_isaaclab) can REPLAY the recorded
    actions while randomising lighting / camera (`--generate_data`,
    `--modify_light`, `--modify_camera`).  That yields paired
    (action, appearance-A, appearance-B) tuples with *identical* action labels.
    Question: does replay-augmentation + a nuisance-consistency regulariser beat
    (a) real-only and (b) naive extra sim data on background and per-robot
    camera shifts, without hurting ID -- and what is its boundary?

S2  Fleet-shared calibration under state isolation (FSC)
    N ports must keep episode *state* isolated, but aggregate, non-episode
    statistics may be shared.  Ports already evaluated warm-start a shared
    conformal scale/quantile for later ports.  Question: how much warmup does a
    hierarchical (shrink-to-fleet) estimator save, and does a trimmed/median
    aggregate bound contamination from one rogue robot?

S3  Chunk-size / latency scalability frontier
    N ports share one model instance.  Chunk length T trades inference call rate
    (fleet throughput) against reaction granularity (trust-gate abort latency).
    Question: at what N does a static chunk violate the latency SLO, and does an
    adaptive per-port chunk dominate the best static choice?

Declared generative models; magnitudes are illustrative, not fit to the board.
"""
import json
import math
import os
import random
import statistics as st

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fleet_results.json")
LEADER = os.path.join(HERE, "unibot_leaderboard_20261102.json")

RNG_SEED = 20261102


# ======================================================================
# S0  live leaderboard facts (provenance: official leaderboard_data.json)
# ======================================================================
def leaderboard_facts():
    with open(LEADER, encoding="utf-8") as f:
        d = json.load(f)
    models = d["models"]
    tasks = d["tasks"]
    n_m = len(models)
    n_t = len(tasks)
    S = {m["model_name"]: {t["task"]: t["success_rate"] for t in m["task_metrics"]}
         for m in models}
    K = {m["model_name"]: {t["task"]: t["step_score"] for t in m["task_metrics"]}
         for m in models}
    names = [m["model_name"] for m in models]

    # rank correlation success vs step_score (should be identical)
    def ranks(vals):
        order = sorted(range(len(vals)), key=lambda i: -vals[i])
        r = [0] * len(vals)
        for pos, i in enumerate(order):
            r[i] = pos
        return r
    r_s = ranks([m["avg_success_rate"] for m in models])
    r_k = ranks([m["avg_step_score"] for m in models])
    rank_identical = r_s == r_k

    # oracle per-task routing over the 8 submitted models (upper bound only)
    oracle = sum(max(S[n][t] for n in names) for t in tasks) / n_t
    leader_avg = models[0]["avg_success_rate"]
    # model tau corr across 32 tasks (pairwise mean)
    def corr(a, b):
        xa = [S[a][t] for t in tasks]
        xb = [S[b][t] for t in tasks]
        mx, my = st.mean(xa), st.mean(xb)
        sx = math.sqrt(sum((v - mx) ** 2 for v in xa))
        sy = math.sqrt(sum((v - my) ** 2 for v in xb))
        if sx == 0 or sy == 0:
            return 0.0
        return sum((a0 - mx) * (b0 - my) for a0, b0 in zip(xa, xb)) / (sx * sy)
    pair = [corr(a, b) for i, a in enumerate(names) for b in names[i + 1:]]
    step_ratio = [round(m["avg_step_score"] / m["avg_success_rate"], 3)
                  for m in models]
    return {
        "source": "https://unibot.unitree.com/leaderboard_data.json",
        "retrieved": "2026-11-02",
        "n_models_generalist": n_m,
        "n_models_specialist": len(d.get("specialist", [])),
        "n_tasks": n_t,
        "leader": names[0],
        "leader_success": leader_avg,
        "mean_pairwise_task_corr": round(st.mean(pair), 4),
        "min_pairwise_corr": round(min(pair), 4),
        "max_pairwise_corr": round(max(pair), 4),
        "oracle_per_task_avg": round(oracle, 3),
        "oracle_headroom_pp": round(oracle - leader_avg, 3),
        "step_over_success_ratio": step_ratio,
        "rank_identical_success_vs_step": rank_identical,
        "note": "step score adds no ranking information over success (ranks identical)",
    }


# ======================================================================
# S1  Sim-anchored paired counterfactual augmentation (SAP)
# ======================================================================
BG = 6          # background clusters
LIGHT = 2       # lighting clusters
CELLS = BG * LIGHT
REAL_BG = {0, 1}   # recordings only cover these two backgrounds

PROFILE = {                    # per-stage tolerance / noise / semantic-miss rate
    "free":       dict(w=0.50, tau=0.050, sv=0.015, qmiss=0.20, stages=(2, 3)),
    "precision":  dict(w=0.30, tau=0.012, sv=0.012, qmiss=0.25, stages=(1, 2, 3)),
    "deformable": dict(w=0.20, tau=0.030, sv=0.025, qmiss=0.30, stages=(2, 3, 4)),
}
KAPPA = 0.011        # m of target bias per unit background distance
ROBOT_SIG = 0.008    # per-robot camera/calibration systematic bias (m)
DEFORM_RES = 0.030   # un-modellable deformation residual sigma (m)

# policy -> (background coverage aug in [0,1], nuisance-consistency in [0,1])
AUG = {
    "real":      (0.00, 0.00),
    "sim_naive": (0.30, 0.00),   # extra sim frames, no paired action labels
    "sap":       (1.00, 0.60),   # full replay coverage + consistency loss
    "sap_hard":  (1.00, 0.85),
}


def bgdist(bg):
    return 0 if bg in REAL_BG else min(abs(bg - b) for b in REAL_BG)


def unit(rng):
    a = rng.uniform(0.0, 2.0 * math.pi)
    return np.array([math.cos(a), math.sin(a)])


def run_ep_s1(kind, policy, rng, kappa=KAPPA, robot_sig=ROBOT_SIG,
              p_novel=0.15):
    p = PROFILE[kind]
    S = rng.choice(p["stages"])
    c = rng.randrange(CELLS)
    bg = c // LIGHT
    d = float(bgdist(bg))
    aug, cons = AUG[policy]
    d_eff = d * (1.0 - aug)
    robot = np.array([rng.gauss(0, robot_sig), rng.gauss(0, robot_sig)])
    passed = 0
    prog = 0.0
    succ = True
    for _ in range(S):
        miss = rng.random() < p["qmiss"]
        b = unit(rng) * rng.uniform(0.02, 0.08) if miss else np.zeros(2)
        if rng.random() < p_novel:            # unseen-object semantic novelty
            b = b + unit(rng) * rng.uniform(0.02, 0.06)   # augmentation cannot fix
        app = unit(rng) * kappa * d_eff
        sv = p["sv"] * (1.0 - 0.15 * aug)     # extra visual data -> small noise cut
        noise = np.array([rng.gauss(0, sv), rng.gauss(0, sv)])
        defv = (unit(rng) * abs(rng.gauss(0, DEFORM_RES))
                if kind == "deformable" else np.zeros(2))
        e = b + app + robot * (1.0 - cons) + noise + defv
        err = float(np.linalg.norm(e))
        if err <= p["tau"]:
            passed += 1
            prog += 1.0
        else:
            succ = False
            prog += max(0.0, 1.0 - err / (4.0 * p["tau"]))
            break
    return succ, prog / S, (bg in REAL_BG)


def eval_s1(policy, n=20000, seed=11, **kw):
    rng = random.Random(seed)
    id_s, oo_s, all_s = [], [], []
    for _ in range(n):
        kind = rng.choices(list(PROFILE), weights=[PROFILE[k]["w"] for k in PROFILE])[0]
        s, t, is_id = run_ep_s1(kind, policy, rng, **kw)
        all_s.append(1 if s else 0)
        (id_s if is_id else oo_s).append(1 if s else 0)
    return dict(id=st.mean(id_s), ood=st.mean(oo_s), all=st.mean(all_s), n=n)


# ======================================================================
# S2  Fleet-shared calibration under state isolation (FSC)
# ======================================================================
def eval_s2(P=16, episodes=12, sigma_h=0.30, sigma_noise=0.50,
            rogue=False, seed=3, tau_prior=0.30):
    """Per-port log-scale estimation error under three estimators:
    isolated (own sample mean), hierarchical (shrink to fleet), and a
    mean-aggregated fleet (non-robust, for contamination comparison)."""
    rng = random.Random(seed)
    true = [rng.gauss(0, sigma_h) for _ in range(P)]
    r_idx = P - 1 if rogue else None
    if rogue:
        true[r_idx] = 3.0                       # one badly mis-calibrated robot
    obs = [[] for _ in range(P)]                # per-port observation history
    curve = {"isolated": [], "hier": [], "fleet_mean": []}
    maj = {"isolated": [], "hier": [], "fleet_mean": []}   # exclude the rogue port
    for ep in range(episodes):
        for i in range(P):
            obs[i].append(true[i] + rng.gauss(0, sigma_noise))
        # estimators for each port
        iso_err, hier_err, fm_err = [], [], []
        port_means = [st.mean(obs[i]) for i in range(P)]
        prior = st.median(port_means)           # robust fleet prior
        for i in range(P):
            own = st.mean(obs[i])
            t = len(obs[i])
            v = sigma_noise ** 2 / t
            vp = tau_prior ** 2
            post = (v ** -1 * own + vp ** -1 * prior) / (v ** -1 + vp ** -1)
            iso_err.append(abs(own - true[i]))
            hier_err.append(abs(post - true[i]))
            fm_err.append(abs(st.mean(port_means) - true[i]))
        curve["isolated"].append(round(st.mean(iso_err), 4))
        curve["hier"].append(round(st.mean(hier_err), 4))
        curve["fleet_mean"].append(round(st.mean(fm_err), 4))
        keep = [i for i in range(P) if i != r_idx]
        for key, err in (("isolated", iso_err), ("hier", hier_err),
                         ("fleet_mean", fm_err)):
            maj[key].append(round(st.mean(err[i] for i in keep), 4))

    def warmup(target=0.25):
        out = {}
        for name in curve:
            out[name] = next((k + 1 for k, v in enumerate(curve[name]) if v <= target),
                             None)
        return out
    # derived false-fallback proxy: a scale error e gives FA ~ min(1, g*e)
    g = 1.5
    fa = {name: [round(min(1.0, g * v), 4) for v in vs] for name, vs in curve.items()}
    return dict(episodes=episodes, P=P, rogue=rogue,
                error_curve=curve, majority_error_curve=maj, false_alarm_proxy=fa,
                majority_final={k: v[-1] for k, v in maj.items()},
                error_at={k: {f"ep{e+1}": curve[k][e] for e in (0, 1, 2, 4)
                              if e < len(curve[k])} for k in curve},
                warmup_to_0p25=warmup(0.25),
                final={k: v[-1] for k, v in curve.items()})


# ======================================================================
# S3  Chunk-size / latency scalability frontier
# ======================================================================
def eval_s3(T_grid=(1, 2, 3, 5, 10, 20, 30, 50), N_grid=(3, 8, 12, 20),
            L0=0.030, a_per_step=0.0020, dt=0.02, batch=8,
            slo=0.150, base_succ=0.30, react_beta=0.20, viol_penalty=0.10):
    """Utilisation rho = N*L/(T*dt*B); p99 ~ L/(1-rho) when rho<1.
    Success degrades with chunk (coarser reaction) and with SLO violation."""
    out = {}
    for N in N_grid:
        rows = []
        for T in T_grid:
            L = L0 + a_per_step * T
            B = max(1, min(N, batch))
            rho = (N / (T * dt)) * L / B
            if rho < 1.0:
                p99 = L / (1.0 - rho)
            else:
                p99 = float("inf")
            viol = p99 > slo
            react_pen = react_beta * (T - 1) * dt     # coarser abort granularity
            succ = base_succ * (1.0 - react_pen) - (viol_penalty if viol else 0.0)
            rows.append(dict(T=T, latency_ms=round(1000 * L, 2),
                             calls_per_s=round(N / (T * dt), 1), rho=round(rho, 3),
                             p99_ms=(None if p99 == float("inf") else round(1000 * p99, 1)),
                             slo_violation=viol, success=round(max(0.0, succ), 4)))
        feasible = [r for r in rows if not r["slo_violation"]]
        best_static = max(feasible, key=lambda r: r["success"]) if feasible else None
        out[N] = dict(rows=rows, best_static_T=(best_static["T"] if best_static else None),
                      best_static_success=(best_static["success"] if best_static else 0.0))
    # adaptive: smallest T whose p99 meets the SLO (finest safe reaction)
    adaptive = {}
    for N in N_grid:
        T = pick_T(N, slo, L0, a_per_step, dt, batch)
        L = L0 + a_per_step * T
        rho = (N / (T * dt)) * L / max(1, min(N, batch))
        p99 = (L / (1 - rho)) if rho < 1 else float("inf")
        succ = base_succ * (1.0 - react_beta * (T - 1) * dt) - (viol_penalty if p99 > slo else 0.0)
        adaptive[N] = dict(T=T, rho=round(rho, 3),
                           p99_ms=(None if p99 == float("inf") else round(1000 * p99, 1)),
                           success=round(max(0.0, succ), 4))

    # time-varying fleet: load alternates between a quiet and a busy phase;
    # a static chunk must commit to one T, an SLO-aware controller tracks N.
    schedule = [(3, 300.0), (20, 200.0), (8, 300.0), (20, 200.0)]  # (N, seconds)
    total_t = sum(t for _, t in schedule)
    static_dyn = {}
    for T in T_grid:
        w_succ = w_viol = 0.0
        for N, sec in schedule:
            L = L0 + a_per_step * T
            rho = (N / (T * dt)) * L / max(1, min(N, batch))
            p99 = (L / (1 - rho)) if rho < 1 else float("inf")
            viol = p99 > slo
            succ = base_succ * (1.0 - react_beta * (T - 1) * dt) - (viol_penalty if viol else 0.0)
            w_succ += sec * max(0.0, succ)
            w_viol += sec * (1.0 if viol else 0.0)
        static_dyn[T] = dict(success=round(w_succ / total_t, 4),
                             violation_frac=round(w_viol / total_t, 3))
    w_succ = w_viol = 0.0
    for N, sec in schedule:
        ad = adaptive.get(N) or {}
        T = pick_T(N, slo, L0, a_per_step, dt, batch)
        L = L0 + a_per_step * T
        rho = (N / (T * dt)) * L / max(1, min(N, batch))
        p99 = (L / (1 - rho)) if rho < 1 else float("inf")
        succ = base_succ * (1.0 - react_beta * (T - 1) * dt) - (viol_penalty if p99 > slo else 0.0)
        w_succ += sec * max(0.0, succ)
        w_viol += sec * (1.0 if p99 > slo else 0.0)
    dynamic = dict(schedule=schedule, static=static_dyn,
                   adaptive=dict(success=round(w_succ / total_t, 4),
                                 violation_frac=round(w_viol / total_t, 3)))
    return dict(L0=L0, a_per_step=a_per_step, dt=dt, batch=batch, slo_ms=1000 * slo,
                static=out, adaptive=adaptive, dynamic=dynamic)


def pick_T(N, slo, L0, a_per_step, dt, batch, Tmax=200):
    """Smallest chunk length whose p99 latency meets the SLO."""
    for T in range(1, Tmax + 1):
        L = L0 + a_per_step * T
        rho = (N / (T * dt)) * L / max(1, min(N, batch))
        if rho < 1.0 and L / (1.0 - rho) <= slo:
            return T
    return Tmax


# ======================================================================
def main():
    random.seed(RNG_SEED)
    res = {"note": "synthetic mechanism check; not benchmark evidence",
           "seed": RNG_SEED}

    res["S0_leaderboard_facts"] = leaderboard_facts()
    print("== S0 leaderboard ==", res["S0_leaderboard_facts"])

    print("\n== S1 SAP (background + robot camera shift) ==")
    res["S1_sap"] = {}
    for pol in AUG:
        r = eval_s1(pol)
        res["S1_sap"][pol] = {k: round(v, 4) if isinstance(v, float) else v
                              for k, v in r.items()}
        print(f"  {pol:10s} ID {r['id']:.3f}  OOD {r['ood']:.3f}  all {r['all']:.3f}")

    print("\n  coverage sweep (SAP background aug) ==")
    res["S1_coverage_sweep"] = {}
    for aug in (0.0, 0.25, 0.5, 0.75, 1.0):
        AUG["sap"] = (aug, 0.60)
        r = eval_s1("sap", n=12000)
        res["S1_coverage_sweep"][f"aug={aug}"] = dict(
            id=round(r["id"], 4), ood=round(r["ood"], 4), all=round(r["all"], 4))
        print(f"    aug={aug}: ID {r['id']:.3f} OOD {r['ood']:.3f} all {r['all']:.3f}")
    AUG["sap"] = (1.00, 0.60)

    print("\n  sensitivity: appearance kappa x robot sigma (SAP vs real, OOD) ==")
    res["S1_sensitivity"] = {}
    for kappa in (0.005, 0.011, 0.020):
        row = {}
        for rsig in (0.004, 0.008, 0.016):
            real = eval_s1("real", n=8000, kappa=kappa, robot_sig=rsig)
            sap = eval_s1("sap", n=8000, kappa=kappa, robot_sig=rsig)
            row[f"robot={rsig}"] = dict(real=round(real["ood"], 4),
                                        sap=round(sap["ood"], 4),
                                        delta_pp=round(100 * (sap["ood"] - real["ood"]), 2))
        res["S1_sensitivity"][f"kappa={kappa}"] = row
        print(f"    kappa={kappa}: " + "  ".join(
            f"{k}:{v['delta_pp']:+.1f}pp" for k, v in row.items()))

    print("\n  boundary: unseen-object novelty (augmentation cannot fix) ==")
    res["S1_boundary_unseen_object"] = {}
    for pn in (0.0, 0.15, 0.35):
        real = eval_s1("real", n=8000, p_novel=pn)
        sap = eval_s1("sap", n=8000, p_novel=pn)
        res["S1_boundary_unseen_object"][f"p_novel={pn}"] = dict(
            real=round(real["all"], 4), sap=round(sap["all"], 4),
            delta_pp=round(100 * (sap["all"] - real["all"]), 2))
        print(f"    p_novel={pn}: real {real['all']:.3f} sap {sap['all']:.3f} "
              f"({100*(sap['all']-real['all']):+.1f}pp)")

    print("\n== S2 FSC ==")
    res["S2_fsc"] = {
        "clean": eval_s2(rogue=False),
        "rogue": eval_s2(rogue=True),
    }
    for tag in ("clean", "rogue"):
        c = res["S2_fsc"][tag]
        print(f"  {tag}: warmup(ep<=.25) {c['warmup_to_0p25']}  final {c['final']}")
        print(f"        majority(final) {c['majority_final']}")

    print("\n== S3 scalability frontier ==")
    res["S3_scale"] = eval_s3()
    for N in (3, 8, 12, 20):
        s = res["S3_scale"]["static"][N]
        ad = res["S3_scale"]["adaptive"][N]
        print(f"  N={N:2d}: best static T={s['best_static_T']} succ={s['best_static_success']} "
              f"| adaptive T={ad['T']} rho={ad['rho']} p99={ad['p99_ms']}ms succ={ad['success']}")
    dyn = res["S3_scale"]["dynamic"]
    print("  time-varying fleet (N=3/20/8/20):")
    for T, v in dyn["static"].items():
        print(f"    static T={T:2d}: succ={v['success']} viol_frac={v['violation_frac']}")
    print(f"    adaptive   : succ={dyn['adaptive']['success']} "
          f"viol_frac={dyn['adaptive']['violation_frac']}")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
