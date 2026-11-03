#!/usr/bin/env python3
"""Synthetic mechanism check for TRI-VLA (round 16).

NOT benchmark evidence. Isolates one question: when the semantic map and
the VLA share the same wrong prior (round-15 OOD-G, Prop. 7 boundary),
can an independent deterministic 6D-pose source plus a base SHUTTLE (a
second viewpoint) move the information-set boundary, and does Mondrian
(per-task-family) conformal calibration fix the family-level
miscalibration that a single global threshold suffers under multi-task
residual heterogeneity?

Generative model (declared, not fit; extends exp/zest_sim.py):
  - episode type: ID (+15% noisy), OOD-exec, OOD-semantic (map right,
    VLA wrong), OOD-G view-fragile (map+VLA wrong together, single-view
    pose source also fooled, second view corrects with prob P_FIX),
    OOD-G view-stable (pose source shares the error: undetectable, the
    honest boundary).
  - task families A/B (60/40): family B (insert/open-like) has higher ID
    residual mean and 20% contact spikes -> a single global conformal
    threshold is dragged up by B and goes blind on A; Mondrian
    calibrates q_alpha per family.  This is the multi-task axis.
  - 6D pose source: deterministic geometric judge of which object the
    commanded gripper pose fits; misidentification prob EPS_POSE1
    (single view) / EPS_POSE2 (after shuttle: larger effective baseline,
    Prop. 11); its confidence is low exactly in OOD-G scenes.
  - SHUTTLE: pays C_SH once per episode for a second viewpoint.
  - Conflict gate: two consecutive SERVO steps whose pose target differs
    from the map/VLA target -> lock onto the pose source's target and
    fall back to geometric primitives; fused pose (round-16 upgrade)
    boosts primitive success by G_BOOST when the locked target is the
    true one.  FALLBACK toward a wrong target succeeds with prob 0.20.
"""
import os, random, math, json, statistics, bisect

# ---------- world parameters (declared) ----------
N_OBJ = 4                 # candidate objects on the table
FAM_B_FRAC = 0.40         # share of task family B (insert/open-like)
SPIKE_PROB = 0.20         # family-B contact-spike probability (ID)
SPIKE_AMP = 1.00          # spike amplitude on the residual mean
EPS_POSE1 = 0.03          # pose-source mis-ID, single view
EPS_POSE2 = 0.015         # pose-source mis-ID, two views (baseline gain)
P_FIX = 0.85              # cross-view correction prob, view-fragile OOD-G
G_BOOST = 1.15            # fused-pose primitive success boost
C_SH = 1.0                # SHUTTLE cost (one second viewpoint)

TYPE_LIST = ["id", "id_noisy", "ood_exec", "ood_sem", "ood_gv", "ood_gs"]


def clip(x, lo=0.0, hi=3.0):
    return max(lo, min(hi, x))


def quantile(xs, q):
    ys = sorted(xs)
    if not ys:
        return 0.0
    i = min(len(ys) - 1, max(0, int(math.ceil(q * len(ys))) - 1))
    return ys[i]


def sample_episode(rng, pi, rho, mapok_frac, v_frac):
    fam = "B" if rng.random() < FAM_B_FRAC else "A"
    if rng.random() >= pi:
        return fam, "id_noisy" if rng.random() < 0.15 else "id"
    if rng.random() >= rho:
        return fam, "ood_exec"
    if rng.random() < mapok_frac:
        return fam, "ood_sem"
    return fam, ("ood_gv" if rng.random() < v_frac else "ood_gs")


def type_params(t, fam):
    """(c_mean, g_mean, residual mean triple, conf_low)"""
    mu = 0.28 if fam == "B" else 0.15
    if t in ("id", "id_noisy"):
        return 0.80, 0.50, (mu, mu, mu), False
    if t == "ood_exec":
        return 0.30, 0.60, (0.70, 0.70, 0.50), False
    if t == "ood_sem":
        return 0.30, 0.60, (0.20, 0.20, 0.80), False
    # ood_gv / ood_gs: residuals look ID (silent), competence low
    return 0.30, 0.30, (mu, mu, mu), True


def judge_pose(rng, truth, eps):
    """Deterministic 6D-pose source, with a misidentification error."""
    if rng.random() < eps:
        return rng.choice([o for o in range(N_OBJ) if o != truth])
    return truth


def run_episode(fam, t, policy, rng, B=10.0, q=4.2, c_sh=C_SH,
                fb_cost=1.2, g_scale=1.0):
    cm, gm, mu, conf_low = type_params(t, fam)
    sig = 0.40 if t == "id_noisy" else (0.12 if fam == "B" else 0.08)
    c_true = clip(rng.gauss(cm, 0.08), 0.0, 1.0)
    g_true = clip(rng.gauss(gm, 0.08), 0.0, 1.0)
    p_need = 3.0
    tstar = rng.randrange(N_OBJ)
    j = (tstar + 1 + rng.randrange(N_OBJ - 1)) % N_OBJ
    if t in ("id", "id_noisy", "ood_exec"):
        map_t = vla_t = tstar; pose1 = pose2 = tstar
    elif t == "ood_sem":
        map_t, vla_t = tstar, j; pose1 = pose2 = tstar
    elif t == "ood_gv":
        map_t = vla_t = j
        pose1 = j
        pose2 = tstar if rng.random() < P_FIX else j
    else:  # ood_gs: nobody can detect (view-stable shared error)
        map_t = vla_t = j; pose1 = pose2 = j

    alpha, k, h = 0.12, 0.05, 2.5
    progress = spent = 0.0
    raw_win = []; cusum = 0.0; mode = "vla"; dwell = 0
    bought2 = False; streak = 0; locked = False
    g_used = 0.0; lock_step = 0; shuttles = 0
    max_z = 0.0; conflict_ever = False; lowconf_ever = False
    corrected = False; surp = 0; serv = 0; steps = 0

    while spent < B - 1e-9 and progress < p_need:
        steps += 1
        if steps > 200:
            break
        spike = SPIKE_AMP if (fam == "B" and rng.random() < SPIKE_PROB) else 0.0
        act = None
        if policy == "vla":
            act = "servo"
        elif policy == "oracle":
            if t == "ood_gs":
                break                       # knows it is hopeless: stop
            if t == "ood_gv":
                act = "fallback"; g_used = min(1.0, g_true * g_scale)
            else:
                g_use = min(1.0, g_true * g_scale)
                act = "servo" if c_true * 0.9 >= g_use * 0.8 else "fallback"
                if act == "fallback":
                    g_used = g_use
        elif policy in ("zest", "mond"):
            if mode == "fallback":
                dwell += 1
                if dwell >= 3:
                    act = "servo"; mode = "probe"
                else:
                    act = "fallback"
                    g_used = (min(1.0, g_true * g_scale)
                              if map_t == tstar else 0.20)
            elif cusum > h:
                mode = "fallback"; dwell = 0; act = "fallback"
                g_used = (min(1.0, g_true * g_scale)
                          if map_t == tstar else 0.20)
            else:
                act = "servo"
        else:  # tri / shuttle
            have2 = policy == "shuttle" and bought2
            truth = pose2 if have2 else pose1
            eps = EPS_POSE2 if have2 else EPS_POSE1
            conf = clip(rng.gauss(0.25 if conf_low else 0.90,
                                  0.10 if conf_low else 0.15), 0.0, 1.0)
            pj = judge_pose(rng, truth, eps)
            conflict = (pj != map_t) or (pj != vla_t)
            lowconf = conf < 0.5
            if locked:
                lock_step += 1
                if lock_step % 3 == 0 and pj == map_t and pj == vla_t:
                    locked = False; streak = 0
            if locked:
                act = "fallback"
            elif conflict or lowconf:
                conflict_ever |= conflict
                lowconf_ever |= lowconf
                if policy == "shuttle" and not bought2:
                    bought2 = True; shuttles += 1; spent += c_sh
                    conf = clip(rng.gauss(0.25 if conf_low else 0.90,
                                          0.10 if conf_low else 0.15),
                                0.0, 1.0)
                    pj = judge_pose(rng, pose2, EPS_POSE2)
                    conflict = (pj != map_t) or (pj != vla_t)
                    lowconf = conf < 0.5
                if conflict:
                    streak += 1
                    if streak >= 2:
                        locked = True; lock_step = 0
                        g_used = (min(1.0, g_true * G_BOOST * g_scale)
                                  if pj == tstar else 0.20)
                        if pj == tstar and t in ("ood_gv", "ood_sem"):
                            corrected = True
                        act = "fallback"
                    else:
                        act = "servo"     # wait one step for confirmation
                else:
                    streak = 0            # lowconf only: no conclusion
            else:
                streak = 0
            if act is None:               # residual CUSUM gate (zest path)
                if mode == "fallback":
                    dwell += 1
                    if dwell >= 3:
                        act = "servo"; mode = "probe"
                    else:
                        act = "fallback"
                        g_used = (min(1.0, g_true * g_scale)
                                  if map_t == tstar else 0.20)
                elif cusum > h:
                    mode = "fallback"; dwell = 0; act = "fallback"
                    g_used = (min(1.0, g_true * g_scale)
                              if map_t == tstar else 0.20)
                else:
                    act = "servo"

        # ---------- execute ----------
        if act == "servo":
            ok = rng.random() < c_true * 0.9
            rs = tuple(clip(rng.gauss(m + spike, sig)) for m in mu)
        elif act == "fallback":
            ok = rng.random() < clip(g_used * 0.8, 0.0, 1.0)
            rs = tuple(clip(rng.gauss(0.20, 0.10)) for _ in range(3))
        else:
            ok = False; rs = (0.0, 0.0, 0.0)
        if ok:
            progress += 1.0
        spent += 1.0 if act == "servo" else fb_cost

        # ---------- residual gate update (SERVO only) ----------
        if act == "servo":
            serv += 1
            s = sum(rs) / 3.0
            raw_win.append(s)
            if len(raw_win) > 10:
                raw_win.pop(0)
            med = statistics.median(raw_win)
            mad = statistics.median([abs(x - med) for x in raw_win])
            scale = 1.4826 * mad + 0.05
            z = s / scale
            if z > max_z:
                max_z = z
            if z > q:
                surp += 1
            cusum = max(0.0, cusum + (1 if z > q else 0) - alpha - k)
            if mode == "probe":
                if z <= q:
                    mode = "vla"; cusum = 0.0
                else:
                    mode = "fallback"; dwell = 0

    score = max_z + 3.0 * conflict_ever + 2.0 * lowconf_ever
    return dict(succ=progress >= p_need, spent=spent, score=score,
                corrected=corrected, shuttles=shuttles,
                surp=surp, serv=serv, fam=fam, type=t)


def calibrate(n=6000, seed=99):
    """Sliding-MAD self-normalized ID scores; per-family and global."""
    rng = random.Random(seed)
    zA, zB, zmix = [], [], []
    for _ in range(n):
        fam = "B" if rng.random() < FAM_B_FRAC else "A"
        noisy = rng.random() < 0.15
        sig = 0.40 if noisy else (0.12 if fam == "B" else 0.08)
        mu = 0.28 if fam == "B" else 0.15
        win = []
        for _ in range(6):
            spike = SPIKE_AMP if (fam == "B" and rng.random() < SPIKE_PROB) else 0.0
            s = sum(clip(rng.gauss(mu + spike, sig)) for _ in range(3)) / 3.0
            win.append(s)
            w10 = win[-10:]
            med = statistics.median(w10)
            mad = statistics.median([abs(x - med) for x in w10])
            z = s / (1.4826 * mad + 0.05)
            zmix.append(z)
            (zA if fam == "A" else zB).append(z)
    return quantile(zA, 0.90), quantile(zB, 0.90), quantile(zmix, 0.90)


def auroc(pos, neg):
    if not pos or not neg:
        return 0.5
    neg_sorted = sorted(neg)
    wins = 0.0
    for x in pos:
        i = bisect.bisect_left(neg_sorted, x)
        j = bisect.bisect_right(neg_sorted, x)
        wins += i + 0.5 * (j - i)
    return wins / (len(pos) * len(neg))


def evaluate(policy, n=12000, pi=0.35, rho=0.30, mapok_frac=0.5, v_frac=0.5,
             seed=3, q=(4.2, 4.2, 4.2), c_sh=C_SH, fb_cost=1.2, g_scale=1.0):
    rng = random.Random(seed)
    agg = {t: [0, 0, 0] for t in TYPE_LIST}      # succ, cost, count
    surp_fam = {"A": [0, 0], "B": [0, 0]}        # surprises, servo steps
    scores = {t: [] for t in TYPE_LIST}
    shuttles = 0; corr = [0, 0]                  # corrected, gv count
    for _ in range(n):
        fam, t = sample_episode(rng, pi, rho, mapok_frac, v_frac)
        if policy in ("mond", "tri", "shuttle"):
            q_use = q[0] if fam == "A" else q[1]
        else:
            q_use = q[2]
        r = run_episode(fam, t, policy, rng, q=q_use, c_sh=c_sh,
                        fb_cost=fb_cost, g_scale=g_scale)
        a = agg[t]
        a[0] += 1 if r["succ"] else 0
        a[1] += r["spent"]
        a[2] += 1
        scores[t].append(r["score"])
        if t in ("id", "id_noisy"):
            surp_fam[r["fam"]][0] += r["surp"]
            surp_fam[r["fam"]][1] += r["serv"]
        if t == "ood_gv":
            corr[1] += 1
            corr[0] += 1 if r["corrected"] else 0
        shuttles += r["shuttles"]
    succ = sum(a[0] for a in agg.values()) / n
    cost = sum(a[1] for a in agg.values()) / n
    idn = agg["id"][2] + agg["id_noisy"][2]
    per = {t: (round(a[0] / a[2], 3) if a[2] else None) for t, a in agg.items()}
    out = dict(policy=policy, rho=rho, v_frac=v_frac, c_sh=c_sh,
               g_scale=g_scale, succ=round(succ, 3),
               cost=round(cost, 3), spc=round(succ / max(cost, 1e-9), 3),
               succ_id=per["id"], succ_exec=per["ood_exec"],
               succ_sem=per["ood_sem"], succ_gv=per["ood_gv"],
               succ_gs=per["ood_gs"],
               shut_rate=round(shuttles / n, 3),
               gv_fix=round(corr[0] / max(1, corr[1]), 3),
               surp_A=round(surp_fam["A"][0] / max(1, surp_fam["A"][1]), 3),
               surp_B=round(surp_fam["B"][0] / max(1, surp_fam["B"][1]), 3))
    m = 3000
    ids = (scores["id"] + scores["id_noisy"])[:m]
    out["auroc_sem"] = round(auroc(scores["ood_sem"][:m], ids), 3)
    out["auroc_gv"] = round(auroc(scores["ood_gv"][:m], ids), 3)
    out["auroc_gs"] = round(auroc(scores["ood_gs"][:m], ids), 3)
    out["auroc_exec"] = round(auroc(scores["ood_exec"][:m], ids), 3)
    return out


if __name__ == "__main__":
    qA, qB, qmix = calibrate()
    qs = (qA, qB, qmix)
    print("calibrated q_alpha: family A", round(qA, 3), "| family B",
          round(qB, 3), "| global", round(qmix, 3))
    rows = []
    for rho in (0.0, 0.25, 0.50):
        print(f"\n=== static OOD, semantic/grounding share rho = {rho} "
              f"(v_frac=0.5, c_sh={C_SH})")
        for pol in ("vla", "zest", "mond", "tri", "shuttle", "oracle"):
            r = evaluate(pol, n=12000, rho=rho, q=qs)
            r["scenario"] = "static"
            rows.append(r)
            print(f"{pol:8s} succ {r['succ']:.3f} cost {r['cost']:.2f} "
                  f"spc {r['spc']:.3f} id {r['succ_id']} "
                  f"exec {r['succ_exec']} sem {r['succ_sem']} "
                  f"gv {r['succ_gv']} gs {r['succ_gs']} "
                  f"fix {r['gv_fix']} sh {r['shut_rate']}")
    print("\n=== v_frac scan (rho=0.5): does the shuttle payoff follow the "
          "view-fragile share?")
    for vf in (0.0, 0.5, 1.0):
        for pol in ("zest", "mond", "tri", "shuttle"):
            r = evaluate(pol, n=10000, rho=0.5, v_frac=vf, q=qs)
            r["scenario"] = "vfrac"
            rows.append(r)
            print(f"v_frac={vf:.1f} {pol:8s} succ {r['succ']:.3f} "
                  f"cost {r['cost']:.2f} spc {r['spc']:.3f} "
                  f"gv {r['succ_gv']} fix {r['gv_fix']}")
    print("\n=== shuttle cost scan (rho=0.5, v_frac=0.5)")
    for cs in (0.5, 1.0, 2.0):
        for pol in ("shuttle", "mond"):
            r = evaluate(pol, n=10000, rho=0.5, c_sh=cs, q=qs)
            r["scenario"] = "csh"
            rows.append(r)
            print(f"c_sh={cs:.1f} {pol:8s} succ {r['succ']:.3f} "
                  f"cost {r['cost']:.2f} spc {r['spc']:.3f} "
                  f"sh {r['shut_rate']}")
    print("\n=== primitive quality scan (rho=0.25): fused-pose boost in the "
          "weak-primitive corner")
    for gs in (0.75, 1.0, 1.25):
        for pol in ("vla", "mond", "shuttle"):
            r = evaluate(pol, n=10000, rho=0.25, g_scale=gs, q=qs)
            r["scenario"] = "gscale"
            rows.append(r)
            print(f"g_scale={gs:.2f} {pol:8s} succ {r['succ']:.3f} "
                  f"spc {r['spc']:.3f} sem {r['succ_sem']}")
    print("\n=== per-family ID surprise rate (global vs Mondrian)")
    for pol in ("zest", "mond"):
        r = evaluate(pol, n=12000, rho=0.3, q=qs)
        print(f"{pol:8s} ID surprise A {r['surp_A']:.3f}  B {r['surp_B']:.3f}")
    out = dict(calibration=dict(qA=qA, qB=qB, qmix=qmix), rows=rows)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "tri_results.json")
    json.dump(out, open(path, "w"), indent=2)
    print("\nwrote", path)
