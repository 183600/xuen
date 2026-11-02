"""Synthetic mechanism check for SWARM-VLA (round 16).

NOT benchmark evidence.  Isolates one question:
when a frozen single-model policy is sampled K times per decision and the
evaluator gives ~180 s per task (leaderboard average is ~44 s), can a
population of candidates + multi-view verification + time-budgeted retry
improve success without violating the single-model rule?

The model is deliberately conservative about retries: a failed attempt can
leave the episode "stuck" in the same failure mode, and only an active probe
(which costs time and is imperfect) can clear it.  This is the main reason
blind retry does not dominate.

Generative model (declared, not fit):
  - episode mode: ordinary (independent candidate errors) or shared-grounding
    (OOD-G: every candidate has the same wrong target prior).
  - K candidate action scalars: good candidates cluster at 0, bad ones at a
    random offset.  The medoid is the consensus action.
  - verification score: good ~ N(1,1), bad ~ N(0,1); an independent wrist
    view can veto a shared-grounding episode with prob wrist_vis*wrist_se;
    a probe costs time and clears the shared/stuck mode with prob probe_fix.
  - execution: good candidate succeeds with p_succ_good, bad with
    p_succ_bad, shared-grounding with p_succ_shared; a stuck episode scales
    success by stuck_scale.
  - after a failure, the episode becomes stuck with prob p_persist
    (p_persist_shared for shared-grounding).
  - human disturbance occurs with prob human_rate; a yield policy detects it
    with prob yield_detect, waits, and resumes with prob yield_recover.
  - time: attempt 8 s, each candidate 0.4 s, each verification 0.1 s,
    probe 3 s, wait 4 s; policy budget 60 s (hard evaluator cap 180 s).
"""
import json, os, random

OUT = os.path.join(os.path.dirname(__file__), "swarm_results.json")

DEFAULTS = dict(
    p_good=0.50, p_succ_good=0.80, p_succ_bad=0.10, p_succ_shared=0.05,
    rho_oodg=0.25, wrist_vis=0.50, wrist_se=0.60, probe_fix=0.30,
    p_persist=0.80, p_persist_shared=0.95, stuck_scale=0.05,
    human_rate=0.20, yield_detect=0.75, yield_recover=0.60,
    p_disturb_fail=0.80, K=5, c_cand=0.4, c_ver=0.1,
    t_attempt=8.0, t_probe=3.0, t_wait=4.0, T_policy=60.0,
    score_thr=0.5, max_attempts=2,
)

POLICIES = [
    "base", "retry", "kmedoid", "kmedoid_retry",
    "kverify", "kverify_retry", "kverify_retry_yield",
]


def cands(rng, P, shared):
    out = []
    for _ in range(P["K"]):
        good = (not shared) and (rng.random() < P["p_good"])
        if good:
            out.append((rng.gauss(0.0, 0.20), True, rng.gauss(1.0, 1.0)))
        else:
            off = -1.0 if rng.random() < 0.5 else 1.0
            out.append((rng.gauss(off, 0.80), False, rng.gauss(0.0, 1.0)))
    return out


def medoid(cs):
    return min(cs, key=lambda c: sum(abs(c[0] - b[0]) for b in cs))


def choose(cs, policy, P):
    if policy in ("base", "retry"):
        return cs[0]
    if policy in ("kmedoid", "kmedoid_retry"):
        return medoid(cs)
    top = max(cs, key=lambda c: c[2])
    if top[2] >= P["score_thr"]:
        return top
    ordered = sorted(cs, key=lambda c: c[2], reverse=True)
    return medoid(ordered[: max(1, len(ordered) // 2)])


def attempt(rng, P, policy, shared, stuck, human, attempt_idx):
    """Return (success, seconds, probed, stuck_after, shared_after)."""
    t = 0.0
    do_verify = policy in ("kverify", "kverify_retry", "kverify_retry_yield")
    do_yield = policy == "kverify_retry_yield"
    probed = False
    stuck_after = stuck
    shared_after = shared

    cs = cands(rng, P, shared)
    t += P["K"] * P["c_cand"]

    if do_verify:
        t += P["K"] * P["c_ver"]
        need_probe = max(c[2] for c in cs) < P["score_thr"]
        if shared and rng.random() < P["wrist_vis"] * P["wrist_se"]:
            need_probe = True
        if need_probe:
            probed = True
            t += P["t_probe"]
            if rng.random() < P["probe_fix"]:
                shared_after = False
                stuck_after = False
            cs = cands(rng, P, shared_after)
            t += P["K"] * P["c_cand"]

    chosen = choose(cs, policy, P)

    if human:
        if do_yield and rng.random() < P["yield_detect"]:
            t += P["t_wait"]
            if rng.random() >= P["yield_recover"]:
                return False, t + P["t_attempt"], probed, stuck_after, shared_after
        elif rng.random() < P["p_disturb_fail"]:
            return False, t + P["t_attempt"], probed, stuck_after, shared_after

    t += P["t_attempt"]
    if shared_after:
        p = P["p_succ_shared"]
    elif chosen[1]:
        p = P["p_succ_good"]
    else:
        p = P["p_succ_bad"]
    if stuck_after:
        p *= P["stuck_scale"]
    p *= 0.90 ** attempt_idx
    return (rng.random() < p), t, probed, stuck_after, shared_after


def run(policy, P, n, seed):
    rng = random.Random(seed)
    succ = 0
    times = []
    probes = 0
    attempts_total = 0
    for _ in range(n):
        shared0 = rng.random() < P["rho_oodg"]
        human = rng.random() < P["human_rate"]
        t = 0.0
        ok = False
        k = 0
        stuck = False
        shared = shared0
        while t < P["T_policy"] and k < P["max_attempts"]:
            s, dt, pr, stuck_after, shared_after = attempt(
                rng, P, policy, shared, stuck, human, k)
            t += dt
            k += 1
            probes += int(pr)
            if s:
                ok = True
                break
            # a failed attempt may leave the scene in the same failure mode
            if rng.random() < (P["p_persist_shared"] if shared else P["p_persist"]):
                stuck = True
            shared = shared_after
            stuck = stuck or stuck_after
            if policy in ("base", "kmedoid", "kverify"):
                break
        succ += int(ok)
        times.append(min(t, P["T_policy"]))
        attempts_total += k
    return dict(success=succ / n, time=sum(times) / n,
                probes_per_ep=probes / n, attempts_per_ep=attempts_total / n)


def main():
    n = 10000
    grid = []
    for rho in (0.0, 0.25, 0.50):
        for vis in (0.0, 0.60, 0.90):
            for human in (0.0, 0.20):
                P = dict(DEFAULTS, rho_oodg=rho, wrist_vis=vis, human_rate=human)
                row = {"rho_oodg": rho, "wrist_vis": vis, "human_rate": human,
                       "policies": {}}
                for pol in POLICIES:
                    seed = 1000 + int(rho * 100) + int(vis * 10) + int(human * 3) + abs(hash(pol)) % 100
                    row["policies"][pol] = run(pol, P, n, seed)
                grid.append(row)
    P = dict(DEFAULTS)
    headline = {pol: run(pol, P, 20000, 7) for pol in POLICIES}
    out = {"note": "synthetic mechanism check; not benchmark evidence; magnitudes not calibrated",
           "n_per_cell": n, "headline_n": 20000,
           "defaults": DEFAULTS, "headline": headline, "grid": grid}
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)
    print("WROTE", OUT)
    print("\nHEADLINE (default cell, n=20000)")
    print(f"{'policy':24} {'succ':>6} {'time_s':>7} {'succ/time':>10} {'probe':>7} {'att':>5}")
    for pol in POLICIES:
        r = headline[pol]
        print(f"{pol:24} {r['success']*100:5.1f}% {r['time']:7.1f} {r['success']/max(r['time'],1e-9):10.4f} {r['probes_per_ep']:7.2f} {r['attempts_per_ep']:5.2f}")
    print("\nGRID success (%) base / retry / kmedoid / kverify / kverify_retry / kverify_retry_yield")
    for row in grid:
        ps = row["policies"]
        print(f"rho={row['rho_oodg']:.2f} vis={row['wrist_vis']:.2f} hum={row['human_rate']:.1f}  " +
              " ".join(f"{ps[p]['success']*100:5.1f}" for p in
                       ["base","retry","kmedoid","kverify","kverify_retry","kverify_retry_yield"]) +
              f"  | t_yield={ps['kverify_retry_yield']['time']:.1f}s")


if __name__ == "__main__":
    main()
