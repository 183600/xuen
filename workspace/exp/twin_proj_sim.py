"""Round-16 synthetic mechanism check: TWIN-PROJ (online digital-twin projection).

NOT benchmark evidence. Isolates one question:
  When a frozen VLA grounds/manipulates with per-stage geometric error, does
  an *online metric digital twin* (reconstructed from the rectified head stereo
  pair + FK) let us REPAIR the action chunk by projecting it onto the twin's
  feasible/manipulation target -- better than (a) raw VLA, (b) round-15-style
  verify-and-replan gating -- and where is the failure boundary?

Declared generative model (not fit to the leaderboard):
  - task classes: free / precision / deformable
  - episode = S sequential stages; each stage needs EE target accuracy <= tau
  - VLA per-stage error = semantic bias b_vec (mis-grounding, prob q_miss)
                          + zero-mean noise N(0, sigma_v^2 I)
  - twin per-stage target error = N(0, sigma_t^2 I), independent when opaque;
    when the object is transparent/reflective the twin is unreliable
    (sigma_t large, confidence c low) and may share the VLA's bias.
  - "projection" replaces the geometric target by the twin estimate (hard) or a
    confidence-weighted blend (soft).  It is gated by twin confidence c >= c0.
  - "verify" is a round-15-style comparator: on large VLA/twin disagreement it
    re-plans once (recovers the semantic miss with prob p_replan).
  - progress (partial credit) = passed stages + partial current stage; this
    mirrors the observed leaderboard property step_score ~= 1.31 * success.

Evidence level B: reproduces a mechanism and its boundary, not the real board.
"""
import json
import math
import os
import random
import statistics as st

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "twin_proj_results.json")


# --------------------------------------------------------------------------
# task profiles
# --------------------------------------------------------------------------
# tau   : per-stage position tolerance (m)
# sv    : VLA zero-mean per-stage error sigma (m)
# st_op : twin per-stage error sigma when object is opaque / textured (m)
# st_tr : twin error sigma for transparent / reflective / featureless objects
# qmiss : prob. a stage triggers a semantic mis-grounding bias
# qtr   : prob. an object is transparent/reflective (twin degraded)
# bmag  : range of semantic bias magnitude (m)
PROFILE = {
    "free":       dict(weight=0.50, tau=0.050, sv=0.015, st_op=0.006, st_tr=0.050,
                       qmiss=0.20, qtr=0.15, bmag=(0.020, 0.080), stages=(2, 3)),
    "precision":  dict(weight=0.30, tau=0.012, sv=0.012, st_op=0.004, st_tr=0.045,
                       qmiss=0.25, qtr=0.20, bmag=(0.020, 0.080), stages=(1, 2, 3)),
    "deformable": dict(weight=0.20, tau=0.030, sv=0.025, st_op=0.020, st_tr=0.060,
                       qmiss=0.30, qtr=0.15, bmag=(0.020, 0.080), stages=(2, 3, 4)),
}
# For deformable tasks the twin cannot represent the *shape*; projection only
# fixes position, so even a perfect pose twin leaves a task-specific residual.
DEFORM_RESIDUAL = 0.030   # sigma of un-modellable deformation residual (m)

C0 = 0.5          # confidence gate threshold
D0 = 0.030        # VLA/twin disagreement threshold for "detect semantic miss" (m)
P_REPLAN = 0.55   # prob. a single re-plan recovers a semantic miss
RHO_SHARED = 1.00 # OOD-G: correlation between VLA bias and twin error


def unit(rng):
    a = rng.uniform(0, 2 * math.pi)
    return np.array([math.cos(a), math.sin(a)])


def run_episode(kind, policy, rng, soft=False, corr=False, rel_twin=1.0,
                rel_vla=1.0):
    p = PROFILE[kind]
    S = rng.choice(p["stages"])
    passed = 0
    progress = 0.0
    success = True
    replans = 0
    for _ in range(S):
        tau = p["tau"]
        # --- latent scene ---
        miss = rng.random() < p["qmiss"]
        b = unit(rng) * rng.uniform(*p["bmag"]) if miss else np.zeros(2)
        transparent = rng.random() < p["qtr"]

        # --- VLA output (target error) ---
        e_v = b + np.array([rng.gauss(0, p["sv"] * rel_vla),
                            rng.gauss(0, p["sv"] * rel_vla)])

        # --- twin: estimate + confidence ---
        if transparent:
            sigma_t = p["st_tr"] * rel_twin
            c = rng.uniform(0.00, 0.30)        # degraded perception -> low conf
        else:
            sigma_t = p["st_op"] * rel_twin
            c = rng.uniform(0.55, 1.00)        # good perception -> high conf
        if corr and miss:
            # OOD-G: twin shares the VLA's systematic bias (same wrong prior)
            e_t = RHO_SHARED * b + np.array([rng.gauss(0, sigma_t),
                                             rng.gauss(0, sigma_t)])
            if transparent:
                c = rng.uniform(0.70, 1.00)    # confidently wrong
        else:
            e_t = np.array([rng.gauss(0, sigma_t), rng.gauss(0, sigma_t)])

        # --- policy decision ---
        if kind == "deformable":
            # position projection cannot fix deformation
            e_deform = rng.gauss(0, DEFORM_RESIDUAL)
            e_deform_vec = unit(rng) * abs(e_deform)
        else:
            e_deform_vec = np.zeros(2)

        if policy == "vla":
            e_out = e_v
        elif policy == "verify":
            disagreement = np.linalg.norm(e_v - e_t)
            if disagreement > D0 and (transparent is False or corr) and rng.random() < P_REPLAN:
                replans += 1
                # a re-plan recovers the systematic bias but not the noise
                e_out = (b * 0.0) + np.array([rng.gauss(0, p["sv"]),
                                              rng.gauss(0, p["sv"])])
            else:
                e_out = e_v
        elif policy == "proj":
            if c >= C0:
                if soft:
                    lam = c
                    e_out = lam * e_t + (1 - lam) * e_v
                else:
                    e_out = e_t
            else:
                e_out = e_v
        elif policy == "proj_always":
            e_out = e_t
        elif policy == "proj_oracle":
            e_out = np.zeros(2)  # perfect twin
        else:
            raise ValueError(policy)

        err = np.linalg.norm(e_out + e_deform_vec)
        ok = err <= tau
        if ok:
            passed += 1
            progress += 1.0
        else:
            success = False
            partial = max(0.0, 1.0 - err / (4.0 * tau))
            progress += partial
            break  # a failed stage aborts the episode
    total = progress / S
    return success, total, passed, S, replans


def evaluate(kind, policy, n=20000, seed=11, **kw):
    rng = random.Random(seed)
    succ, prog, pass_frac = [], [], []
    for i in range(n):
        s, t, p, S, r = run_episode(kind, policy, rng, **kw)
        succ.append(1 if s else 0)
        prog.append(t)
        pass_frac.append(p / S)
    return dict(success=st.mean(succ), progress=st.mean(prog),
                stage_pass=st.mean(pass_frac),
                step_score_proxy=100 * st.mean(prog), n=n)


def main():
    policies = ["vla", "verify", "proj", "proj_always", "proj_oracle"]
    results = {"profiles": PROFILE, "policies": {}, "per_class": {},
               "sensitivity": {}, "soft_projection": {}, "oodg": {}}

    # ---- overall (mixture of task classes) ----
    print("=== overall task mixture ===")
    for pol in policies:
        agg_s = agg_p = agg_sp = 0.0
        for kind, p in PROFILE.items():
            r = evaluate(kind, pol)
            agg_s += p["weight"] * r["success"]
            agg_p += p["weight"] * r["progress"]
            agg_sp += p["weight"] * r["stage_pass"]
        results["policies"][pol] = dict(success=round(agg_s, 4),
                                        progress=round(agg_p, 4),
                                        stage_pass=round(agg_sp, 4))
        print(f"{pol:12s} success {agg_s:.3f}  progress {agg_p:.3f}  "
              f"stage_pass {agg_sp:.3f}  step_proxy {100*agg_p:.1f}")

    # ---- per class ----
    print("\n=== per task class (success / step_score_proxy) ===")
    for pol in policies:
        results["per_class"][pol] = {}
        row = []
        for kind in PROFILE:
            r = evaluate(kind, pol)
            results["per_class"][pol][kind] = dict(
                success=round(r["success"], 4),
                step_score_proxy=round(r["step_score_proxy"], 2))
            row.append(f"{kind[:4]}:{r['success']:.3f}/{r['step_score_proxy']:.1f}")
        print(f"{pol:12s} " + "  ".join(row))

    # ---- soft projection vs hard, at the mixture level ----
    print("\n=== soft (confidence-weighted) vs hard projection ===")
    for hard, soft in [(False, False), (True, False), (True, True)]:
        # hard==False -> raw vla handled elsewhere; here compare soft flag with proj
        tag = "hard" if (hard and not soft) else ("soft" if soft else "vla")
        if tag == "vla":
            pol, kwargs = "vla", {}
        else:
            pol, kwargs = "proj", {"soft": soft}
        agg_s = agg_sp = 0.0
        for kind, p in PROFILE.items():
            r = evaluate(kind, pol, **kwargs)
            agg_s += p["weight"] * r["success"]
            agg_sp += p["weight"] * r["step_score_proxy"]
        results["soft_projection"][tag] = dict(success=round(agg_s, 4),
                                               step_score_proxy=round(agg_sp, 2))
        print(f"{tag:5s} success {agg_s:.3f}  step_proxy {agg_sp:.1f}")

    # ---- confidence gate threshold sweep ----
    print("\n=== confidence gate c0 sweep (proj, mixture success) ===")
    results["confidence_sweep"] = {}
    for c0 in (0.0, 0.3, 0.5, 0.7, 0.9):
        globals()["C0"] = c0
        agg_s = sum(PROFILE[k]["weight"] * evaluate(k, "proj")["success"]
                    for k in PROFILE)
        results["confidence_sweep"][f"c0={c0}"] = round(agg_s, 4)
        print(f"c0={c0}: proj success {agg_s:.3f}")
    globals()["C0"] = 0.5

    # ---- sensitivity: twin quality (rel_twin) and VLA quality (rel_vla) ----
    print("\n=== sensitivity: rel_twin x rel_vla (mixture success) ===")
    for rel_t in (0.5, 1.0, 2.0, 4.0):
        row = {}
        for rel_v in (0.75, 1.0, 1.5):
            s_proj = sum(PROFILE[k]["weight"] *
                         evaluate(k, "proj", rel_twin=rel_t, rel_vla=rel_v)["success"]
                         for k in PROFILE)
            s_vla = sum(PROFILE[k]["weight"] *
                        evaluate(k, "vla", rel_twin=rel_t, rel_vla=rel_v)["success"]
                        for k in PROFILE)
            row[f"rel_vla={rel_v}"] = dict(
                vla=round(s_vla, 4), proj=round(s_proj, 4),
                delta_pp=round(100 * (s_proj - s_vla), 2))
        results["sensitivity"][f"rel_twin={rel_t}"] = row
        print(f"rel_twin={rel_t}: " +
              "  ".join(f"{k}: d={v['delta_pp']:+.1f}pp" for k, v in row.items()))

    # ---- OOD-G boundary: correlated twin ----
    print("\n=== OOD-G: twin shares VLA's wrong prior (corr=True) ===")
    for pol in ["vla", "proj", "proj_always", "proj_oracle"]:
        agg_s = sum(PROFILE[k]["weight"] *
                    evaluate(k, pol, corr=True)["success"] for k in PROFILE)
        results["oodg"][pol] = dict(success=round(agg_s, 4))
        print(f"{pol:12s} success {agg_s:.3f}")

    # ---- stereo depth-error sanity (justifies sigma_t magnitudes) ----
    print("\n=== stereo depth error sigma_z = z^2 * sigma_d / (f*b) ===")
    f, b = 600.0, 0.060  # focal px (approx), baseline m
    stereo = {}
    for z in (0.5, 0.7, 1.0):
        for sd in (0.1, 0.25, 0.5, 2.0):
            sz = z * z * sd / (f * b)
            stereo[f"z={z},sigma_d={sd}px"] = round(sz * 1000, 2)
    results["stereo_depth_error_mm"] = stereo
    for k, v in stereo.items():
        print(f"  {k:24s} -> {v:6.2f} mm")

    json.dump(results, open(OUT, "w"), indent=2)
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
