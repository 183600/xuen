"""Synthetic mechanism check for CHORD-VLA (inspiration loop round 1).

NOT benchmark evidence. Isolates one question:
in a cloud-edge flow-matching VLA, can we separate *policy failure* from
*explainable* residual caused by (a) harmonic-drive mechanism error and
(b) stale cloud plans, so that the trust gate does not confuse the two?

Generative model (declared, not fit):
  - episode type: ID, OOD-E (execution), OOD-S (semantic, map correct),
    OOD-G (silent grounding; residuals look like ID).
  - harmonic mechanism: reversal bursts + periodic transmission error;
    a calibrated low-dimensional explainer subtracts the predictable part.
  - cloud staleness: per-episode delay d; a flow certificate decides
    re-anchor vs replan. Re-anchoring reduces the stale residual.
  - flow certificate: curvature C, truncation error dN, sample agreement.
  - residuals: base(type) + mechanism + stale + noise.
  - gate: channel-wise split conformal (residual + flow) with a union
    bound, then CUSUM + fallback/probe (ZEST machinery).
  - success: per-step progress Bernoulli(c_true*0.9*comp) for SERVO,
    Bernoulli(g_true*0.8) for FALLBACK.
"""
import os, random, math, json, statistics

# ---------------- helpers ----------------
def clip(x, lo=0.0, hi=2.0):
    return max(lo, min(hi, x))

def quantile(xs, q):
    ys = sorted(xs)
    if not ys:
        return 0.0
    i = min(len(ys) - 1, max(0, int(math.ceil(q * len(ys))) - 1))
    return ys[i]

def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0

def sample_flow(t, rng):
    """Return curvature C, truncation error dN, sample agreement A."""
    if t == "ood_exec":
        C = abs(rng.gauss(0.35, 0.10)); dN = abs(rng.gauss(0.20, 0.05)); A = rng.betavariate(3, 3)
    elif t == "ood_sem_mapok":
        # semantic ambiguity: geometry looks plausible, but the flow is multimodal
        C = abs(rng.gauss(0.30, 0.08)); dN = abs(rng.gauss(0.08, 0.03)); A = rng.betavariate(2.5, 4.5)
    else:  # ID and silent OOD-G
        C = abs(rng.gauss(0.15, 0.05)); dN = abs(rng.gauss(0.05, 0.02)); A = rng.betavariate(8, 2)
    return C, dN, A

MECH_DIR = (0.9, 0.9, 0.1)
TE_DIR = (0.5, 0.5, 0.0)
STALE_DIR = (0.6, 0.6, 0.35)
ALIGN_DIR = MECH_DIR

# ---------------- generative model ----------------
def sample_type(rng, pi=0.35, rho=0.25, mapok_frac=0.5, noisy_id_frac=0.15):
    if rng.random() >= pi:
        return "id_noisy" if rng.random() < noisy_id_frac else "id"
    if rng.random() >= rho:
        return "ood_exec"
    return "ood_sem_mapok" if rng.random() < mapok_frac else "ood_sem_silent"

def type_params(t):
    if t == "id":
        return 0.80, 0.50, (0.20, 0.20, 0.20), 0.10
    if t == "id_noisy":
        return 0.80, 0.50, (0.20, 0.20, 0.20), 0.35
    if t == "ood_exec":
        return 0.30, 0.60, (0.70, 0.70, 0.50), 0.10
    if t == "ood_sem_mapok":
        # VLA chooses a semantically wrong but geometrically smooth mode
        return 0.30, 0.60, (0.25, 0.25, 0.45), 0.12
    return 0.30, 0.30, (0.20, 0.20, 0.20), 0.10  # ood_sem_silent (OOD-G)

# ---------------- policy flags ----------------
def flags(policy):
    return dict(
        gate=policy not in ("vla", "fallback", "oracle"),
        mech=policy in ("chord_flow", "chord_gate", "chord_adapt", "chord_core", "chord_no_stale"),
        stale=policy in ("chord_flow", "chord_gate", "chord_adapt", "chord_core", "chord_no_mech"),
        flow=policy in ("chord_flow", "chord_gate", "chord_adapt", "chord_no_mech", "chord_no_stale"),
        repair=policy in ("chord_flow", "chord_gate", "chord_adapt", "chord_core", "chord_no_mech"),
        adaptive=policy in ("chord_adapt",),
    )

# ---------------- one episode ----------------
def run_episode(t, policy, rng, cfg, q_res=1e9, q_flow=1e9, gate=True):
    fl = flags(policy)
    cm, gm, mu, sigma = type_params(t)
    c_true = clip(rng.gauss(cm, 0.08), 0.0, 1.0)
    g_true = clip(rng.gauss(gm, 0.08), 0.0, 1.0)
    p_need = 3.0
    B = 10.0

    # per-episode calibration drift
    h_hat = cfg["h_scale"] * (1.0 + rng.gauss(0.0, 0.05))
    k_hat = cfg["k_stale"] * (1.0 + rng.gauss(0.0, 0.05))
    # per-episode cloud delay: 75% no delay, else 1..3 steps
    u = rng.random()
    d_ep = 0 if u < 0.75 else (1 if u < 0.85 else (2 if u < 0.95 else 3))
    te_phase = rng.uniform(0, 2 * math.pi)
    replanned = False

    progress = 0.0
    spent = 0.0
    cusum = 0.0
    mode = "trust"
    dwell = 0
    ever_fb = False
    first_res = None
    first_flow = None
    surprised = 0
    servo_steps = 0
    alpha, k, h = 0.12, 0.05, 2.5

    rev = 0
    step = 0
    flow_enabled = False
    res_surp_win = []
    flow_anom_win = []
    while spent < B - 1e-9 and progress < p_need and step < 40:
        step += 1

        # reversal burst Markov chain
        if rev == 1:
            rev = 1 if rng.random() < 0.80 else 0
        else:
            rev = 1 if rng.random() < 0.20 else 0

        # mechanism (true and estimated)
        te = math.sin(2 * math.pi * step / 6.0 + te_phase)
        m_true = [cfg["h_scale"] * (rev * MECH_DIR[j] + cfg["te_amp"] * te * TE_DIR[j])
                  for j in range(3)]
        m_hat = [(h_hat + cfg.get("explain_bias", 0.0)) * (rev * MECH_DIR[j] + cfg["te_amp"] * te * TE_DIR[j])
                 + rng.gauss(0.0, 0.05) for j in range(3)]

        # flow certificate
        C, dN, A = sample_flow(t, rng)
        flow_score = cfg["wC"] * C + cfg["wN"] * dN + cfg["wA"] * (1.0 - A)

        # stale-plan decision
        stale = d_ep > 0
        replan = False
        if stale and fl["stale"] and fl["repair"]:
            if replanned:
                d_eff = 0.0
            elif fl["flow"] and C >= cfg["c_thresh"]:
                d_eff = 0.0
                replan = True
                replanned = True
            else:
                d_eff = cfg["rho_ra"] * d_ep
        else:
            d_eff = d_ep

        # true stale residual / competence penalty
        if stale:
            s_true = [cfg["k_stale"] * d_eff * STALE_DIR[j] for j in range(3)]
            if fl["stale"]:
                comp = 1.0 - cfg["stale_pen"] * d_eff
            else:
                comp = 1.0 - cfg["stale_pen"] * d_ep
        else:
            s_true = [0.0, 0.0, 0.0]
            comp = 1.0

        # base policy residual; OOD failure may align with reversal (over-whitening risk)
        if cfg.get("confound", False) and t == "ood_exec":
            # confounding scenario: failure is *only* in the mechanism direction
            base = [0.20, 0.20, 0.20]
            for j in range(3):
                base[j] += cfg["align"] * rev * ALIGN_DIR[j]
        else:
            base = list(mu)
            if t.startswith("ood") and cfg["align"] > 0.0:
                for j in range(3):
                    base[j] += cfg["align"] * rev * ALIGN_DIR[j]
        noise = [rng.gauss(0.0, sigma) for _ in range(3)]
        r_raw = [clip(base[j] + m_true[j] + s_true[j] + noise[j]) for j in range(3)]

        r_w = list(r_raw)
        if fl["mech"]:
            for j in range(3):
                r_w[j] = clip(r_w[j] - m_hat[j])
        if fl["stale"]:
            s_hat = [k_hat * d_eff * STALE_DIR[j] for j in range(3)]
            for j in range(3):
                r_w[j] = clip(r_w[j] - s_hat[j])

        res_score = mean(r_w)
        if first_res is None:
            first_res = res_score
            first_flow = flow_score

        # ---------------- action selection ----------------
        if policy == "vla":
            act = "servo"
        elif policy == "fallback":
            act = "fallback"
        elif policy == "oracle":
            act = "servo" if c_true * 0.9 >= g_true * 0.8 else "fallback"
        else:
            if replan:
                spent += cfg["c_replan"]
            if mode == "fallback":
                dwell += 1
                if dwell >= 3:
                    act = "servo"
                    mode = "probe"
                else:
                    act = "fallback"
            else:
                trigger = cusum > h
                if trigger:
                    mode = "fallback"
                    dwell = 0
                    act = "fallback"
                else:
                    act = "servo"

        if act == "fallback":
            ever_fb = True

        # ---------------- execute ----------------
        if act == "servo":
            servo_steps += 1
            ok = rng.random() < clip(c_true * comp) * 0.9
        else:
            ok = rng.random() < clip(g_true) * 0.8

        if ok:
            progress += 1.0
        spent += 1.0 if act == "servo" else 1.2

        # ---------------- gate update (channel-wise union) ----------------
        if fl["gate"] and act == "servo":
            res_surp = 1 if res_score > q_res else 0
            flow_anom = 1 if (fl["flow"] and flow_score > q_flow) else 0
            if fl.get("adaptive", False):
                res_surp_win.append(res_surp)
                flow_anom_win.append(flow_anom)
                if len(flow_anom_win) > 6:
                    res_surp_win.pop(0)
                    flow_anom_win.pop(0)
                # self-audit: residual is quiet but the flow is repeatedly anomalous
                if (len(flow_anom_win) >= 4
                        and mean(flow_anom_win) >= 0.5
                        and mean(res_surp_win) <= 0.10):
                    flow_enabled = True
                surprise = res_surp or (1 if (flow_enabled and flow_anom) else 0)
            else:
                surprise = res_surp or flow_anom
            surprised += surprise
            cusum = max(0.0, cusum + surprise - alpha - k)
            if mode == "probe":
                if not surprise:
                    mode = "trust"
                    cusum = 0.0
                else:
                    mode = "fallback"
                    dwell = 0
        elif fl["gate"] and act == "fallback":
            # fallback is not diagnostic of VLA competence; CUSUM decays
            cusum = max(0.0, cusum - alpha - k)

    return dict(success=(progress >= p_need), cost=spent, ever_fb=ever_fb,
                first_res=first_res, first_flow=first_flow,
                surprised=surprised, steps=step, type=t, d_ep=d_ep)

# ---------------- calibration ----------------
def calibrate(policy, cfg, n=5000, seed=99, alpha=0.12):
    rng = random.Random(seed)
    res, flow = [], []
    for _ in range(n):
        t = "id_noisy" if rng.random() < 0.15 else "id"
        r = run_episode(t, policy, rng, cfg, gate=False)
        if r["first_res"] is not None:
            res.append(r["first_res"])
            flow.append(r["first_flow"])
    if policy == "chord_gate":
        # residual gate at alpha-alpha_f, flow gate at a stringent alpha_f
        # so the union bound stays <= alpha without diluting the residual gate.
        alpha_f = 0.02
        q_res = quantile(res, 1.0 - (alpha - alpha_f))
        q_flow = quantile(flow, 1.0 - alpha_f)
    elif policy == "chord_adapt":
        # residual gate at alpha; flow cross-check is conditional and stringent
        q_res = quantile(res, 1.0 - alpha)
        q_flow = quantile(flow, 1.0 - 0.02)
    elif flags(policy)["flow"]:
        q_res = quantile(res, 1.0 - alpha / 2.0)
        q_flow = quantile(flow, 1.0 - alpha / 2.0)
    else:
        q_res = quantile(res, 1.0 - alpha)
        q_flow = 1e9
    return q_res, q_flow

# ---------------- evaluation ----------------
def evaluate(policy, cfg, q_res, q_flow, n=6000, seed=3, pi=0.35, rho=0.25,
             mapok_frac=0.5, scenario="static"):
    rng = random.Random(seed)
    succ, cost, fb_id, fb_ood = [], [], [], []
    s_id, s_ood = [], []
    for _ in range(n):
        t = sample_type(rng, pi, rho, mapok_frac)
        if scenario == "stale":
            t = "id" if rng.random() < 0.65 else "ood_exec"
        elif scenario == "confound":
            t = "id" if rng.random() < 0.65 else "ood_exec"
        r = run_episode(t, policy, rng, cfg, q_res=q_res, q_flow=q_flow)
        succ.append(1.0 if r["success"] else 0.0)
        cost.append(r["cost"])
        if t.startswith("id"):
            fb_id.append(1.0 if r["ever_fb"] else 0.0)
            s_id.append(r["first_res"])
        else:
            fb_ood.append(1.0 if r["ever_fb"] else 0.0)
            s_ood.append(r["first_res"])
    m = min(3000, len(s_id), len(s_ood))
    wins = 0.0
    for x in s_ood[:m]:
        for y in s_id[:m]:
            wins += 1.0 if x > y else 0.5 if x == y else 0.0
    auroc = wins / max(1, m * m)
    return dict(policy=policy, scenario=scenario,
                succ=mean(succ), cost=mean(cost), spc=mean(succ) / mean(cost),
                fb_id=mean(fb_id) if fb_id else 0.0,
                fb_ood=mean(fb_ood) if fb_ood else 0.0,
                auroc=auroc)

# ---------------- sensitivity: over-whitening / calibration bias ----------------
def overwhiten_sensitivity(cfg, policies, n=3000, seed=7):
    """OOD failures are correlated with reversals (align=0.6); a calibration
    bias `b` makes the explainer subtract part of the failure as mechanism.
    Re-calibrate per bias, because the explainer itself changed."""
    rows = []
    for bias in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
        c = dict(cfg); c["align"] = 1.2; c["explain_bias"] = bias
        c["confound"] = True
        for pol in policies:
            if flags(pol)["gate"]:
                q_res, q_flow = calibrate(pol, c, n=2500, seed=123)
            else:
                q_res, q_flow = 1e9, 1e9
            r = evaluate(pol, c, q_res, q_flow, n=n, seed=seed,
                         scenario="confound")
            rows.append({"bias": bias, **r})
    return rows

# ---------------- main ----------------
def main():
    cfg = dict(h_scale=0.45, te_amp=0.5, k_stale=0.18, stale_pen=0.04,
               rho_ra=0.20, c_replan=2.0, c_thresh=0.28,
               wC=1.5, wN=1.0, wA=0.5, w_flow=0.6, align=0.0, explain_bias=0.0)
    policies = ["vla", "fallback", "zest", "chord_no_mech", "chord_no_stale",
                "chord_core", "chord_flow", "chord_gate", "chord_adapt", "oracle"]
    qs = {}
    for pol in policies:
        if flags(pol)["gate"]:
            qs[pol] = calibrate(pol, cfg)
        else:
            qs[pol] = (1e9, 1e9)
    print("calibration q_res/q_flow:",
          {p: (round(qs[p][0], 3), round(qs[p][1], 3)) for p in policies})

    out = {"config": cfg,
           "calibration": {p: {"q_res": qs[p][0], "q_flow": qs[p][1]} for p in policies},
           "rows": [], "alignment": []}

    for rho in (0.0, 0.25, 0.50):
        print(f"\n=== static OOD, silent fraction rho={rho}")
        for pol in policies:
            r = evaluate(pol, cfg, *qs[pol], n=6000, rho=rho)
            out["rows"].append(r)
            print(f"{pol:16s} succ {r['succ']:.3f} cost {r['cost']:.2f} "
                  f"spc {r['spc']:.3f} fb_id {r['fb_id']:.3f} "
                  f"fb_ood {r['fb_ood']:.3f} auroc {r['auroc']:.3f}")

    print("\n=== stale-plan scenario (65% ID, 35% OOD-E; per-episode cloud delay)")
    for pol in policies:
        r = evaluate(pol, cfg, *qs[pol], n=6000, scenario="stale", seed=11)
        out["rows"].append(r)
        print(f"{pol:16s} succ {r['succ']:.3f} cost {r['cost']:.2f} "
              f"spc {r['spc']:.3f} fb_id {r['fb_id']:.3f} "
              f"fb_ood {r['fb_ood']:.3f} auroc {r['auroc']:.3f}")

    print("\n=== over-whitening sensitivity (OOD failures align with reversals)")
    for row in overwhiten_sensitivity(cfg, ["zest", "chord_core", "chord_flow", "chord_adapt"]):
        out["alignment"].append(row)
        print(f"bias {row['bias']:.2f} {row['policy']:12s} "
              f"succ {row['succ']:.3f} auroc {row['auroc']:.3f} "
              f"fb_ood {row['fb_ood']:.3f}")

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chord_results.json")
    json.dump(out, open(path, "w"), indent=2)
    print("\nwrote", path)

if __name__ == "__main__":
    main()
