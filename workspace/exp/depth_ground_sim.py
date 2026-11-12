"""Synthetic mechanism check for DEPTH-GROUND (round 55).

NOT benchmark evidence. Isolates one question:
round 54's action profile alpha_S and joint certificate J assume the action
space is *observed*. On a real robot it is inferred from a depth camera whose
depth is missing on transparent / specular / black / thin materials. Gazebo
renders those materials as solid, so alpha_S calibrated in Gazebo is
over-confident. Does an explicit depth-observability field + criticality-
weighted gate + budgeted active probing reduce unsafe deployments (phantom
affordances) while retaining coverage, versus trusting the round-54 cert?

Model (declared, not fit):
  - N scene points; each has true occupancy (free/occupied), a material
    (matte/glass/mirror/black), and a criticality kappa in [0,1]
    (support / contact / collision region).
  - depth camera: a point is observed with prob 1-dropout(material); observed
    depth carries small noise and misclassifies with prob P_ERR.
  - missing depth is "optimistically inpainted" as free with prob P_FILL
    (the phantom mechanism: glass looks like support).
  - Gazebo baseline: alpha_S calibrated on ideal depth (no dropout), so the
    certificate assumes observed == true. At runtime it executes every point
    perceived free.
  - DEPTH-GROUND: execute a critical point only if observed, or certified by a
    probe. Non-critical points are executed optimistically (criticality-
    weighted gate).
  - active probe: on an unobserved critical point a probe reveals truth with
    accuracy P_PROBE at unit cost; budget B per episode; unprobed dropouts are
    refused (conservative).
Metrics over episodes: unsafe (executed a phantom critical action),
coverage (executed truly-free critical points), success (all free critical
executed and no unsafe), probe cost.
"""
import json
import random

SEED = 20261112
EPISODES = 4000
N = 300
CRIT_P = 0.12
FREE_P = 0.65
MATERIALS = {
    # name: (prob, dropout, weight)
    "matte": (0.60, 0.02),
    "glass": (0.15, 0.55),
    "mirror": (0.15, 0.50),
    "black": (0.10, 0.35),
}
P_ERR = 0.01       # observed-depth misclassification
P_FILL = 0.60      # missing depth inpainted as free (phantom)
P_PROBE = 0.95     # naive active probe accuracy
P_PROBE_CERT = 0.99  # certified (multi-view + touch) probe accuracy
KAPPA_MIN = 0.5    # criticality gate threshold


def sample_scene(rng):
    pts = []
    for _ in range(N):
        free = rng.random() < FREE_P
        kappa = 1.0 if rng.random() < CRIT_P else rng.random() * 0.4
        r = rng.random()
        acc = 0.0
        for name, (p, drop) in MATERIALS.items():
            acc += p
            if r <= acc:
                mat, dropout = name, drop
                break
        pts.append((free, kappa, dropout))
    return pts


def perceive(pts, rng):
    """Return (perceived_free, observed) under the real depth camera."""
    perc, observed = [], []
    for free, kappa, dropout in pts:
        if rng.random() < dropout:
            observed.append(False)
            # missing depth: optimistic inpainting
            perc.append(rng.random() < P_FILL)
        else:
            observed.append(True)
            if rng.random() < P_ERR:
                perc.append(not free)
            else:
                perc.append(free)
    return perc, observed


def run_episode(rng, mode, budget, p_probe=P_PROBE):
    pts = sample_scene(rng)
    perc, observed = perceive(pts, rng)
    executed = [False] * N
    cost = 0
    for i, (free, kappa, dropout) in enumerate(pts):
        if kappa < KAPPA_MIN:
            # non-critical: optimistic execution (criticality-weighted)
            executed[i] = perc[i]
            continue
        if mode == "baseline":
            executed[i] = perc[i]
        elif mode == "depth_ground_noprobe":
            # only observed depth is trusted; dropouts refused
            executed[i] = perc[i] if observed[i] else False
        elif mode.startswith("depth_ground_probe"):
            if observed[i]:
                executed[i] = perc[i]
            elif cost < budget:
                cost += 1
                truth = free if rng.random() < p_probe else (not free)
                executed[i] = truth
            else:
                executed[i] = False
        else:
            raise ValueError(mode)
    unsafe = any(executed[i] and not pts[i][0] and pts[i][1] >= KAPPA_MIN
                 for i in range(N))
    true_free_crit = [i for i in range(N)
                      if pts[i][0] and pts[i][1] >= KAPPA_MIN]
    coverage = (sum(executed[i] for i in true_free_crit) /
                max(1, len(true_free_crit)))
    phantom = sum(executed[i] and not pts[i][0] and pts[i][1] >= KAPPA_MIN
                  for i in range(N))
    success = (not unsafe) and coverage >= 0.95
    return unsafe, coverage, phantom, success, cost


def summarize(rng, mode, budget, p_probe=P_PROBE):
    u = c = ph = s = cost = 0.0
    for _ in range(EPISODES):
        uu, cc, pp, ss, co = run_episode(rng, mode, budget, p_probe)
        u += uu
        c += cc
        ph += pp
        s += ss
        cost += co
    return {
        "mode": mode,
        "probe_budget": budget,
        "p_probe": p_probe,
        "unsafe_rate": round(u / EPISODES, 4),
        "coverage": round(c / EPISODES, 4),
        "phantom_per_episode": round(ph / EPISODES, 3),
        "success_rate": round(s / EPISODES, 4),
        "probe_cost": round(cost / EPISODES, 3),
    }


def main():
    rows = []
    for mode, budget, pp in [("baseline", 0, 0.0),
                             ("depth_ground_noprobe", 0, 0.0),
                             ("depth_ground_probe_naive", 30, P_PROBE),
                             ("depth_ground_probe_cert", 10, P_PROBE_CERT),
                             ("depth_ground_probe_cert", 30, P_PROBE_CERT),
                             ("depth_ground_probe_cert", 60, P_PROBE_CERT)]:
        rng = random.Random(SEED)
        rows.append(summarize(rng, mode, budget, pp))
    out = {"seed": SEED, "episodes": EPISODES, "N": N,
           "crit_p": CRIT_P, "free_p": FREE_P, "p_fill": P_FILL,
           "p_err": P_ERR, "p_probe": P_PROBE, "rows": rows}
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
