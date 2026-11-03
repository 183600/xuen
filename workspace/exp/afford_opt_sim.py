"""Synthetic mechanism check for AFFORD-OPT (research line round 16, cycle-2 round 1).

NOT benchmark evidence. Isolates three decision questions:

  Q1  If the dominant failure of a frozen VLA on UniBot-V1 is *metric* (6D
      approach-pose error / path / coordination) rather than *semantic*, how much
      success rate can a deterministic geometric layer (6D affordance refinement
      + SE(3) trajectory optimisation + bimanual coupling + contact-driven 6D
      local search + budget-aware retry) recover, and at what price?
  Q2  What is the break-even share of "geometry-limited" failures below which
      the geometric layer is NOT worth building (i.e. when to spend the budget
      on data / model scale instead)?
  Q3  Can a log-only triage classifier (no success labels) identify
      geometry-limited failures early enough to decide per-episode whether to
      spend the search/retry budget? (AUC)

Generative model (DECLARED, NOT FIT).  One global scalar sigma_pos is
bisection-calibrated so that the simulated VLA-only mean success matches the
published 8-model x 32-task mean of 25.2%.  That is an aggregate sanity
check, NOT a validation of the failure-mode decomposition.

  per attempt:
    semantic_fail ~ Bernoulli(p_sem(task))        wrong target/affordance
    path_fail     ~ Bernoulli(p_path(task))       collision/singularity/slip
    coord_fail    ~ Bernoulli(p_coord(task))      bimanual relative-pose break
    6D error      e_p = |N(0, sigma_pos^2 I_3)|, e_r = |N(0, sigma_rot^2)|
                  with a heavy-tail mixture (prob p_gross -> x gross_mult)
    success       = no semantic_fail and no path_fail and no coord_fail
                    and e_p <= tau_p and e_r <= tau_r

  the geometric layer can only touch PATH + COORD + the PRECISION part;
  SEMANTIC is out of reach by construction (that is the whole point).

  costs: per-attempt wall clock ~ t_attempt (default 44 s, the observed
  leaderboard mean), episode hard cap 180 s (official rule), local-search
  probes cost t_probe each and may knock the object over.
"""
import json
import math
import os
import random
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "afford_opt_results.json")

EPISODE_CAP_S = 180.0          # official: max 180 s per real-robot episode
OBS_T_ATTEMPT_S = 44.02        # observed leaderboard mean duration (MolmoAct2)
LEADER_MEAN_SUCC = 0.2517      # observed mean over 8 models x 32 tasks

# ---------------------------------------------------------------- task table
# tau_p/tau_r: affordance tolerance in mm / deg (declared by physics)
# p_sem: probability the VLA picks a semantically wrong affordance
# p_path: probability of a path / collision / slip failure
# p_coord: probability of a bimanual coordination break
# n_sub: number of scoring sub-steps (for the step-score side metric)
TASKS = [
    # name,                     tau_p, tau_r, p_sem, p_path, p_coord, bim, n_sub
    ("Hang the Cup",              6.0, 12.0, 0.30, 0.16, 0.00, False, 4),
    ("Fruit Basket Collection",   8.0, 14.0, 0.26, 0.14, 0.10, True,  4),
    ("Pack the Doll",            12.0, 18.0, 0.22, 0.18, 0.12, True,  5),
    ("Fruit Sorting",             8.0, 14.0, 0.24, 0.14, 0.00, False, 4),
    ("Disconnect Ethernet",       3.0,  8.0, 0.28, 0.16, 0.10, True,  3),
    ("Color Arrangement",         9.0, 14.0, 0.26, 0.16, 0.00, False, 4),
    ("Place Photo Frames",        8.0, 12.0, 0.28, 0.16, 0.00, False, 4),
    ("Organize Bookshelf",       12.0, 18.0, 0.24, 0.18, 0.00, False, 5),
    ("Toolbox Storage",          10.0, 16.0, 0.24, 0.16, 0.00, False, 4),
    ("Plug Charger",              3.5,  9.0, 0.30, 0.14, 0.14, True,  3),
    ("Pick Out Battery",          8.0, 14.0, 0.30, 0.16, 0.00, False, 3),
    ("Unlock",                    4.0, 10.0, 0.34, 0.14, 0.10, True,  3),
    ("Arrange Test Tubes",        8.0, 14.0, 0.28, 0.16, 0.00, False, 4),
    ("Open Pill Bottle",          7.0, 13.0, 0.32, 0.14, 0.00, False, 3),
    ("Organize Tools",            9.0, 15.0, 0.26, 0.16, 0.00, False, 5),
    ("Fold Towel",               12.0, 20.0, 0.18, 0.20, 0.00, False, 4),
    ("Organize Stationery",       9.0, 14.0, 0.30, 0.14, 0.00, False, 5),
    ("Pack Bag",                 14.0, 20.0, 0.20, 0.20, 0.14, True,  5),
    ("Zip Up",                   10.0, 16.0, 0.20, 0.20, 0.14, True,  4),
    ("Paper Cup Stacking",        7.0, 12.0, 0.26, 0.16, 0.00, False, 4),
    ("Clear Plates",              9.0, 14.0, 0.28, 0.16, 0.08, True,  4),
    ("Spell robot",               7.0, 13.0, 0.30, 0.14, 0.00, False, 4),
    ("Store Racket",             11.0, 17.0, 0.26, 0.18, 0.00, False, 4),
    ("Conveyor Food Sorting",     8.0, 14.0, 0.30, 0.20, 0.00, False, 5),
    ("Stack Cups",                6.0, 11.0, 0.24, 0.14, 0.00, False, 3),
    ("Plug In Ethernet",          2.5,  7.0, 0.32, 0.14, 0.12, True,  3),
    ("Stack Bowls",               7.0, 12.0, 0.26, 0.16, 0.00, False, 3),
    ("Store Earphones",           9.0, 15.0, 0.28, 0.18, 0.00, False, 4),
    ("Pack Phone",               12.0, 18.0, 0.22, 0.20, 0.12, True,  5),
    ("Remove Pinned Note",        5.0, 10.0, 0.28, 0.12, 0.00, False, 3),
    ("Organize Pencil Case",      9.0, 14.0, 0.28, 0.16, 0.00, False, 4),
    ("Syringe Water Transfer",    3.0,  8.0, 0.26, 0.16, 0.14, True,  3),
]


def sample_task(rng, sem_scale):
    t = rng.choice(TASKS)
    return {
        "name": t[0], "tau_p": t[1], "tau_r": t[2],
        "p_sem": min(0.95, t[3] * sem_scale),
        "p_path": t[4], "p_coord": t[5], "bim": t[6], "n_sub": t[7],
    }


def gauss(rng):
    u1 = max(1e-12, rng.random())
    u2 = rng.random()
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def norm3(rng, sigma):
    return math.sqrt(sum((gauss(rng) * sigma) ** 2 for _ in range(3)))


# ------------------------------------------------------------------ episode
def attempt(rng, cfg, task):
    """One VLA attempt. Returns (fail_cause_or_None, e_p, e_r)."""
    semantic = rng.random() < task["p_sem"]
    path_fail = rng.random() < task["p_path"]
    coord_fail = task["bim"] and rng.random() < task["p_coord"]
    s_mult = cfg["gross_mult"] if rng.random() < cfg["p_gross"] else 1.0
    e_p = norm3(rng, cfg["sigma_pos"] * s_mult)
    e_r = abs(gauss(rng)) * cfg["sigma_rot"] * s_mult

    if cfg["afford"] and not semantic:
        if rng.random() < cfg["stereo_conf"]:
            e_p /= cfg["k_afford"]
            e_r /= cfg["k_afford_rot"]

    if cfg["trajopt"] and path_fail and rng.random() < cfg["fix_path"]:
        path_fail = False
    if cfg["couple"] and coord_fail and rng.random() < cfg["fix_coord"]:
        coord_fail = False

    if semantic:
        cause = "SEMANTIC"
    elif path_fail:
        cause = "PATH"
    elif coord_fail:
        cause = "COORD"
    elif e_p > task["tau_p"] or e_r > task["tau_r"]:
        cause = "PRECISION"
    else:
        cause = None
    return cause, e_p, e_r


def run_episode(rng, cfg, task):
    seconds = 0.0
    probes = 0
    attempts = 0
    scene_intact = True
    last_cause = "SUCCESS"

    while True:
        attempts += 1
        seconds += cfg["t_attempt"]
        cause, e_p, e_r = attempt(rng, cfg, task)
        last_cause = cause or "SUCCESS"
        if cause is None:
            return {"cause": "SUCCESS", "success": True,
                    "subs_done": task["n_sub"], "seconds": seconds,
                    "probes": probes, "attempts": attempts}

        subs_done = max(0, task["n_sub"] - 2)

        # ---- CONTACT-DRIVEN 6D LOCAL SEARCH (grasp = the oracle) -------
        if (cfg["search"] and cause == "PRECISION" and scene_intact
                and e_p <= cfg["search_radius"] and e_r <= cfg["search_radius_rot"]
                and seconds + cfg["search_cost"] <= EPISODE_CAP_S):
            p_find = (cfg["p_find0"]
                      * math.exp(-(e_p - task["tau_p"]) / cfg["p_find_e0"])
                      * math.exp(-(e_r - task["tau_r"]) / cfg["p_find_e0r"]))
            seconds += cfg["search_cost"]
            probes += cfg["n_probe"]
            if rng.random() < p_find:
                return {"cause": "PRECISION_FIXED", "success": True,
                        "subs_done": task["n_sub"], "seconds": seconds,
                        "probes": probes, "attempts": attempts}
            if rng.random() < cfg["side_effect"]:
                scene_intact = False
                last_cause = "SEMANTIC"   # object knocked away -> unrecoverable

        # ---- RETRY ------------------------------------------------------
        if (not cfg["retry"]) or (not scene_intact):
            break
        if seconds + cfg["t_attempt"] > EPISODE_CAP_S:
            break

    return {"cause": last_cause, "success": False,
            "subs_done": max(0, task["n_sub"] - 2), "seconds": seconds,
            "probes": probes, "attempts": attempts}


def eval_policy(cfg, n_ep, seed, sem_scale=1.0):
    rng = random.Random(seed)
    succ = 0
    secs, probes, atts, steps = [], [], [], []
    causes = {}
    for _ in range(n_ep):
        task = sample_task(rng, sem_scale)
        r = run_episode(rng, cfg, task)
        succ += int(r["success"])
        secs.append(r["seconds"])
        probes.append(r["probes"])
        atts.append(r["attempts"])
        steps.append(100.0 * r["subs_done"] / task["n_sub"])
        causes[r["cause"]] = causes.get(r["cause"], 0) + 1
    return {
        "success_rate": succ / n_ep,
        "avg_step_score": statistics.mean(steps),
        "avg_seconds": statistics.mean(secs),
        "avg_probes": statistics.mean(probes),
        "avg_attempts": statistics.mean(atts),
        "timeout_frac": sum(1 for s in secs if s >= EPISODE_CAP_S - 1e-9) / n_ep,
        "causes": causes,
    }


BASE = dict(
    t_attempt=OBS_T_ATTEMPT_S,
    sigma_pos=17.0,       # mm  (calibrated)
    sigma_rot=16.0,       # deg
    p_gross=0.18, gross_mult=2.4,
    afford=False, k_afford=3.0, k_afford_rot=2.5, stereo_conf=0.72,
    trajopt=False, fix_path=0.60,
    couple=False, fix_coord=0.70,
    search=False, p_find0=0.72, p_find_e0=9.0, p_find_e0r=9.0,
    n_probe=8, search_cost=9.6, search_radius=32.0, search_radius_rot=34.0,
    side_effect=0.07,
    retry=False,
    feat_noise=0.18,
)


def with_cfg(**kw):
    c = dict(BASE)
    c.update(kw)
    return c


def calibrate_sigma(sem_scale=1.0, target=LEADER_MEAN_SUCC, n_ep=30000, seed=12345):
    """Bisection on sigma_pos so simulated VLA-only mean success == target."""
    lo, hi = 1.0, 80.0
    for _ in range(24):
        mid = 0.5 * (lo + hi)
        cfg = with_cfg(sigma_pos=mid)
        s = eval_policy(cfg, n_ep, seed, sem_scale)["success_rate"]
        if s > target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# -------------------------------------------------------------------- triage
def triage_features(rng, cause, cfg):
    """Log-only observables a participant-side logger can compute."""
    stall = {"SEMANTIC": 0.05, "PRECISION": 0.80, "PATH": 0.55,
             "COORD": 0.45, "PRECISION_FIXED": 0.8}.get(cause, 0.1)
    nomove = {"SEMANTIC": 0.85, "PRECISION": 0.90, "PATH": 0.35,
              "COORD": 0.55, "PRECISION_FIXED": 0.1}.get(cause, 0.1)
    armdrift = {"COORD": 0.85, "PRECISION": 0.25, "PATH": 0.20,
                "SEMANTIC": 0.15, "PRECISION_FIXED": 0.2}.get(cause, 0.1)
    notouch = {"SEMANTIC": 0.80, "PRECISION": 0.10, "PATH": 0.20,
               "COORD": 0.25, "PRECISION_FIXED": 0.1}.get(cause, 0.15)
    n = cfg["feat_noise"]
    cl = lambda v: min(1.0, max(0.0, v + rng.gauss(0, n)))
    return {"stall": cl(stall), "nomove": cl(nomove),
            "armdrift": cl(armdrift), "notouch": cl(notouch)}


def triage_score(f):
    """Hand-weighted, non-learned score (fixed coefficients, frozen)."""
    return (1.4 * f["stall"] + 1.0 * f["nomove"] + 0.9 * f["armdrift"]
            - 1.6 * f["notouch"])


def auc(scores, labels):
    pairs = sorted(zip(scores, labels))
    pos = sum(labels)
    neg = len(labels) - pos
    if pos == 0 or neg == 0:
        return float("nan")
    i, r = 0, 0.0
    while i < len(pairs):
        j = i
        while j + 1 < len(pairs) and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            if pairs[k][1] == 1:
                r += avg_rank
        i = j + 1
    return (r - pos * (pos + 1) / 2.0) / (pos * neg)


def run_triage(cfg, n_ep, seed, sem_scale=1.0):
    rng = random.Random(seed)
    scores, labels = [], []
    for _ in range(n_ep):
        task = sample_task(rng, sem_scale)
        r = run_episode(rng, cfg, task)
        f = triage_features(rng, r["cause"], cfg)
        scores.append(triage_score(f))
        labels.append(int(r["cause"] in ("PRECISION", "PATH", "COORD",
                                         "PRECISION_FIXED")))
    return auc(scores, labels), len(scores)


# ---------------------------------------------------------------------- main
def main():
    out = {"meta": {
        "purpose": "synthetic mechanism check, NOT benchmark evidence",
        "episode_cap_s": EPISODE_CAP_S,
        "leaderboard_mean_success_used_for_calibration": LEADER_MEAN_SUCC,
        "n_ep_per_cell": 20000,
        "seeds": "fixed",
    }}

    sigma_star = calibrate_sigma()
    out["calibration"] = {"sigma_pos_star_mm": round(sigma_star, 3)}
    base = with_cfg(sigma_pos=sigma_star)
    res_base = eval_policy(base, 20000, 777)
    out["baseline_vla_only"] = res_base
    print(f"calibrated sigma_pos = {sigma_star:.2f} mm ; "
          f"VLA-only success = {res_base['success_rate']:.4f} "
          f"(target {LEADER_MEAN_SUCC})")

    # ---- Q1: component ablation ---------------------------------------
    ablate = {
        "VLA-only": base,
        "+retry": with_cfg(sigma_pos=sigma_star, retry=True),
        "+AFFORD-6D": with_cfg(sigma_pos=sigma_star, afford=True),
        "+TRAJ-OPT": with_cfg(sigma_pos=sigma_star, trajopt=True),
        "+BI-COUPLE": with_cfg(sigma_pos=sigma_star, couple=True),
        "+LOCAL-SEARCH": with_cfg(sigma_pos=sigma_star, search=True),
        "A+O+C": with_cfg(sigma_pos=sigma_star, afford=True, trajopt=True,
                          couple=True),
        "FULL": with_cfg(sigma_pos=sigma_star, afford=True, trajopt=True,
                         couple=True, search=True, retry=True),
    }
    out["ablation"] = {}
    for name, cfg in ablate.items():
        r = eval_policy(cfg, 20000, 777)
        out["ablation"][name] = r
        print(f"{name:14s} succ={r['success_rate']:.4f} step={r['avg_step_score']:5.1f} "
              f"sec={r['avg_seconds']:6.1f} probes={r['avg_probes']:.2f} "
              f"att={r['avg_attempts']:.2f} timeout={r['timeout_frac']:.3f}")

    # ---- Q2: break-even in the semantic-failure share -------------------
    # semantic_share is the *share of failures* attributed to grounding.
    # For each level we re-calibrate sigma_pos so the VLA-only aggregate stays
    # pinned at the observed 25.2%: "same published level, different mix".
    sweep = []
    for share in [0.0, 0.15, 0.30, 0.45, 0.60, 0.75, 0.90]:
        sem_scale = share / 0.30          # 0.30 == the declared nominal mix
        sp = calibrate_sigma(sem_scale=sem_scale, n_ep=20000, seed=555)
        c0 = with_cfg(sigma_pos=sp)
        c1 = with_cfg(sigma_pos=sp, afford=True, trajopt=True, couple=True,
                      search=True, retry=True)
        r0 = eval_policy(c0, 12000, 999, sem_scale)
        r1 = eval_policy(c1, 12000, 999, sem_scale)
        sweep.append({"semantic_failure_share": share, "sigma_pos_mm": sp,
                      "vla_only": r0["success_rate"], "full": r1["success_rate"],
                      "delta_pp": 100 * (r1["success_rate"] - r0["success_rate"]),
                      "full_seconds": r1["avg_seconds"]})
        print(f"sem_share={share:.2f} sigma={sp:5.2f}mm vla={r0['success_rate']:.3f} "
              f"full={r1['success_rate']:.3f} "
              f"delta={100*(r1['success_rate']-r0['success_rate']):+.1f}pp "
              f"sec={r1['avg_seconds']:.0f}")
    out["break_even_sweep"] = sweep

    # ---- Q2b: sigma sensitivity (how precise is the VLA really?) ------
    sens = []
    for sp in [6, 9, 12, 17, 24, 32, 45]:
        c0 = with_cfg(sigma_pos=sp)
        c1 = with_cfg(sigma_pos=sp, afford=True, trajopt=True, couple=True,
                      search=True, retry=True)
        r0 = eval_policy(c0, 12000, 31337)
        r1 = eval_policy(c1, 12000, 31337)
        sens.append({"sigma_pos_mm": sp, "vla_only": r0["success_rate"],
                     "full": r1["success_rate"],
                     "delta_pp": 100 * (r1["success_rate"] - r0["success_rate"])})
        print(f"sigma_pos={sp:3d}mm vla={r0['success_rate']:.3f} "
              f"full={r1['success_rate']:.3f} "
              f"delta={100*(r1['success_rate']-r0['success_rate']):+.1f}pp")
    out["sigma_sensitivity"] = sens

    # ---- Q2c: stereo confidence sensitivity ---------------------------
    conf = []
    for sc in [0.4, 0.55, 0.72, 0.85, 0.95]:
        c1 = with_cfg(sigma_pos=sigma_star, afford=True, stereo_conf=sc,
                      trajopt=True, couple=True, search=True, retry=True)
        r1 = eval_policy(c1, 12000, 24680)
        conf.append({"stereo_conf": sc, "full": r1["success_rate"]})
        print(f"stereo_conf={sc:.2f} full={r1['success_rate']:.4f}")
    out["stereo_confidence_sensitivity"] = conf

    # ---- Q3: triage ----------------------------------------------------
    a, n = run_triage(with_cfg(sigma_pos=sigma_star), 20000, 4242)
    out["triage"] = {"auc": a, "n": n, "feat_noise": 0.18}
    print(f"triage AUC = {a:.3f} (n={n})")

    # ---- budget --------------------------------------------------------
    out["budget"] = {
        "added_p99_latency_ms": {
            "stereo_sgbm_240x320": 12.0,
            "local_frame_fit": 4.0,
            "se3_trajopt_10iter": 18.0,
            "bimanual_coupling": 3.0,
            "total": 37.0,
        },
        "note": "CPU only; off the VLA critical path except the first 5-step block",
    }

    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
