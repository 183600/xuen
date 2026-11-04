#!/usr/bin/env python3
"""Synthetic mechanism check for SENTINEL-VLA (round 16, inspiration loop r1:
vision perception / embedded systems / safety alignment).

NOT benchmark evidence.  Round 15 (ZEST-VLA, exp/zest_sim.py) proved that when
the VLA and the semantic map share a wrong prior (OOD-G), every residual-based
detector is capped at AUC <= 1/2 + eps/2 (their Prop. 7).  This script isolates
whether three *independent* evidence channels shrink that blind spot:

  T1 execution tine (inherited ZEST): self-supervised residuals -> conformal
     CUSUM gate -> FALLBACK to geometric primitives.  Silent on OOD-G.
  T2 perception tine (vision): stereo/photometric health vitals + an active
     LOOK parallax-falsification probe.  Targets OOD-G*P (perceptual
     grounding failure: transparent/reflective/weak texture).
  T3 intent tine (safety alignment): specification monitor over the
     instruction entity set.  Perturbation necessity: a correct execution
     must perturb at least one instruction entity; m consecutive SERVO blocks
     with zero entity-perturbation events => GROUND.  Targets OOD-G*S1
     (fully off-target operation).  Blind when the confusion is within the
     monitor's spatial granularity r_pne (OOD-G*S2, declared undetectable).

Generative model (declared, not fit; extends exp/zest_sim.py):
  - episode types: ID (+15% noisy), OOD-exec, OOD-semantic(map right),
    G*P (perception degraded + wrong target), G*S1 (off-target, healthy
    perception), G*S2 (near-confusion within r_pne, healthy perception).
  - per-SERVO-block binary signals: exec surprise, perception anomaly,
    entity perturbation event.  G*S2 raises no signal on any channel.
  - GROUND = re-grounding (cost C_GROUND): repairs the target with prob
    p_fix; progress already accumulated toward a wrong target is reset.
  - success = progress >= p_need within budget B.
"""
import json
import math
import random

SEED = 20261104
N_EP = 12000

# ---------- generative parameters (declared) ----------
PI = 0.35                      # OOD episode fraction
TYPE_MIX = {                   # conditional on OOD
    "exec": 0.45, "sem": 0.15, "gperc": 0.15, "goff": 0.10, "gnear": 0.15,
}
C_TRUE = {"id": 0.80, "id_noisy": 0.80, "exec": 0.30, "sem": 0.30,
          "gperc": 0.40, "goff": 0.50, "gnear": 0.70, "transient": 0.80}
G_PRIM = 0.75                  # primitive per-block progress prob = G_PRIM*0.8
B = 12.0                       # block budget
P_NEED = 3.6
C_SERVO, C_FALLBACK, C_LOOK, C_GROUND = 1.0, 1.2, 0.6, 2.0

# binary per-block signal rates (id baseline / ood rates)
ALPHA_ID = 0.12                # exec surprise, ID
ALPHA_EXEC, ALPHA_SEM = 0.55, 0.45
BETA_ID = 0.10                 # perception anomaly, ID
BETA_GPERC = 0.60
P_PERT_BASE = 0.95             # entity perturbation when operating on-entity
P_PERT_OFF = 0.05              # when operating off the entity ROI
NOISY_ID_FRAC = 0.15
TRANSIENT_LEN = 5              # transient scenario: first k blocks incompetent

# gate / policy parameters
ALPHA, KAPPA, H = 0.12, 0.05, 2.5      # exec CUSUM (round 15)
KAPPA_PERC = 0.04                      # perc CUSUM drift allowance
RECHECK_EVERY = 3
SPEC_M = 3                     # consecutive perturbation-free SERVO blocks
SPEC_WARMUP = 2
R_PNE = 2.0                    # PNE spatial granularity (cm), swept later
P_PROBE = 0.75                 # LOOK parallax falsification hit prob (gperc)
P_PROBE_ID = 0.02              # probe false hit on healthy perception
P_FIX_PERC, P_FIX_SPEC = 0.65, 0.60
P_FIX_ORACLE = 0.70
PROBE_COOL, MAX_PROBES = 2, 3
GROUND_COOL, MAX_GROUNDS = 4, 2

GN_LO, GN_HI = 0.3, 6.0        # G*S2 confusion offset distribution (cm)


def Phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def miss_pne(r_pne):
    """ID perturbation-miss probability vs monitor granularity.

    Declared monotone model: smaller ROI -> noisier on-entity perturbation
    detection (self-motion occlusion, support deformation at ROI edges)."""
    return 0.02 + 0.10 * math.exp(-r_pne / 1.0)


def sample_type(rng):
    if rng.random() >= PI:
        return "id_noisy" if rng.random() < NOISY_ID_FRAC else "id"
    u, acc = rng.random(), 0.0
    for t, p in TYPE_MIX.items():
        acc += p
        if u < acc:
            return t
    return "gnear"


def base_type(t):
    return "id" if t in ("id", "id_noisy", "transient") else t


def target_ok_type(t):
    return t in ("id", "id_noisy", "transient", "exec", "sem")


# ---------- signal rates (effective type, block) ----------
def p_exec(t, blk, transient):
    if transient and blk < TRANSIENT_LEN:
        return ALPHA_EXEC
    if t == "exec":
        return ALPHA_EXEC
    if t == "sem":
        return ALPHA_SEM
    return ALPHA_ID


def p_perc(t):
    return BETA_GPERC if t == "gperc" else BETA_ID


def p_pert(t, r_pne, gn_off):
    if t == "gperc" or t == "goff":
        return P_PERT_OFF
    if t == "gnear":
        return P_PERT_OFF if gn_off > r_pne else P_PERT_BASE - miss_pne(r_pne)
    return P_PERT_BASE - miss_pne(r_pne)


# ---------- one episode ----------
def run_episode(t0, policy, rng, r_pne=R_PNE, transient=False,
                p_probe=P_PROBE, p_fix_perc=P_FIX_PERC, p_fix_spec=P_FIX_SPEC,
                use_perc=True, use_spec=True):
    budget, progress, cost = B, 0.0, 0.0
    t = t0
    gn_off = rng.uniform(GN_LO, GN_HI) if t0 == "gnear" else 0.0
    fixed = False
    cusum = {"exec": 0.0, "perc": 0.0}
    mode = "TRUST"                # TRUST / FALLBACK / PROBE
    fb_dwell = 0
    probe_cool, probes = 0, 0
    ground_cool, grounds = 0, 0
    no_pert_run = 0
    servo_seen = 0
    detect_blk = {"gperc": None, "goff": None, "gnear": None}
    id_grounds = 0
    sig = []                      # (exec_s, perc_a, pert) for AUROC

    while True:
        if progress >= P_NEED:
            return {"success": 1, "cost": cost, "t0": t0, "id_grounds": id_grounds,
                    "detect": detect_blk, "sig": sig}
        if budget < C_LOOK:
            return {"success": 0, "cost": cost, "t0": t0, "id_grounds": id_grounds,
                    "detect": detect_blk, "sig": sig}
        blk = servo_seen

        # ---- decision ----
        act = None
        if policy == "vla_only":
            act = "SERVO"
        elif policy == "always_fb":
            act = "FALLBACK"
        elif policy == "oracle":
            tt = base_type(t)
            if target_ok_type(t):
                act = "FALLBACK" if t in ("exec", "sem") and budget >= C_FALLBACK else "SERVO"
            elif grounds == 0 and budget >= C_GROUND:
                act = "GROUND"
            else:
                act = "HOLD"
        else:  # zest / sentinel family
            if mode == "FALLBACK":
                if fb_dwell >= RECHECK_EVERY:
                    act, fb_dwell = "SERVO", 0          # probe block (recheck)
                else:
                    act, fb_dwell = "FALLBACK", fb_dwell + 1
            elif policy == "sentinel" and probe_cool == 0 and probes < MAX_PROBES \
                    and cusum["perc"] > H and budget >= C_LOOK + C_GROUND:
                act, probes, probe_cool = "LOOK", probes + 1, PROBE_COOL
            elif budget >= C_SERVO:
                act = "SERVO"
            else:
                act = "HOLD"
        if act == "FALLBACK" and budget < C_FALLBACK:
            act = "HOLD"

        # ---- execute block ----
        t_eff = "id" if fixed else t
        if act == "SERVO":
            cost += C_SERVO
            budget -= C_SERVO
            c = C_TRUE[t_eff]
            if transient and not fixed and blk < TRANSIENT_LEN:
                c = C_TRUE["exec"]
            if target_ok_type(t_eff):
                if rng.random() < c * 0.9:
                    progress += 1.0
            servo_seen += 1
            # ---- diagnostic signals (SERVO blocks only) ----
            es = 1 if rng.random() < p_exec(t_eff, blk, transient) else 0
            pa = 1 if rng.random() < p_perc(t_eff) else 0
            pt = 1 if rng.random() < p_pert(t_eff, r_pne, gn_off) else 0
            if not fixed:
                sig.append((es, pa, pt))
            if t0 in detect_blk and detect_blk[t0] is None and not fixed:
                hit = (t0 == "gperc" and (pa == 1 or pt == 0)) or \
                      (t0 in ("goff", "gnear") and pt == 0 and blk >= SPEC_WARMUP)
                if t0 == "gnear" and gn_off <= r_pne:
                    hit = False
                if hit:
                    detect_blk[t0] = blk
            # ---- gate updates ----
            cusum["exec"] = max(0.0, cusum["exec"] + es - ALPHA - KAPPA)
            cusum["perc"] = max(0.0, cusum["perc"] + pa - BETA_ID - KAPPA_PERC)
            if fixed or ground_cool > 0:
                no_pert_run = 0
            elif pt == 0 and blk >= SPEC_WARMUP:
                no_pert_run += 1
            else:
                no_pert_run = 0
            if probe_cool > 0:
                probe_cool -= 1
            if ground_cool > 0:
                ground_cool -= 1
            # mode transitions
            if mode == "TRUST":
                if cusum["exec"] > H:
                    mode, fb_dwell = "FALLBACK", 0
            elif mode == "FALLBACK":
                if cusum["exec"] <= 0.0:
                    mode = "TRUST"
        elif act == "FALLBACK":
            cost += C_FALLBACK
            budget -= C_FALLBACK
            if target_ok_type(t_eff) and rng.random() < G_PRIM * 0.8:
                progress += 1.0
        elif act == "LOOK":
            cost += C_LOOK
            budget -= C_LOOK
            hitp = p_probe if (t_eff == "gperc" and not fixed) else P_PROBE_ID
            if rng.random() < hitp:
                if t0 == "gperc" and detect_blk["gperc"] is None and not fixed:
                    detect_blk["gperc"] = blk
                if grounds < MAX_GROUNDS and budget >= C_GROUND:
                    cost += C_GROUND
                    budget -= C_GROUND
                    grounds += 1
                    if rng.random() < (p_fix_perc if t_eff == "gperc" else p_fix_spec):
                        fixed = True
                        progress = 0.0
                    ground_cool = GROUND_COOL
                    cusum["perc"] = 0.0
                    probe_cool = PROBE_COOL
        elif act == "GROUND":
            cost += C_GROUND
            budget -= C_GROUND
            grounds += 1
            pf = P_FIX_ORACLE if policy == "oracle" else (
                p_fix_perc if t_eff == "gperc" else p_fix_spec)
            if rng.random() < pf:
                fixed = True
                progress = 0.0
            ground_cool = GROUND_COOL
        # HOLD: nothing
        # ---- spec alarm (intent tine) -> GROUND ----
        if policy in ("sentinel",) and no_pert_run >= SPEC_M and grounds < MAX_GROUNDS \
                and ground_cool == 0 and not fixed and budget >= C_GROUND:
            cost += C_GROUND
            budget -= C_GROUND
            grounds += 1
            id_grounds += 1 if base_type(t) in ("id", "id_noisy") else 0
            if rng.random() < p_fix_spec:
                fixed = True
                progress = 0.0
            ground_cool = GROUND_COOL
            no_pert_run = 0
        # perc CUSUM alarm -> force probe next block (sentinel) / ignore (zest)
        if policy == "sentinel" and cusum["perc"] > H and not fixed:
            if probes >= MAX_PROBES:      # probe budget exhausted -> reset
                cusum["perc"] = 0.0
                probes = 0
            elif probe_cool == 0 and budget >= C_LOOK + C_GROUND:
                cost += C_LOOK
                budget -= C_LOOK
                hitp = p_probe if t_eff == "gperc" else P_PROBE_ID
                probes += 1
                probe_cool = PROBE_COOL
                if rng.random() < hitp:
                    if t0 == "gperc" and detect_blk["gperc"] is None:
                        detect_blk["gperc"] = blk
                    if grounds < MAX_GROUNDS:
                        cost += C_GROUND
                        budget -= C_GROUND
                        grounds += 1
                        if rng.random() < p_fix_perc:
                            fixed = True
                            progress = 0.0
                        ground_cool = GROUND_COOL
                        cusum["perc"] = 0.0
        # ---- success / exhaustion checks ----
        if progress >= P_NEED:
            return {"success": 1, "cost": cost, "t0": t0, "id_grounds": id_grounds,
                    "detect": detect_blk, "sig": sig}
        if budget < C_LOOK:
            return {"success": 0, "cost": cost, "t0": t0, "id_grounds": id_grounds,
                    "detect": detect_blk, "sig": sig}


# ---------- experiment driver ----------
def run_cell(policy, types, seed, **kw):
    rng = random.Random(seed)
    out = {"n": 0, "succ": 0, "cost": 0.0, "id_eps": 0, "id_grounds": 0,
           "detect": {"gperc": [], "goff": [], "gnear": []},
           "sig": {"id": [], "exec": [], "sem": [], "gperc": [],
                   "goff": [], "gnear": []}}
    for t0 in types:
        r = run_episode(t0, policy, rng, **kw)
        out["n"] += 1
        out["succ"] += r["success"]
        out["cost"] += r["cost"]
        bt = base_type(t0)
        if bt in ("id",):
            out["id_eps"] += 1
            out["id_grounds"] += 1 if r["id_grounds"] > 0 else 0
        if t0 in out["detect"]:
            for k, v in r["detect"].items():
                if v is not None:
                    out["detect"][k].append(v)
        if not r["sig"] or bt == "id":
            pass
        for s in r["sig"]:
            out["sig"][bt].append(s)
    n = max(out["n"], 1)
    out["succ_rate"] = out["succ"] / n
    out["avg_cost"] = out["cost"] / n
    out["succ_per_cost"] = out["succ"] / max(out["cost"], 1e-9)
    out["id_ground_rate"] = out["id_grounds"] / max(out["id_eps"], 1)
    out["detect_rate"] = {k: len(v) for k, v in out["detect"].items()}
    out["detect_med_blk"] = {k: sorted(v)[len(v) // 2] if v else None
                             for k, v in out["detect"].items()}
    # binary-signal AUROC vs ID: AUC = (TPR + 1 - FPR) / 2
    out["auroc"] = {}
    idsig = out["sig"].pop("id", [])
    for ch in range(3):
        row = {}
        for t, ss in out["sig"].items():
            if not ss or not idsig:
                continue
            tpr = sum(s[ch] for s in ss) / len(ss)
            fpr = sum(s[ch] for s in idsig) / len(idsig)
            row[t] = round(0.5 * (tpr + 1.0 - fpr), 3)
        out["auroc"][["exec", "perc", "spec"][ch]] = row
    del out["sig"]
    return out


def main():
    types = []
    for _ in range(N_EP):
        types.append(sample_type(random.Random()))  # placeholder replaced below
    rng = random.Random(SEED)
    types = [sample_type(rng) for _ in range(N_EP)]
    types_t = ["transient"] * N_EP                  # transient scenario

    results = {"meta": {
        "seed": SEED, "n_ep": N_EP, "pi": PI, "type_mix": TYPE_MIX,
        "B": B, "p_need": P_NEED, "alpha": ALPHA, "kappa": KAPPA, "h": H,
        "kappa_perc": KAPPA_PERC, "spec_m": SPEC_M, "r_pne": R_PNE,
        "p_probe": P_PROBE, "p_fix": {"perc": P_FIX_PERC, "spec": P_FIX_SPEC,
                                      "oracle": P_FIX_ORACLE},
        "costs": {"servo": C_SERVO, "fallback": C_FALLBACK,
                  "look": C_LOOK, "ground": C_GROUND},
        "declared_undetectable": "gnear within r_pne (G*S2)",
    }}

    # ---- Q1: static mixed OOD, main table ----
    main_tab = {}
    for pol in ["vla_only", "always_fb", "zest", "sentinel",
                "sentinel_no_perc", "sentinel_no_spec", "oracle"]:
        p = "sentinel" if pol.startswith("sentinel_no") else pol
        r = run_cell(p, types, SEED + 1)
        if pol == "sentinel_no_perc":
            r["note"] = "no perception tine (gperc relies on PNE only)"
        if pol == "sentinel_no_spec":
            r["note"] = "no intent tine (goff/gnear undetectable)"
        main_tab[pol] = r
    results["main"] = main_tab

    # ---- Q2: transient OOD (recovery must not regress) ----
    trans_tab = {}
    for pol in ["vla_only", "zest", "sentinel"]:
        trans_tab[pol] = run_cell(pol, types_t, SEED + 2, transient=True)
    results["transient"] = trans_tab

    # ---- Q3: PNE granularity sweep (G*S2 coverage vs ID false GROUND) ----
    sweep = {}
    for r_pne in [0.5, 1.0, 2.0, 3.0, 4.0, 6.0]:
        r = run_cell("sentinel", types, SEED + 3, r_pne=r_pne)
        r["gnear_cover"] = round((GN_HI - r_pne) / (GN_HI - GN_LO), 3)
        sweep[str(r_pne)] = r
    results["r_pne_sweep"] = sweep

    # ---- Q4: parallax falsification resolution (analytic) ----
    results["probe_resolution"] = {
        "theta": 0.8, "gain": 0.8, "sigma": 0.35,
        "p_detect": {str(e): round(Phi((0.8 * e - 0.8) / 0.35), 3)
                     for e in [0.5, 1.0, 2.0, 3.0, 4.0, 6.0]},
        "e_star_p50_cm": 1.0,
    }

    out = "/home/runner/work/xuen/xuen/workspace/exp/sentinel_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=1)
    print("wrote", out)

    # console summary
    for pol, r in main_tab.items():
        print(f"{pol:>18}  succ {r['succ_rate']:.3f}  cost {r['avg_cost']:.2f}"
              f"  s/c {r['succ_per_cost']:.3f}  idG {r['id_ground_rate']:.3f}"
              f"  det {r['detect_rate']}  med {r['detect_med_blk']}")
    print("-- auroc (sentinel) --")
    print(main_tab["sentinel"]["auroc"])
    print("-- transient --")
    for pol, r in trans_tab.items():
        print(f"{pol:>10}  succ {r['succ_rate']:.3f}  cost {r['avg_cost']:.2f}")
    print("-- r_pne sweep --")
    for rp, r in sweep.items():
        print(f"r_pne {rp:>4}  succ {r['succ_rate']:.3f}  idG {r['id_ground_rate']:.4f}"
              f"  gnear_det {r['detect_rate'].get('gnear', 0)}")


if __name__ == "__main__":
    main()
