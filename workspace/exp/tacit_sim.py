"""TACIT-Gauge pilot simulation (synthetic sanity check, not hardware).

A. 1 kHz momentum-observer torque residual with a robust adaptive baseline,
   compared with a 30 Hz vision/joint baseline (83 ms pipeline delay).
B. Typed dialogue manager with value-of-information (VOI) questioning, and a
   torque certificate that vetoes physically inadmissible commitments.
"""
import json
import math
import numpy as np

RNG = np.random.default_rng(20261115)
DT = 1e-3
T = 1.2
STEPS = int(T / DT)
DOF = 3


def arm_once(contact_nm=0.0, model_err=0.15, noise=0.015, seed=0, K_O=80.0):
    rng = np.random.default_rng(seed)
    M = np.array([0.08, 0.05, 0.03])
    D = np.array([0.20, 0.15, 0.10])
    G = np.array([3.0, 2.0, 1.0])
    Kp = np.array([12.0, 10.0, 8.0])
    Kd = np.array([0.45, 0.40, 0.30])
    q = np.array([0.3, -0.2, 0.1])
    dq = np.zeros(DOF)
    r = np.zeros(DOF)
    t_contact = 0.55
    contact_dur = 0.20
    pattern = np.array([1.0, 0.6, 0.3]) / np.linalg.norm([1.0, 0.6, 0.3])
    pattern = pattern * contact_nm
    p_hat = None
    trace = []
    for k in range(STEPS):
        t = k * DT
        qd = np.array([0.4 * math.sin(2 * math.pi * 0.5 * t),
                       0.25 * math.sin(2 * math.pi * 0.5 * t + 0.7),
                       0.15 * math.sin(2 * math.pi * 0.5 * t + 1.1)])
        dqd = np.array([0.4 * math.pi * math.cos(2 * math.pi * 0.5 * t),
                        0.25 * math.pi * math.cos(2 * math.pi * 0.5 * t + 0.7),
                        0.15 * math.pi * math.cos(2 * math.pi * 0.5 * t + 1.1)])
        ddqd = -np.array([0.4, 0.25, 0.15]) * (math.pi ** 2) * np.sin(
            2 * math.pi * 0.5 * t + np.array([0.0, 0.7, 1.1]))
        g = G * np.sin(q)
        tau_cmd = M * ddqd + D * dqd + g + Kp * (qd - q) + Kd * (dqd - dq)
        active = 1.0 if (t_contact <= t < t_contact + contact_dur) else 0.0
        tau_ext = active * pattern
        ddq = (tau_cmd - D * dq - g + tau_ext) / M
        dq = dq + DT * ddq
        q = q + DT * dq
        tau_meas = tau_cmd + rng.normal(0.0, noise, DOF)
        g_hat = G * (1.0 - 0.5 * model_err) * np.sin(q)
        p = M * dq
        if p_hat is None:
            p_hat = p.copy()
        p_hat = p_hat + DT * (tau_meas - g_hat + r)
        r = K_O * (p - p_hat)
        vis = float(np.linalg.norm(q - qd)) if k % 33 == 0 else np.nan
        trace.append((t, r.copy(), vis, float(np.linalg.norm(tau_ext))))
    return trace


def detect_torque(tr, contact_start=0.55, window=250, k=4.0, floor=0.02):
    hist = []
    for t, r, _, _ in tr:
        hist.append(r.copy())
        if len(hist) > window:
            hist.pop(0)
        if t < contact_start or len(hist) < window:
            continue
        H = np.array(hist)
        med = np.median(H, axis=0)
        mad = np.median(np.abs(H - med), axis=0) * 1.4826
        thr = k * (mad + floor)
        if np.any(np.abs(r - med) > thr):
            return t
    return None


def detect_vision(tr, contact_start=0.55, thr=0.05):
    for t, _, vis, _ in tr:
        if t >= contact_start and not np.isnan(vis) and vis > thr:
            return t + 0.083  # 33 ms frame + 50 ms processing backlog
    return None


def run_torque():
    mags = [0.5, 0.7, 1.0, 1.5, 2.5, 4.0]
    out = []
    for c in mags:
        ds, vs = [], []
        for seed in range(80):
            tr = arm_once(contact_nm=c, seed=seed)
            d, v = detect_torque(tr), detect_vision(tr)
            if d is not None:
                ds.append(d - 0.55)
            if v is not None:
                vs.append(v - 0.55)
        out.append({
            "contact_nm": c,
            "torque_detect_rate": round(len(ds) / 80, 3),
            "torque_latency_ms_median": round(1000 * float(np.median(ds)), 1) if ds else None,
            "vision_detect_rate": round(len(vs) / 80, 3),
            "vision_latency_ms_median": round(1000 * float(np.median(vs)), 1) if vs else None,
        })
    fa = {}
    for me in [0.05, 0.15, 0.30]:
        alarms = 0
        for seed in range(80):
            tr = arm_once(contact_nm=0.0, seed=seed, model_err=me)
            if detect_torque(tr) is not None:
                alarms += 1
        fa[str(me)] = round(alarms / 80, 3)
    return {"sweep": out, "false_alarm_rate": fa}


# ---------------------------------------------------------------- dialogue
SCHEMAS = [
    {"id": "pick",    "env": 1.0, "risk": 0.1},
    {"id": "place",   "env": 1.2, "risk": 0.1},
    {"id": "push",    "env": 2.9, "risk": 0.8},
    {"id": "pull",    "env": 2.4, "risk": 0.7},
    {"id": "twist",   "env": 1.8, "risk": 0.6},
    {"id": "insert",  "env": 1.4, "risk": 0.9},
    {"id": "handover","env": 0.8, "risk": 0.2},
    {"id": "hold",    "env": 0.6, "risk": 0.1},
]
ENV_CAP = 2.0
FEASIBLE = [i for i, s in enumerate(SCHEMAS) if s["env"] <= ENV_CAP]
INFEASIBLE = [i for i, s in enumerate(SCHEMAS) if s["env"] > ENV_CAP]


def entropy(p):
    p = np.clip(p, 1e-12, 1.0)
    return float(-(p * np.log(p)).sum())


def make_belief(rng):
    true_idx = int(rng.choice(FEASIBLE))
    belief = np.zeros(len(SCHEMAS))
    belief[true_idx] = max(0.05, 0.40 + rng.normal(0, 0.06))
    if rng.random() < 0.45:
        decoy = int(rng.choice(INFEASIBLE))
    else:
        decoy = int(rng.choice([i for i in FEASIBLE if i != true_idx]))
    belief[decoy] = max(0.05, 0.35 + rng.normal(0, 0.06))
    rest = [i for i in range(len(SCHEMAS)) if i not in (true_idx, decoy)]
    for i in rest:
        belief[i] += 0.10 / len(rest)
    return belief / belief.sum(), true_idx


def ask(belief, true_idx, rng, acc=0.95):
    cand = list(np.argsort(-belief)[: max(2, int((belief > 0.03).sum()))])
    half = max(1, len(cand) // 2)
    group = cand[:half]
    ans = (true_idx in group)
    if rng.random() > acc:
        ans = not ans
    return group, ans


def update(belief, group, ans):
    b = belief.copy()
    mask = np.zeros_like(b, dtype=bool)
    mask[group] = True
    if ans:
        b[~mask] *= 0.04
    else:
        b[mask] *= 0.04
    s = b.sum()
    return b / s if s > 0 else np.ones_like(b) / len(b)


def p_unsafe(belief):
    return float(sum(belief[i] for i in INFEASIBLE))


def dialogue_episode(mode, rng, torque_gate=True):
    belief, true_idx = make_belief(rng)
    turns = 0
    unsafe_exec = False
    veto = False
    while mode != "never" and turns < 6:
        if mode == "always":
            if int((belief > 0.03).sum()) <= 1:
                break
        if mode == "voi":
            if p_unsafe(belief) * 12.0 < 0.20:
                break
            if entropy(belief) < 0.35:
                break
        group, ans = ask(belief, true_idx, rng)
        belief = update(belief, group, ans)
        turns += 1
    top = int(np.argmax(belief))
    if SCHEMAS[top]["env"] > ENV_CAP:
        if torque_gate:
            veto = True
            group = [i for i in INFEASIBLE if belief[i] > 0.03] or INFEASIBLE
            ans = (true_idx in group)
            if rng.random() > 0.95:
                ans = not ans
            belief = update(belief, group, ans)
            turns += 1
            top = int(np.argmax(belief))
            if SCHEMAS[top]["env"] > ENV_CAP:
                top = max(FEASIBLE, key=lambda i: belief[i])
        else:
            unsafe_exec = True
    success = (top == true_idx)
    return success, unsafe_exec, veto, turns


def run_dialogue():
    out = {}
    for gate in [True, False]:
        for mode in ["never", "always", "voi"]:
            succ, uns, vet, tns = [], [], [], []
            for _ in range(6000):
                s, u, v, t = dialogue_episode(mode, RNG, torque_gate=gate)
                succ.append(s); uns.append(u); vet.append(v); tns.append(t)
            key = f"{mode}{'+torque' if gate else ''}"
            out[key] = {
                "success_rate": round(float(np.mean(succ)), 3),
                "unsafe_execution_rate": round(float(np.mean(uns)), 3),
                "veto_rate": round(float(np.mean(vet)), 3),
                "mean_turns": round(float(np.mean(tns)), 2),
                "mean_dialogue_s": round(float(np.mean(tns)) * 0.8, 2),
            }
    return out


if __name__ == "__main__":
    res = {"torque": run_torque(), "dialogue": run_dialogue()}
    print(json.dumps(res, ensure_ascii=False, indent=2))
    with open("/home/runner/work/xuen/xuen/workspace/exp/tacit_results.json", "w",
              encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
