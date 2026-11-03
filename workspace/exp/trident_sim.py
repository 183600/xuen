"""Synthetic mechanism check for TRIDENT-VLA (round 16, inspiration loop r1).

NOT benchmark evidence. It isolates three questions, one per new module, and
reports the boundary of each:

Q1 (grounding / retrieval).  Round 15 proved that when the VLA and the
    semantic map share a wrong prior (OOD-G), every residual-based detector is
    information-theoretically capped at AUC <= 1/2 + eps/2.  Can a retrieval
    channel whose evidence does NOT come from the deployed policy's own prior
    break that cap -- and what exactly bounds the gain?

Q2 (duty / thermal).  Round 15 normalizes residuals with a sliding MAD.  That
    is blind: a *persistent* multiplicative inflation of the residual is
    absorbed by the window after W blocks, so the CUSUM can stop firing on a
    real OOD.  Does a causal, duty-aware normalizer (inverse-dynamics load
    proxy) keep the detection delay bounded while suppressing duty-drift false
    alarms?

Q3 (perturbation / recovery).  Round 15's residuals cannot distinguish "the
    robot was knocked" from "the policy is incompetent": both look like a
    large residual.  Can a body-level unexpected-displacement detector plus a
    tiered self-reset ladder separate them and recover episodes?

All generative parameters are declared, not fitted.  Nothing here is evidence
about the real robot; it is evidence about the *mechanism*.
"""
import bisect
import json
import math
import os
import random
import statistics

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def quantile(xs, q):
    ys = sorted(xs)
    if not ys:
        return 0.0
    i = min(len(ys) - 1, max(0, int(math.ceil(q * len(ys))) - 1))
    return ys[i]


def auroc(pos, neg):
    """Rank-based AUROC; ties count as 0.5.  O((n+m) log(n+m))."""
    if not pos or not neg:
        return float("nan")
    neg_sorted = sorted(neg)
    total = 0.0
    for x in pos:
        lo = bisect.bisect_left(neg_sorted, x)
        hi = bisect.bisect_right(neg_sorted, x)
        total += lo + 0.5 * (hi - lo)
    return total / (len(pos) * len(neg))


def clip(x, lo=0.0, hi=2.0):
    return max(lo, min(hi, x))


# --------------------------------------------------------------------------- #
# Q1 -- grounding triangulation: retrieval vs the OOD-G degeneracy
# --------------------------------------------------------------------------- #

# Hypotheses are object identities: 0 = the true target, 1/2 = distractors.
# Retrieval outcomes are three-valued: NO_HIT (abstain), WEAK (hit but low
# confidence), CONF (confident hit).  Only CONF hits may raise a flag.

NO_HIT, WEAK, CONF = "no_hit", "weak", "conf"


def _pick_wrong(rng):
    return rng.choice((1, 2))


def sample_episode_sources(rng, cls, cfg):
    """Return the hypotheses of the three grounding sources.

    cls == "ood_g": the map and the VLA share ONE wrong prior (same object).
    cls == "id":    all sources are usually right; independent small errors.
    """
    if cls == "ood_g":
        shared = _pick_wrong(rng)          # shared wrong prior
        h_map, h_vla = shared, shared
    else:
        h_map = 0 if rng.random() > cfg["p_map_err_id"] else _pick_wrong(rng)
        h_vla = 0 if rng.random() > cfg["p_vla_err_id"] else _pick_wrong(rng)

    # retrieval: coverage and correctness are *decoupled* from the policy prior
    u = rng.random()
    if u < cfg["cov_conf"]:
        ret, conf = NO_HIT, None
        hit = CONF
    elif u < cfg["cov_conf"] + cfg["cov_weak"]:
        hit = WEAK
    else:
        hit = NO_HIT
    if hit == CONF:
        p_ok = cfg["p_ret_correct_conf"]
    elif hit == WEAK:
        p_ok = cfg["p_ret_correct_weak"]
    else:
        p_ok = 0.0
    if hit == NO_HIT:
        h_ret, conf = None, 0.0
    else:
        h_ret = 0 if rng.random() < p_ok else _pick_wrong(rng)
        conf = 0.9 if hit == CONF else 0.6
    return {"M": h_map, "V": h_vla, "R": h_ret}, conf, hit


def vote_disagreement(sources, use_retrieval, weights=(1.0, 1.0, 1.0)):
    """Weighted-vote disagreement mass m_perp = 1 - max_i P(i).

    Abstaining sources are removed and the remaining weights renormalized.
    Returns (m_perp, active_retrieval).
    """
    active = [("M", sources["M"]), ("V", sources["V"])]
    if use_retrieval and sources["R"] is not None:
        active.append(("R", sources["R"]))
    wmap = {"M": weights[0], "V": weights[1], "R": weights[2]}
    wsum = sum(wmap[k] for k, _ in active)
    if wsum <= 0:
        return 0.0, False
    tally = {}
    for k, h in active:
        tally[h] = tally.get(h, 0.0) + wmap[k] / wsum
    return 1.0 - max(tally.values()), ("R" in [k for k, _ in active])


def q1_grounding(cfg, n=40000, seed=11):
    rng = random.Random(seed)
    res = {}
    for use_ret in (False, True):
        id_scores, ood_scores = [], []
        id_useful, ood_useful = 0, 0
        id_flag, ood_flag = 0, 0
        ood_harm = 0
        for _ in range(n):
            cls = "id" if rng.random() < 0.5 else "ood_g"
            src, conf, hit = sample_episode_sources(rng, cls, cfg)
            m, ret_active = vote_disagreement(src, use_ret)
            # the flag rule: M and V agree, R is active and disagrees, and the
            # retrieval confidence clears tau_R (only confident hits qualify)
            agree_mv = src["M"] == src["V"]
            disagrees = ret_active and src["R"] != src["M"]
            flag = agree_mv and disagrees and conf >= cfg["tau_R"]
            (id_scores if cls == "id" else ood_scores).append(m)
            if cls == "id":
                id_flag += flag
            else:
                ood_flag += flag
                if flag:
                    if src["R"] == 0:
                        ood_useful += 1
                    else:
                        ood_harm += 1
        thr = quantile(id_scores, 1.0 - cfg["target_id_fa"])
        res["with_retrieval" if use_ret else "map_vla_only"] = {
            "auroc": round(auroc(ood_scores, id_scores), 4),
            "id_flag_rate_at_threshold": round(
                sum(1 for x in id_scores if x > thr) / len(id_scores), 4),
            "ood_flag_rate": round(ood_flag / n, 4),
            "ood_useful_flag_rate": round(ood_useful / n, 4),
            "ood_harmful_flag_rate": round(ood_harm / n, 4),
            "threshold": round(thr, 4),
        }
        # theoretical bound: detection needs R active, confident and correct
        p_conf = cfg["cov_conf"]
        p_ok = cfg["p_ret_correct_conf"]
        res["with_retrieval" if use_ret else "map_vla_only"]["predicted_ood_flag_rate"] = (
            round(p_conf * p_ok, 4) if use_ret else 0.0)
    return res


def q1_sweep(cfg, n=20000, seed=13):
    """How the retrieval channel's value depends on coverage and correctness."""
    rows = []
    base = dict(cfg)
    for cov_conf in (0.2, 0.45, 0.7):
        for p_ok in (0.5, 0.75, 0.9):
            c = dict(base)
            c["cov_conf"] = cov_conf
            c["cov_weak"] = min(0.3, 1.0 - cov_conf)
            c["p_ret_correct_conf"] = p_ok
            r = q1_grounding(c, n=n, seed=seed)
            row = {
                "cov_conf": cov_conf,
                "p_ret_correct": p_ok,
                "auroc": r["with_retrieval"]["auroc"],
                "ood_useful_flag_rate": r["with_retrieval"]["ood_useful_flag_rate"],
                "ood_harmful_flag_rate": r["with_retrieval"]["ood_harmful_flag_rate"],
                "predicted": round(cov_conf * p_ok, 4),
            }
            rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# Q2 -- duty-aware causal normalization vs blind MAD normalization
# --------------------------------------------------------------------------- #

def duty_inflation(duty, beta=1.2, duty0=0.5):
    """Expected multiplicative inflation of the tracking residual at duty `duty`."""
    return 1.0 / max(0.2, 1.0 - beta * max(0.0, duty - duty0))


def q2_run(gate, cfg, ood_onset=None, seed=1):
    """One block sequence; returns per-block records + detection delay."""
    rng = random.Random(seed)
    duty = cfg["duty_start"]
    raw = []           # sliding window of raw fused scores (blind MAD)
    cusum = 0.0
    records = []
    delay = None
    for b in range(cfg["n_blocks"]):
        duty += (cfg["duty_load"] - duty) / cfg["tau_duty"]
        infl = duty_inflation(duty, cfg["beta"], cfg["duty0"])
        base = cfg["base"]
        if ood_onset is not None and b >= ood_onset:
            base = cfg["base"] * cfg["kappa"]
        s = base * infl + rng.gauss(0.0, cfg["sigma_obs"])
        if gate == "blind":
            raw.append(s)
            win = raw[-cfg["W"]:]
            med = statistics.median(win)
            mad = statistics.median([abs(x - med) for x in win])
            sigma = 1.4826 * mad + 0.05
            z = s / sigma
        elif gate == "duty":
            s_corr = s / infl * cfg["model_bias"]
            z = s_corr / cfg["sigma_id"]
        elif gate == "fixed":
            z = s / cfg["sigma_id"]
        else:
            raise ValueError(gate)
        surprise = 1 if z > cfg["q_z"] else 0
        cusum = max(0.0, cusum + surprise - cfg["alpha"] - cfg["k"])
        records.append({"b": b, "duty": duty, "s": s, "z": z,
                        "surprise": surprise, "cusum": cusum})
        if ood_onset is not None and delay is None and b >= ood_onset and cusum > cfg["h"]:
            delay = b - ood_onset + 1
    return records, delay


def q2(cfg, seeds=(1, 2, 3)):
    """Calibrate each gate on ID-cool, then test ID-hot and persistent OOD."""
    out = {}
    # calibration: ID, cool machine -> 90th percentile of z per gate
    qz = {}
    for gate in ("blind", "duty", "fixed"):
        zs = []
        for sd in seeds:
            c = dict(cfg)
            c.update({"duty_load": cfg["duty_cool"], "q_z": 1e9})
            rec, _ = q2_run(gate, c, None, seed=sd)
            zs += [r["z"] for r in rec]
        qz[gate] = quantile(zs, 0.90)
    for gate in ("blind", "duty", "fixed"):
        c = dict(cfg)
        c["q_z"] = qz[gate]
        # ID hot: false-alarm rate under duty drift
        fa_hot, fa_cool, delays, detected, ood_z, id_z = [], [], [], 0, [], []
        for sd in seeds:
            c_cool = dict(c)
            c_cool["duty_load"] = cfg["duty_cool"]
            rec, _ = q2_run(gate, c_cool, None, seed=sd)
            fa_cool.append(sum(r["surprise"] for r in rec) / len(rec))
            c_hot = dict(c)
            c_hot["duty_load"] = cfg["duty_hot"]
            rec, _ = q2_run(gate, c_hot, None, seed=sd)
            fa_hot.append(sum(r["surprise"] for r in rec) / len(rec))
            id_z += [r["z"] for r in rec]
            rec, d = q2_run(gate, c_hot, cfg["ood_onset"], seed=sd)
            ood_z += [r["z"] for r in rec if r["b"] >= cfg["ood_onset"]]
            if d is not None:
                detected += 1
                delays.append(d)
        out[gate] = {
            "q_z": round(qz[gate], 3),
            "id_fa_rate_cool": round(statistics.mean(fa_cool), 4),
            "id_fa_rate_hot": round(statistics.mean(fa_hot), 4),
            "ood_detected_runs": "%d/%d" % (detected, len(seeds)),
            "ood_delay_blocks": (round(statistics.mean(delays), 2) if delays else None),
            "ood_z_mean": round(statistics.mean(ood_z), 3),
            "id_z_mean_hot": round(statistics.mean(id_z), 3),
        }
    return out


# --------------------------------------------------------------------------- #
# Q3 -- body-level perturbation detection and the self-reset ladder
# --------------------------------------------------------------------------- #

PERT_MILD, PERT_MOD, PERT_SEVERE = "mild", "moderate", "severe"


def sample_perturbation(rng, cfg):
    u = rng.random()
    if u < cfg["p_pert_mild"]:
        return PERT_MILD
    if u < cfg["p_pert_mild"] + cfg["p_pert_mod"]:
        return PERT_MOD
    return PERT_SEVERE


def q3_run(policy, cfg, seed=1):
    rng = random.Random(seed)
    B, p_need = cfg["B"], cfg["p_need"]
    blocks, progress, duty = 0.0, 0.0, cfg["duty_start"]
    dead = False
    pert_events, recovered, lost_to_pert = 0, 0, 0
    extra_duty = 0.0
    while blocks < B and progress < p_need and not dead:
        blocks += 1
        duty += (cfg["duty_load"] - duty) / cfg["tau_duty"]
        if rng.random() < cfg["p_pert"]:
            kind = sample_perturbation(rng, cfg)
            pert_events += 1
            if policy == "none":
                dead = True
                lost_to_pert += 1
                continue
            if policy == "zest_style":
                # round 15 sees a big residual, misreads it as policy
                # incompetence and runs the geometric fallback on a stale map
                ok = {"mild": 0.20, "moderate": 0.05, "severe": 0.0}[kind]
                blocks += cfg["cost_fallback"]
                extra_duty += 0.25
                if rng.random() < ok:
                    recovered += 1
                else:
                    dead = True
                    lost_to_pert += 1
                continue
            if policy == "guard":
                cost, ok = {"mild": (1.0, 0.85), "moderate": (1.0, 0.30),
                            "severe": (1.0, 0.0)}[kind]
            elif policy == "cascade":
                cost, ok = {"mild": (1.0, 0.85), "moderate": (2.0, 0.55),
                            "severe": (3.0, 0.15)}[kind]
            elif policy == "cascade_duty_gated":
                if duty > cfg["duty_gate"]:
                    cost, ok = {"mild": (1.0, 0.80), "moderate": (1.0, 0.35),
                                "severe": (1.0, 0.0)}[kind]
                else:
                    cost, ok = {"mild": (1.0, 0.85), "moderate": (2.0, 0.55),
                                "severe": (3.0, 0.15)}[kind]
            else:
                raise ValueError(policy)
            blocks += cost
            extra_duty += 0.15 * cost
            if rng.random() < ok:
                recovered += 1
            else:
                dead = True
                lost_to_pert += 1
            continue
        # ordinary work
        ok = rng.random() < cfg["p_progress"]
        if ok:
            progress += 1.0
    return {
        "success": int(progress >= p_need and not dead),
        "blocks": blocks,
        "dead": dead,
        "pert_events": pert_events,
        "recovered": recovered,
        "lost_to_pert": lost_to_pert,
        "extra_duty": extra_duty,
    }


def q3(cfg, n=30000, seeds=(1, 2, 3)):
    rows = []
    for p_pert in (0.005, 0.01, 0.02):
        for duty_load, label in ((0.55, "cool"), (0.9, "hot")):
            c = dict(cfg)
            c.update({"p_pert": p_pert, "duty_load": duty_load})
            for policy in ("none", "zest_style", "guard", "cascade",
                           "cascade_duty_gated"):
                succ, lost, rec, blk, duty = [], [], [], [], []
                for sd in seeds:
                    rr = q3_run(policy, c, seed=sd * 7919 + int(p_pert * 1e4))
                    succ.append(rr["success"])
                    lost.append(rr["lost_to_pert"])
                    rec.append(rr["recovered"])
                    blk.append(rr["blocks"])
                    duty.append(rr["extra_duty"])
                rows.append({
                    "p_pert": p_pert, "duty": label, "policy": policy,
                    "success": round(statistics.mean(succ), 4),
                    "lost_to_perturbation": round(statistics.mean(lost), 4),
                    "recovered_events": round(statistics.mean(rec), 4),
                    "mean_blocks": round(statistics.mean(blk), 3),
                    "extra_duty": round(statistics.mean(duty), 4),
                })
    return rows


# --------------------------------------------------------------------------- #
# Q4 -- end-to-end: does the three-layer supervisor beat round 15?
# --------------------------------------------------------------------------- #

def q4_sample_type(rng, cfg):
    u = rng.random()
    if u < 1.0 - cfg["pi"]:
        return "id"
    if u < 1.0 - cfg["pi"] + cfg["pi"] * (1.0 - cfg["rho"]):
        return "ood_exec"
    if u < 1.0 - cfg["pi"] + cfg["pi"] * (1.0 - cfg["rho"]) + cfg["pi"] * cfg["rho"] * cfg["m_mapok"]:
        return "ood_sem_mapok"
    return "ood_ground"


def q4_run(policy, cfg, seed):
    rng = random.Random(seed)
    typ = q4_sample_type(rng, cfg)
    use_gate = policy != "vla"
    use_duty = policy in ("trident", "trident_no_ret", "trident_no_recov")
    use_ret = policy in ("trident", "trident_no_duty", "trident_no_recov")
    use_rec = policy in ("trident", "trident_no_ret", "trident_no_duty")
    shuffled = policy == "trident_shuffled_mem"

    # grounding truth for this episode
    map_ok = typ in ("id", "ood_exec", "ood_sem_mapok")
    vla_ok = typ == "id"
    if typ == "ood_ground":
        # map and VLA share the wrong prior
        wrong_target = True
    else:
        wrong_target = False

    # retrieval outcome
    u = rng.random()
    if u < cfg["cov_conf"]:
        hit, conf = "conf", 0.9
    elif u < cfg["cov_conf"] + cfg["cov_weak"]:
        hit, conf = "weak", 0.6
    else:
        hit, conf = "no_hit", 0.0
    if hit == "no_hit":
        ret_h, ret_ok = None, False
    else:
        p_ok = cfg["p_ret_correct_conf"] if hit == "conf" else cfg["p_ret_correct_weak"]
        ret_ok = rng.random() < p_ok
        if shuffled:
            ret_ok = rng.random() < (1.0 - p_ok)   # negative control: permuted memory
        ret_h = 0 if ret_ok else 1

    progress, blocks, duty = 0.0, 0.0, cfg["duty_start"]
    cusum, raw = 0.0, []
    mode = "servo"
    perturbed = False
    dead = False
    flagged_ground = 0
    used_primitive_wrong_target = 0
    pert_events, pert_recovered = 0, 0

    while blocks < cfg["B"] and progress < cfg["p_need"] and not dead:
        blocks += 1
        duty += (cfg["duty_load"] - duty) / cfg["tau_duty"]
        derate = max(0.4, 1.0 - 0.8 * max(0.0, duty - 0.6))

        # --- perturbation handling (body-level detector) ---
        if rng.random() < cfg["p_pert"]:
            pert_events += 1
            kind = sample_perturbation(rng, cfg)
            if not use_rec:
                dead = True
                continue
            cost, ok = {"mild": (1.0, 0.85), "moderate": (2.0, 0.55),
                        "severe": (3.0, 0.15)}[kind]
            if duty > cfg["duty_gate"]:
                cost, ok = {"mild": (1.0, 0.80), "moderate": (1.0, 0.35),
                            "severe": (1.0, 0.0)}[kind]
            blocks += cost
            if rng.random() < ok:
                pert_recovered += 1
            else:
                dead = True
            continue

        # --- grounding triangulation (retrieval channel) ---
        if use_ret and typ == "ood_ground" and ret_h is not None \
                and conf >= cfg["tau_R"] and ret_h != (0 if map_ok else 1):
            # M and V agree on the (wrong) target, R disagrees confidently
            flagged_ground += 1
            blocks += cfg["cost_reground"]
            if ret_ok:
                # re-grounding confirms the map is wrong -> switch to the
                # retrieved target and run the geometric primitive on it
                mode = "primitive"
                mode_target_ok = True
            else:
                mode = "servo"   # escalation was a false alarm, keep serving
        # --- execute ---
        if mode == "primitive":
            blocks += cfg["cost_fallback"] - 1.0
            tgt_ok = mode_target_ok
            if not tgt_ok:
                used_primitive_wrong_target += 1
            ok = rng.random() < cfg["p_prim"] * (1.0 if tgt_ok else 0.05)
        else:
            if typ == "id":
                p_ok = cfg["c_id"] * 0.9 * derate
            elif typ == "ood_exec":
                p_ok = cfg["c_ood"] * 0.9 * derate if use_gate else cfg["c_ood"] * 0.9 * derate
            else:
                p_ok = cfg["c_ood"] * 0.9 * derate
            if typ in ("ood_exec", "ood_sem_mapok") and use_gate:
                p_ok = cfg["c_ood"] * 0.9 * derate   # VLA acts on the wrong thing
            ok = rng.random() < p_ok
        if ok:
            progress += 1.0

        # --- residual channel + trust gate (only after a servo block) ---
        if mode == "servo":
            if typ == "id":
                base = cfg["base"]
            elif typ == "ood_exec":
                base = cfg["base"] * cfg["kappa_exec"]
            elif typ == "ood_sem_mapok":
                base = cfg["base"] * cfg["kappa_sem"]
            else:
                base = cfg["base"]          # OOD-G looks exactly like ID
            infl = duty_inflation(duty, cfg["beta"], cfg["duty0"])
            s = base * infl + rng.gauss(0.0, cfg["sigma_obs"])
            if use_duty:
                z = (s / infl) / cfg["sigma_id"]
            else:
                raw.append(s)
                win = raw[-cfg["W"]:]
                med = statistics.median(win)
                mad = statistics.median([abs(x - med) for x in win])
                sigma = 1.4826 * mad + 0.05
                z = s / sigma
            surprise = 1 if z > cfg["q_z_blind"] else 0
            cusum = max(0.0, cusum + surprise - cfg["alpha"] - cfg["k"])
            if use_gate and cusum > cfg["h"] and mode == "servo":
                if typ == "ood_exec" or typ == "ood_sem_mapok":
                    mode = "primitive"
                    mode_target_ok = map_ok
                elif typ == "id":
                    # false fallback (blind normalization chases duty drift)
                    mode = "primitive"
                    mode_target_ok = True
                cusum = 0.0
    return {
        "success": int(progress >= cfg["p_need"] and not dead),
        "typ": typ,
        "blocks": blocks,
        "flagged_ground": flagged_ground,
        "used_primitive_wrong_target": used_primitive_wrong_target,
        "pert_events": pert_events,
        "pert_recovered": pert_recovered,
        "dead": dead,
    }


def q4(cfg, policies=("vla", "zest", "trident", "trident_no_ret",
                      "trident_no_duty", "trident_no_recov",
                      "trident_shuffled_mem"), n=12000, seed=17):
    rows = []
    for pol in policies:
        succ, blocks = [], []
        per_type = {}
        flagged, harm, pert_ev, pert_rec = [], [], [], []
        for i in range(n):
            rr = q4_run(pol, cfg, seed=seed + i * 13 + hash(pol) % 1000)
            succ.append(rr["success"])
            blocks.append(rr["blocks"])
            d = per_type.setdefault(rr["typ"], [0, 0])
            d[0] += rr["success"]
            d[1] += 1
            flagged.append(rr["flagged_ground"])
            harm.append(rr["used_primitive_wrong_target"])
            pert_ev.append(rr["pert_events"])
            pert_rec.append(rr["pert_recovered"])
        rows.append({
            "policy": pol,
            "success": round(statistics.mean(succ), 4),
            "mean_blocks": round(statistics.mean(blocks), 3),
            "ground_flags_per_ep": round(statistics.mean(flagged), 4),
            "primitive_on_wrong_target": round(statistics.mean(harm), 4),
            "pert_events": round(statistics.mean(pert_ev), 4),
            "pert_recovered": round(statistics.mean(pert_rec), 4),
            "success_by_type": {k: round(v[0] / v[1], 4) for k, v in sorted(per_type.items())},
        })
    return rows


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

DEFAULT_CFG = {
    # Q1 retrieval channel
    "cov_conf": 0.45, "cov_weak": 0.25,
    "p_ret_correct_conf": 0.9, "p_ret_correct_weak": 0.5,
    "tau_R": 0.75, "target_id_fa": 0.05,
    "p_map_err_id": 0.02, "p_vla_err_id": 0.02,
    # Q2 duty / residual
    "n_blocks": 60, "W": 8, "base": 0.20, "sigma_obs": 0.05, "sigma_id": 0.05,
    "kappa": 3.0, "beta": 1.2, "duty0": 0.5, "tau_duty": 8.0,
    "duty_start": 0.20, "duty_cool": 0.25, "duty_hot": 0.9,
    "alpha": 0.12, "k": 0.05, "h": 2.0, "ood_onset": 20, "model_bias": 1.0,
    # Q3 perturbation
    "p_pert": 0.01, "p_pert_mild": 0.65, "p_pert_mod": 0.25,
    "B": 12, "p_need": 3, "p_progress": 0.6, "duty_gate": 0.7,
    "cost_fallback": 1.2,
    # Q4 end-to-end
    "pi": 0.35, "rho": 0.6, "m_mapok": 0.35,
    "c_id": 0.80, "c_ood": 0.30, "p_prim": 0.60,
    "kappa_exec": 3.0, "kappa_sem": 2.2,
    "cost_reground": 1.5, "q_z_blind": 4.2,
}


if __name__ == "__main__":
    cfg = dict(DEFAULT_CFG)
    out = {}

    print("=" * 74)
    print("Q1  grounding triangulation: retrieval vs the OOD-G degeneracy")
    print("=" * 74)
    r = q1_grounding(cfg)
    for k, v in r.items():
        print(k, v)
    out["q1_grounding"] = r
    sw = q1_sweep(cfg)
    out["q1_sweep"] = sw
    print("\nsweep (coverage x correctness):")
    for row in sw:
        print(row)

    print("\n" + "=" * 74)
    print("Q2  duty-aware causal normalization vs blind MAD normalization")
    print("=" * 74)
    r2 = q2(cfg)
    for gate, v in r2.items():
        print(gate, v)
    out["q2_duty"] = r2
    print("\nmodel-bias sensitivity (duty gate, hot ID):")
    sens = []
    for bias in (0.8, 1.0, 1.25):
        c = dict(cfg)
        c["model_bias"] = bias
        rr = q2(c)
        sens.append({"model_bias": bias,
                     "blind_id_fa_hot": rr["blind"]["id_fa_rate_hot"],
                     "duty_id_fa_hot": rr["duty"]["id_fa_rate_hot"],
                     "duty_delay": rr["duty"]["ood_delay_blocks"],
                     "blind_delay": rr["blind"]["ood_delay_blocks"]})
        print(sens[-1])
    out["q2_model_bias"] = sens

    print("\n" + "=" * 74)
    print("Q3  perturbation detection and the tiered self-reset ladder")
    print("=" * 74)
    r3 = q3(cfg)
    out["q3_perturbation"] = r3
    for row in r3:
        print(row)

    print("\n" + "=" * 74)
    print("Q4  end-to-end: vla / zest / trident and the ablations")
    print("=" * 74)
    r4 = q4(cfg)
    out["q4_end_to_end"] = r4
    for row in r4:
        print(row)

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "trident_results.json")
    json.dump(out, open(path, "w"), indent=2)
    print("\nwrote", path)
