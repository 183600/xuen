"""Synthetic mechanism check for AUDIT-VLA (round 16).

NOT benchmark evidence. Isolates one question:
round 15 proved (Prop 7) that passive action-observation residuals cannot
detect OOD-G (VLA and semantic map share a wrong referent prior). Round 16
asks: can instruction-derived spec signatures + counterfactual referent
probes (runtime ablation of the instruction/viewpoint channel) detect and
repair the wrong grounding without hurting ID?

Generative model (declared, not fit):
  - episode types: ID (15% noisy), OOD-exec, OOD-sem (map referent right),
    OOD-G-shape (collapse to a shape-DISTINGUISHABLE distractor: relation
    signature mismatch is measurable), OOD-G-silent (shape-plausible or
    unmeasurable distractor: no signal anywhere).
  - per block: SERVO progress ~ Bern(c_eff); executing a WRONG referent
    yields correct-goal progress ~ Bern(0.05) (smooth but misdirected);
    FALLBACK ~ Bern(g), g depends on whether the MAP referent is right.
  - ZEST channel (round 15): per-block surprise ~ Bern(p_surp[type]);
    CUSUM (alpha=.12, k=.05, h=2.5); recheck every 3rd fallback block.
  - AUDIT channel (round 16): per-block spec alarm ~ Bern(p_alarm[type]),
    rising to .35 on a false-flipped ID referent (signature mismatch of the
    now-wrong referent); on alarm a paraphrase probe (1 block, cost 1.5)
    tests referent sensitivity; confirmed collapse triggers ONE reground
    (1 block, cost 1.0). OOD-G-silent keeps p_alarm at ID level: the
    boundary survives by construction.
  - success = correct-goal progress >= P_NEED within budget.
  - policies: vla_only / zest15 (round 15 mechanism) / audit / audit_noprobe
    (no probe verification) / probe_always (always-on probing) /
    audit_rand (type-independent alarm: negative control) / oracle.
"""
import json
import random

# ---------- declared parameters (not fitted) ----------
ALPHA, KAPPA, H = 0.12, 0.05, 2.5          # ZEST CUSUM (round 15)
P_NEED, B_MAIN = 3, 10
C_SERVO, C_FB, C_PROBE, C_REGR = 1.0, 1.2, 1.5, 1.0
G_OK, G_WRONG = 0.60, 0.05                 # primitive progress, map right/wrong
C_WRONG = 0.05                             # servo progress on wrong referent
PROBE_CONFIRM = {"ood_gc": 0.95, "ood_gs": 0.50}
REGROUND_FIX = {"ood_gc": 0.80, "ood_gs": 0.35}
C_RESTORE = {"ood_gc": 0.60, "ood_gs": 0.50}
Q_FF_ID = 0.02                             # probe false-flip on ID
Q_FF_EXEC = 0.05                           # probe false-flip on OOD-exec
PROBE_FIX_FLIP = 0.60                      # a later probe repairs a false flip
NOPROBE_FLIP = 0.25                        # unverified reground breaks healthy grounding
NOPROBE_FIX_GC = 0.55                      # unverified reground fixes collapse
PA_FLIPPED_ID = 0.35                       # signature alarm once ID referent is wrong

PARAMS = {  # c_servo, p_surprise, p_alarm
    "id":       (0.72, 0.03, 0.005),
    "id_noisy": (0.72, 0.10, 0.015),
    "ood_exec": (0.27, 0.75, 0.02),
    "ood_sem":  (0.18, 0.65, 0.30),
    "ood_gc":   (0.05, 0.03, 0.35),
    "ood_gs":   (0.05, 0.03, 0.01),
}
MIX = {"ood_exec": 0.40, "ood_sem": 0.20, "ood_gc": 0.25, "ood_gs": 0.15}
PI = 0.35
AUDIT_POLICIES = ("audit", "audit_noprobe", "probe_always", "audit_rand", "oracle")
GATED = ("zest15", "audit", "audit_noprobe", "probe_always", "audit_rand")


def sample_types(rng, B=B_MAIN, pi=PI, mix=MIX):
    if rng.random() >= pi:
        t = "id_noisy" if rng.random() < 0.15 else "id"
    else:
        r, acc = rng.random(), 0.0
        t = "ood_gs"
        for k in ("ood_exec", "ood_sem", "ood_gc", "ood_gs"):
            acc += mix[k]
            if r < acc:
                t = k
                break
    return [t] * B


def run_episode(types, policy, rng, q_rg=REGROUND_FIX["ood_gc"],
                q_ff_id=Q_FF_ID, p_need=P_NEED):
    n = len(types)
    progress = cost = vla_calls = 0.0
    S = 0.0
    mode = "trust"
    dwell = 0
    flip = False            # referent wrongly swapped by the auditor itself
    restored = 0.0          # competence after a successful reground
    probes_left = 2
    reground_used = False
    primitives = False
    pending = None
    hold_end = False
    gc_detected = False
    false_repair = False
    reground_att = False

    for b in range(n):
        t = types[b]
        c0, p_surp, p_alarm = PARAMS[t]
        wrong = flip or (t in ("ood_gc", "ood_gs") and restored == 0.0)

        # ---------- choose action ----------
        if pending is not None:
            act, pending = pending, None
        elif hold_end:
            act = "hold"
        elif primitives:
            act = "fb"
        elif mode == "fallback":
            act = "servo_probe" if (dwell > 0 and dwell % 3 == 0) else "fb"
        elif policy == "probe_always" and b == 2 and probes_left > 0 \
                and mode == "trust":
            act = "probe"
        else:
            act = "servo"

        # ---------- execute ----------
        if act == "servo":
            c = restored if (t in ("ood_gc", "ood_gs") and restored) \
                else (C_WRONG if wrong else c0)
            progress += 1.0 if rng.random() < c else 0.0
            cost += C_SERVO
            if policy in GATED:
                S = max(0.0, S + (1.0 if rng.random() < p_surp else 0.0)
                        - ALPHA - KAPPA)
                if S > H:
                    mode, dwell = "fallback", 0
        elif act == "servo_probe":
            c = restored if (t in ("ood_gc", "ood_gs") and restored) \
                else (C_WRONG if wrong else c0)
            progress += 1.0 if rng.random() < c else 0.0
            cost += C_SERVO
            e = 1 if rng.random() < p_surp else 0
            if e == 0 and not wrong and restored == 0.0:
                mode, S = "trust", 0.0
            dwell = 0
        elif act == "fb":
            g = G_WRONG if wrong else G_OK
            progress += 1.0 if rng.random() < g else 0.0
            cost += C_FB
            dwell += 1
        elif act == "hold":
            pass
        elif act == "probe":
            cost += C_PROBE
            vla_calls += 1
            probes_left -= 1
            if t in ("ood_gc", "ood_gs") and restored == 0.0:
                if rng.random() < PROBE_CONFIRM[t]:
                    gc_detected = True
                    if not reground_used:
                        pending = "reground"
            elif flip:
                if rng.random() < PROBE_FIX_FLIP:
                    flip = False
            elif t == "ood_sem":
                if rng.random() < 0.85:
                    primitives = True
            elif t == "ood_exec":
                if rng.random() < Q_FF_EXEC:
                    flip = True
            else:  # id / id_noisy
                if rng.random() < q_ff_id:
                    flip = True
                    false_repair = True
        elif act == "reground":
            cost += C_REGR
            vla_calls += 1
            reground_used = True
            reground_att = True
            if t in ("id", "id_noisy") and not flip:
                # unverified reground on a healthy grounding (noprobe path)
                if policy == "audit_noprobe" and rng.random() < NOPROBE_FLIP:
                    flip = True
                    false_repair = True
            elif t == "ood_gs":
                if rng.random() < REGROUND_FIX["ood_gs"]:
                    restored = C_RESTORE["ood_gs"]
                    S, mode = 0.0, "trust"
                else:
                    hold_end = True
            else:  # ood_gc (or a flipped id under audit_noprobe)
                if policy == "oracle":
                    fixp = 0.90
                elif policy == "audit_noprobe" and t not in ("id", "id_noisy"):
                    fixp = NOPROBE_FIX_GC
                else:
                    fixp = q_rg
                if rng.random() < fixp:
                    if t in ("id", "id_noisy"):
                        flip, restored = False, 0.0
                    else:
                        restored = C_RESTORE["ood_gc"]
                    S, mode = 0.0, "trust"
                elif t not in ("id", "id_noisy"):
                    hold_end = True
        # ---------- audit channel ----------
        if policy in AUDIT_POLICIES and not hold_end and not primitives \
                and pending is None:
            if policy == "oracle":
                if t in ("ood_exec", "ood_sem") and b == 1:
                    primitives = True
                elif t in ("ood_gc", "ood_gs") and not reground_used \
                        and (b == 0 or types[b - 1] not in ("ood_gc", "ood_gs")):
                    pending = "reground"
            else:
                if policy == "audit_rand":
                    p = 0.05
                elif flip and t in ("id", "id_noisy"):
                    p = PA_FLIPPED_ID
                else:
                    p = p_alarm
                if rng.random() < p:
                    if policy == "audit_noprobe":
                        if t in ("ood_gc", "ood_gs") and not reground_used:
                            pending = "reground"
                        elif t == "ood_sem":
                            primitives = True
                        elif t in ("id", "id_noisy") and not reground_used:
                            pending = "reground"
                    elif probes_left > 0 and (n - b) >= 2:
                        pending = "probe"

    return {
        "success": 1 if progress >= p_need else 0,
        "cost": cost,
        "vla_calls": vla_calls,
        "gc_detected": 1 if gc_detected else 0,
        "false_repair": 1 if false_repair else 0,
        "reground": 1 if reground_att else 0,
    }


def cell(policy, n_ep, seed, types_fn=None, q_rg=REGROUND_FIX["ood_gc"],
         q_ff_id=Q_FF_ID, p_need=P_NEED):
    rng = random.Random(seed)
    types_fn = types_fn or sample_types
    agg = {"success": 0, "cost": 0.0, "vla_calls": 0.0, "gc_detected": 0,
           "false_repair": 0, "reground": 0, "n": 0,
           "id_n": 0, "id_succ": 0, "id_cost": 0.0, "id_flip": 0,
           "gc_n": 0, "gc_succ": 0, "gc_det": 0, "gs_n": 0, "gs_succ": 0,
           "sem_n": 0, "sem_succ": 0, "exec_n": 0, "exec_succ": 0}
    for _ in range(n_ep):
        types = types_fn(rng)
        r = run_episode(types, policy, rng, q_rg=q_rg, q_ff_id=q_ff_id,
                        p_need=p_need)
        agg["n"] += 1
        for k in ("success", "cost", "vla_calls", "gc_detected",
                  "false_repair", "reground"):
            agg[k] += r[k]
        tset = set(types)
        if tset <= {"id", "id_noisy"}:
            agg["id_n"] += 1
            agg["id_succ"] += r["success"]
            agg["id_cost"] += r["cost"]
            agg["id_flip"] += r["false_repair"]
        elif tset == {"ood_gc"}:
            agg["gc_n"] += 1
            agg["gc_succ"] += r["success"]
            agg["gc_det"] += r["gc_detected"]
        elif tset == {"ood_gs"}:
            agg["gs_n"] += 1
            agg["gs_succ"] += r["success"]
        elif tset == {"ood_sem"}:
            agg["sem_n"] += 1
            agg["sem_succ"] += r["success"]
        elif tset == {"ood_exec"}:
            agg["exec_n"] += 1
            agg["exec_succ"] += r["success"]
    n = agg["n"]
    out = {
        "policy": policy,
        "success": agg["success"] / n,
        "cost": agg["cost"] / n,
        "succ_per_cost": (agg["success"] / n) / max(agg["cost"] / n, 1e-9),
        "vla_calls": agg["vla_calls"] / n,
        "ood_exec_succ": agg["exec_succ"] / agg["exec_n"] if agg["exec_n"] else None,
        "ood_sem_succ": agg["sem_succ"] / agg["sem_n"] if agg["sem_n"] else None,
        "ood_gc_succ": agg["gc_succ"] / agg["gc_n"] if agg["gc_n"] else None,
        "ood_gc_detect": agg["gc_det"] / agg["gc_n"] if agg["gc_n"] else None,
        "ood_gs_succ": agg["gs_succ"] / agg["gs_n"] if agg["gs_n"] else None,
        "id_succ": agg["id_succ"] / agg["id_n"] if agg["id_n"] else None,
        "id_false_repair": agg["id_flip"] / agg["id_n"] if agg["id_n"] else None,
        "id_cost": agg["id_cost"] / agg["id_n"] if agg["id_n"] else None,
    }
    return out


def main():
    N_MAIN, N_SENS = 12000, 8000
    results = {"config": {
        "N_main": N_MAIN, "N_sens": N_SENS, "pi": PI, "mix": MIX,
        "B": B_MAIN, "p_need": P_NEED,
        "params": {k: list(v) for k, v in PARAMS.items()},
        "probe_confirm": PROBE_CONFIRM, "reground_fix": REGROUND_FIX,
        "c_restore": C_RESTORE, "q_ff_id": Q_FF_ID, "noprobe": {
            "flip": NOPROBE_FLIP, "fix_gc": NOPROBE_FIX_GC},
        "seeds": {"main": 1601, "sens_qrg": 2601, "sens_qff": 2602,
                  "transient": 3601},
        "date": "2026-11-05",
    }, "main": [], "sens_qrg": [], "sens_qff": [], "transient": []}

    # ---- main table ----
    for pol in ("vla_only", "zest15", "audit", "audit_noprobe",
                "probe_always", "audit_rand", "oracle"):
        results["main"].append(cell(pol, N_MAIN, seed=1601))

    # ---- sensitivity: reground success q_rg ----
    for q in (0.60, 0.80, 0.90):
        row = {"q_rg": q}
        for pol in ("vla_only", "audit", "oracle"):
            row[pol] = cell(pol, N_SENS, seed=2601, q_rg=q)
        results["sens_qrg"].append(row)

    # ---- sensitivity: probe false-flip q_ff_id ----
    for q in (0.01, 0.02, 0.05):
        row = {"q_ff_id": q}
        for pol in ("vla_only", "audit"):
            row[pol] = cell(pol, N_SENS, seed=2602, q_ff_id=q)
        results["sens_qff"].append(row)

    # ---- transient grounding drift: ID for 5 blocks, then collapse ----
    def transient(rng):
        return ["id"] * 5 + ["ood_gc"] * 7

    for pol in ("vla_only", "zest15", "audit", "oracle"):
        results["transient"].append(
            cell(pol, N_SENS, seed=3601, types_fn=transient, p_need=5))

    out_path = __file__.replace("audit_sim.py", "audit_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=1)
    print("saved", out_path)
    for section in ("main", "transient"):
        print("\n==", section)
        for row in results[section]:
            print({k: (round(v, 3) if isinstance(v, float) else v)
                   for k, v in row.items() if k != "policy"},
                  row.get("policy", row.get("q_rg", row.get("q_ff_id"))))


if __name__ == "__main__":
    main()
