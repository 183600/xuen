"""Synthetic mechanism check for ZEST-VLA (round 15).

NOT benchmark evidence. Isolates one question:
when a frozen VLA is competent in-distribution but fails zero-shot, can
label-free self-supervised residuals + a risk-controlled gate decide when
to fall back to a compositional geometric primitive, without hurting ID?

Generative model (declared, not fit):
  - episode type: ID (p=1-pi), OOD-exec (p=pi*(1-rho)),
    OOD-semantic-mapok (p=pi*rho*mapok), OOD-semantic-silent (rest).
  - three residuals (temporal, geometric, goal-progress) are noisy views
    of the type; 'silent' OOD has ID-like residuals (the hard boundary).
  - SERVO progress ~ Bernoulli(c_true*0.9); FALLBACK ~ Bernoulli(g_true*0.8).
  - success = progress >= 3 within budget B; SERVO cost 1, FALLBACK 1.2.
  - gates observe only SERVO residuals (counterfactual); FALLBACK residuals
    are not diagnostic of VLA competence.
"""
import os, random, math, json, statistics

# ---------- small numeric helpers (pure Python) ----------
def beta_sample(a, b, rng):
    def gamma(k):
        if k < 1.0:
            return gamma(k + 1.0) * (rng.random() ** (1.0 / k))
        d = k - 1.0 / 3.0
        c = 1.0 / math.sqrt(9.0 * d)
        while True:
            x = rng.gauss(0.0, 1.0)
            v = (1.0 + c * x) ** 3
            if v <= 0.0:
                continue
            u = rng.random()
            if u < 1.0 - 0.0331 * (x ** 4):
                return d * v
            if math.log(u) < 0.5 * x * x + d * (1.0 - v + math.log(v)):
                return d * v
    x = gamma(a)
    y = gamma(b)
    return x / (x + y)

def quantile(xs, q):
    ys = sorted(xs)
    if not ys:
        return 0.0
    i = min(len(ys) - 1, max(0, int(math.ceil(q * len(ys))) - 1))
    return ys[i]

def beta_lb(a, b, z=1.28):
    """Mean - z*sd of Beta(a,b), clipped to [0,1] (conservative, cheap)."""
    m = a / (a + b)
    var = a * b / ((a + b) ** 2 * (a + b + 1.0))
    return max(0.0, min(1.0, m - z * math.sqrt(var)))

def clip(x, lo=0.0, hi=2.0):
    return max(lo, min(hi, x))

# ---------- generative model ----------
def sample_type(rng, pi, rho, mapok_frac, noisy_id_frac=0.15):
    if rng.random() >= pi:
        return "id_noisy" if rng.random() < noisy_id_frac else "id"
    if rng.random() >= rho:
        return "ood_exec"
    return "ood_sem_mapok" if rng.random() < mapok_frac else "ood_sem_silent"

def type_params(t):
    # (c_mean, g_mean, residual means (tmp, geo, goal), residual sigma)
    if t == "id":
        return 0.80, 0.50, (0.20, 0.20, 0.20), 0.10
    if t == "id_noisy":
        return 0.80, 0.50, (0.20, 0.20, 0.20), 0.40
    if t == "ood_exec":
        return 0.30, 0.60, (0.70, 0.70, 0.50), 0.10
    if t == "ood_sem_mapok":
        return 0.30, 0.60, (0.20, 0.20, 0.80), 0.10
    if t == "transient_low":
        return 0.20, 0.45, (0.70, 0.70, 0.50), 0.10
    return 0.30, 0.30, (0.20, 0.20, 0.20), 0.10  # silent semantic OOD

# ---------- episode ----------
def run_episode(t, policy, rng, B=10.0, q_raw=0.42, q_z=4.2,
                w=(1/3., 1/3., 1/3.), transient=False, switch=2,
                fb_cost=1.2, g_scale=1.0):
    cm, gm, mu, sigma = type_params(t)
    c_true = clip(rng.gauss(cm, 0.08), 0.0, 1.0)
    g_true = clip(rng.gauss(gm, 0.08), 0.0, 1.0)
    p_need = 4.0 if transient else 3.0
    progress = 0.0
    spent = 0.0
    raw_win = []
    cusum = 0.0
    mode = "vla"
    dwell = 0
    # CUSUM parameters: target surprise alpha, drift allowance k, threshold h
    alpha, k, h, W = 0.12, 0.05, 2.5, 5
    surprise_log = []
    ever_fb = False
    last_score = 0.0
    servo_steps = 0
    step_count = 0

    while spent < B - 1e-9 and progress < p_need:
        step_count += 1
        # transient OOD: after `switch` total actions, competence recovers
        if transient and step_count > switch:
            ct, gt, mut = 0.80, 0.45, (0.20, 0.20, 0.20)
        else:
            ct, gt, mut = c_true, g_true, mu

        # ---------- action selection ----------
        if policy == "vla":
            act = "servo"
        elif policy == "fallback":
            act = "fallback"
        elif policy == "oracle":
            act = "servo" if ct * 0.9 >= gt * 0.8 else "fallback"
        elif policy == "fixed":
            act = "fallback" if (len(raw_win) >= W and
                                  sum(raw_win) / len(raw_win) > q_raw) else "servo"
        elif policy in ("conformal", "recheck", "zest"):
            if policy == "conformal":
                act = "fallback" if cusum > h else "servo"
            else:
                if policy == "zest":
                    a_s = 1 + sum(1 for e in surprise_log if e == 0)
                    b_s = 1 + sum(1 for e in surprise_log if e == 1)
                    c_lb = beta_lb(a_s, b_s, 1.28)
                else:
                    c_lb = 0.0  # no Beta posterior in the recheck baseline
                if mode == "fallback":
                    dwell += 1
                    if dwell >= 3:
                        act = "servo"
                        mode = "probe"
                    else:
                        act = "fallback"
                else:
                    trigger = (cusum > h) and (policy != "zest" or c_lb < 0.60)
                    if trigger:
                        mode = "fallback"
                        dwell = 0
                        act = "fallback"
                    else:
                        act = "servo"
        else:
            raise ValueError(policy)

        if act == "fallback":
            ever_fb = True

        # ---------- execute ----------
        if act == "servo":
            servo_steps += 1
            ok = rng.random() < ct * 0.9
            rs = tuple(clip(rng.gauss(m, sigma)) for m in mut)
        else:
            ok = rng.random() < clip(gt * g_scale, 0.0, 1.0) * 0.8
            # fallback is geometrically consistent; residuals do not test the VLA
            rs = tuple(clip(rng.gauss(0.20, 0.10)) for _ in range(3))

        if ok:
            progress += 1.0
        spent += 1.0 if act == "servo" else fb_cost

        # ---------- gate update (only SERVO residuals are diagnostic) ----------
        if act == "servo":
            s = sum(w[i] * rs[i] for i in range(3))
            last_score = s
            raw_win.append(s)
            if len(raw_win) > W:
                raw_win.pop(0)
            recent = raw_win[-10:]
            med = statistics.median(recent)
            mad = statistics.median([abs(x - med) for x in recent])
            scale = 1.4826 * mad + 0.05
            z = s / scale
            surprise = 1 if z > q_z else 0
            surprise_log.append(surprise)
            cusum = max(0.0, cusum + surprise - alpha - k)
            if policy in ("recheck", "zest") and mode == "probe":
                if not surprise:
                    mode = "vla"
                    cusum = 0.0
                else:
                    mode = "fallback"
                    dwell = 0
        elif policy == "fixed":
            # naive gate also sees fallback residuals; this is a known weakness
            raw_win.append(0.20)
            if len(raw_win) > W:
                raw_win.pop(0)

    return (progress >= p_need), spent, ever_fb, last_score, len(surprise_log)

# ---------- evaluation ----------
def evaluate(policy, n=12000, pi=0.35, rho=0.3, mapok_frac=0.5,
             seed=3, q_raw=0.42, q_z=4.2, transient=False,
             fb_cost=1.2, g_scale=1.0):
    rng = random.Random(seed)
    succ, cost = [], []
    fb_id, fb_ood = [], []
    s_id, s_ood = [], []
    for _ in range(n):
        t = sample_type(rng, pi, rho, mapok_frac)
        if transient:
            t = "transient_low"  # starts incompetent, recovers after `switch` servo steps
        s, sp, ef, score, ns = run_episode(
            t, policy, rng, B=(12.0 if transient else 10.0), q_raw=q_raw,
            q_z=q_z, transient=transient, switch=5,
            fb_cost=fb_cost, g_scale=g_scale)
        succ.append(1 if s else 0)
        cost.append(sp)
        if transient:
            s_ood.append(score)
            fb_ood.append(1 if ef else 0)
        elif t.startswith("id"):
            fb_id.append(1 if ef else 0)
            s_id.append(score)
        else:
            fb_ood.append(1 if ef else 0)
            s_ood.append(score)
    wins = 0.0
    for p in s_ood:
        for nv in s_id:
            wins += 1.0 if p > nv else 0.5 if p == nv else 0.0
    auroc = wins / max(1, len(s_ood) * len(s_id))
    return dict(succ=statistics.mean(succ), cost=statistics.mean(cost),
                spc=statistics.mean(succ) / statistics.mean(cost),
                fb_id=statistics.mean(fb_id) if fb_id else 0.0,
                fb_ood=statistics.mean(fb_ood) if fb_ood else 0.0,
                auroc=auroc)

def calibrate_qz(n=5000, seed=99):
    rng = random.Random(seed)
    cal = []
    for _ in range(n):
        noisy = rng.random() < 0.15
        sig = 0.40 if noisy else 0.10
        win = []
        for _ in range(6):
            rs = [clip(rng.gauss(0.20, sig)) for _ in range(3)]
            s = sum(rs) / 3.0
            win.append(s)
            recent = win[-10:]
            med = statistics.median(recent)
            mad = statistics.median([abs(x - med) for x in recent])
            scale = 1.4826 * mad + 0.05
            cal.append(s / scale)
    return quantile(cal, 0.90)

# ---------- residual-channel ablation (classification view) ----------
def residual_ablation(n=40000, seed=5, sigma=0.25):
    rng = random.Random(seed)
    classes = ["id", "ood_exec", "ood_sem_mapok", "ood_sem_silent"]
    data = {c: [] for c in classes}
    for c in classes:
        _, _, mu, _ = type_params(c)
        for _ in range(n):
            rs = tuple(clip(rng.gauss(m, sigma)) for m in mu)
            data[c].append(rs)
    def auroc(pos, neg, fn):
        wins = 0.0
        for x in pos:
            fx = fn(x)
            for y in neg:
                fy = fn(y)
                wins += 1.0 if fx > fy else 0.5 if fx == fy else 0.0
        return wins / (len(pos) * len(neg))
    # downsample for pairwise AUROC cost
    m = min(4000, n)
    out = {}
    for ch, name in [(0, "temporal"), (1, "geometric"), (2, "goal")]:
        out[name] = {
            "exec_vs_id": round(auroc(data["ood_exec"][:m], data["id"][:m], lambda r: r[ch]), 3),
            "mapok_vs_id": round(auroc(data["ood_sem_mapok"][:m], data["id"][:m], lambda r: r[ch]), 3),
            "silent_vs_id": round(auroc(data["ood_sem_silent"][:m], data["id"][:m], lambda r: r[ch]), 3),
        }
    out["combined_equal"] = {
        "exec_vs_id": round(auroc(data["ood_exec"][:m], data["id"][:m], lambda r: sum(r) / 3), 3),
        "mapok_vs_id": round(auroc(data["ood_sem_mapok"][:m], data["id"][:m], lambda r: sum(r) / 3), 3),
        "silent_vs_id": round(auroc(data["ood_sem_silent"][:m], data["id"][:m], lambda r: sum(r) / 3), 3),
    }
    return out

if __name__ == "__main__":
    qz = calibrate_qz()
    print("calibrated q_z =", round(qz, 3))
    policies = ["vla", "fallback", "fixed", "conformal", "recheck", "zest", "oracle"]
    rows = []
    for rho in (0.0, 0.25, 0.50):
        print("\n=== static OOD, silent fraction rho =", rho)
        for pol in policies:
            r = evaluate(pol, n=12000, pi=0.35, rho=rho, q_z=qz)
            r.update(policy=pol, rho=rho, scenario="static")
            rows.append(r)
            print(f"{pol:10s} succ {r['succ']:.3f} cost {r['cost']:.2f} "
                  f"spc {r['spc']:.3f} fb_id {r['fb_id']:.3f} "
                  f"fb_ood {r['fb_ood']:.3f} auroc {r['auroc']:.3f}")
    print("\n=== transient OOD (competence recovers after 5 actions)")
    for pol in policies:
        r = evaluate(pol, n=12000, pi=1.0, rho=0.0, q_z=qz, transient=True)
        r.update(policy=pol, rho=None, scenario="transient")
        rows.append(r)
        print(f"{pol:10s} succ {r['succ']:.3f} cost {r['cost']:.2f} "
              f"spc {r['spc']:.3f} fb_ood {r['fb_ood']:.3f}")
    sens = []
    print("\n=== sensitivity: static rho=0.25, fallback quality/cost")
    for gs in (0.75, 1.0, 1.25):
        for fc in (1.0, 1.2, 1.5):
            rv = evaluate("vla", n=8000, pi=0.35, rho=0.25, q_z=qz,
                          fb_cost=fc, g_scale=gs)
            rz = evaluate("zest", n=8000, pi=0.35, rho=0.25, q_z=qz,
                          fb_cost=fc, g_scale=gs)
            row = {"g_scale": gs, "fb_cost": fc,
                   "vla_succ": round(rv["succ"], 3), "zest_succ": round(rz["succ"], 3),
                   "delta_pp": round(100 * (rz["succ"] - rv["succ"]), 2),
                   "vla_spc": round(rv["spc"], 3), "zest_spc": round(rz["spc"], 3)}
            sens.append(row)
            print(row)
    abl = residual_ablation()
    print("\n=== residual channel ablation (AUROC)")
    for k, v in abl.items():
        print(k, v)
    out = {"calibration_qz": qz, "rows": rows, "sensitivity": sens, "ablation": abl}
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zest_results.json")
    json.dump(out, open(path, "w"), indent=2)
    print("\nwrote", path)
