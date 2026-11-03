"""Round-16 evidence: sensorless "virtual torque" channel and fault isolation on public UniBot-V1 data.

Two experiments, both explicit about what they are NOT:

E1 (DATA-GROUNDED, B-level): from the public challenge demonstrations
    (HuggingFace unitreerobotics/G1_Dex1_<Task>, LeRobot v3.0, 30 fps) we
    identify the arm servo model  q[t+1] = q[t] + kappa * (q_cmd[t-lag] - q[t])
    per joint, and we test whether the *commanded-vs-realised tracking residual*
    is a usable proxy for contact load, i.e. whether it separates free-space
    motion from load-bearing (carrying) motion.  Also measures the gripper
    stall channel (commanded vs realised opening) and EE-vs-joint consistency.

    Everything here is measured on demonstration data, whose action field is a
    joint-space target.  It is evidence about the *plant/observability*, not
    about UniBot task success.

E2 (SYNTHETIC, mechanism check): inject seven plant faults into the E1-identified
    model and test a deterministic diagnosis rule set for DETECTION and
    ISOLATION (which joint), against a global-threshold baseline, under a
    confounder: external load also enlarges tracking residuals.

Retrieval dates:
    cached pages  : 2026-11-02 (UTC)  (from ../duo_rows_cache)
    fresh pages   : 2026-11-03 (UTC)  (fetched by this script into ./r16_rows_cache)

Usage:  PYTHONPATH=<repo>/workspace/.pylibs python3 exp/r16_virtual_torque.py
"""
import json
import os
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://huggingface.co/api/datasets/unitreerobotics/G1_Dex1_{}/parquet"
ROWS_API = "https://datasets-server.huggingface.co/rows"
DUO_CACHE = os.path.join(HERE, "duo_rows_cache")
CACHE = os.path.join(HERE, "r16_rows_cache")
PAGE = 100
PAGES = 30                      # 3000 frames per dataset
LAGS = (0, 1, 2, 3, 4)
GRIP_OPEN = 4.0                 # Dex1 opening: 5.5 open ... 0 closed
GRIP_CLOSED = 1.0

# contact-heavy tasks already cached on 2026-11-02 + free-space-heavy tasks fetched today
CONTACT_TASKS = ["Unlock", "SyringeWaterTransfer", "PourOutMedicine", "PlugInEthernet",
                 "PlugCharger", "HangCup", "DisconnectEthernet"]
FRESH_TASKS = ["ArrangePlates", "SpellRobot", "PickOutBatteries", "PlacePhotoFrame",
               "OrganizeBookshelf", "StackBowls"]


# ----------------------------------------------------------------- data layer
def _read_rows(ds, offset):
    """Return the list of row dicts for one dataset page (cache first)."""
    for root in (CACHE, DUO_CACHE):
        path = os.path.join(root, f"{ds}_{offset}.json")
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f).get("rows", [])
    url = f"{ROWS_API}?dataset=unitreerobotics/G1_Dex1_{ds}&config=default&split=train&offset={offset}&length={PAGE}"
    with urllib.request.urlopen(url, timeout=120) as r:
        payload = json.load(r)
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, f"{ds}_{offset}.json"), "w") as f:
        json.dump(payload, f)
    return payload.get("rows", [])


def fetch_task(ds, pages=PAGES):
    with ThreadPoolExecutor(max_workers=8) as ex:
        chunks = list(ex.map(lambda o: _read_rows(ds, o), range(0, pages * PAGE, PAGE)))
    rows = []
    for c in chunks:
        rows.extend(c)
    return rows


def episodes_from_rows(rows):
    """Group rows into episodes; each episode is a dict of contiguous float arrays."""
    eps = {}
    for r in rows:
        tr = r.get("row", r)
        ei = int(tr["episode_index"])
        eps.setdefault(ei, []).append((int(tr["frame_index"]), tr))
    out = []
    for ei in sorted(eps):
        fr = sorted(eps[ei], key=lambda x: x[0])
        out.append((ei, [t for _, t in fr]))
    return out


def stack_episode(frames):
    """Turn one episode's rows into numpy arrays (skip episodes with missing keys)."""
    def col(key, dim=None):
        vals = []
        for t in frames:
            v = t.get(key)
            if v is None:
                return None
            v = np.asarray(v, dtype=np.float64).ravel()
            if dim is not None and v.size != dim:
                return None
            vals.append(v)
        return np.asarray(vals)

    rec = {
        "frame_index": np.asarray([int(t["frame_index"]) for t in frames]),
        "q_left": col("observation.state.left_arm", 7),
        "q_right": col("observation.state.right_arm", 7),
        "qc_left": col("action.left_arm", 7),
        "qc_right": col("action.right_arm", 7),
        "g_left": col("observation.state.left_gripper", 1),
        "g_right": col("observation.state.right_gripper", 1),
        "gc_left": col("action.left_gripper", 1),
        "gc_right": col("action.right_gripper", 1),
        "ee_left": col("observation.state.left_ee_pose_gripper_base", 6),
        "ee_right": col("observation.state.right_ee_pose_gripper_base", 6),
        "lb_obs": col("observation.state.lower_body", 15),
        "lb_cmd": col("action.lower_body", 15),
    }
    if any(v is None for v in rec.values()):
        return None
    return rec


# -------------------------------------------------------------- identification
def identify_servo(q, qc, lags=LAGS):
    """Least-squares identification of the one-tap servo model per joint.

    q[t+1] - q[t] = kappa * (qc[t-lag] - q[t]) + eps
    Returns dict with best lag, kappa, residual scale per joint.
    """
    T = q.shape[0]
    best = None
    for lag in lags:
        ks, res = [], []
        for j in range(q.shape[1]):
            xs, ys = [], []
            for t in range(lag, T - 1):
                x = qc[t - lag, j] - q[t, j]
                y = q[t + 1, j] - q[t, j]
                xs.append(x)
                ys.append(y)
            xs = np.asarray(xs)
            ys = np.asarray(ys)
            den = float(xs @ xs)
            k = float(xs @ ys / den) if den > 1e-12 else 0.0
            r = ys - k * xs
            ks.append(k)
            res.append(np.median(np.abs(r)) if r.size else 0.0)
        score = float(np.mean(res))
        if best is None or score < best["score"]:
            best = {"lag": lag, "kappa": np.asarray(ks), "res_med": np.asarray(res), "score": score}
    return best


def servo_residual(q, qc, kappa, lag):
    """Signed tracking residual r[t] = q[t+1]-q[t] - kappa*(qc[t-lag]-q[t]) (per joint)."""
    T = q.shape[0]
    r = np.zeros((T - 1, q.shape[1]))
    for t in range(lag, T - 1):
        r[t - lag] = (q[t + 1] - q[t]) - kappa * (qc[t - lag] - q[t])
    return r


# ------------------------------------------------------------------ statistics
def auroc(pos, neg):
    """AUROC of pos scores vs neg scores (rank based, ties averaged)."""
    pos = np.asarray(pos, dtype=np.float64).ravel()
    neg = np.asarray(neg, dtype=np.float64).ravel()
    if pos.size == 0 or neg.size == 0:
        return float("nan")
    allv = np.concatenate([pos, neg])
    order = np.argsort(allv, kind="mergesort")
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.arange(1, allv.size + 1)
    # average ranks for ties
    vals = allv[order]
    i = 0
    while i < vals.size:
        j = i
        while j + 1 < vals.size and vals[j + 1] == vals[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    rp = ranks[:pos.size].sum()
    return float((rp - pos.size * (pos.size + 1) / 2.0) / (pos.size * neg.size))


def phase_labels(rec, arm):
    """Label frames with observation-only phase tags.

    free  : gripper commanded open (not carrying anything)
    hold  : gripper commanded closed AND realised closed AND EE rose > 2 cm in the
            last 15 frames -> carrying a load
    closed: gripper closed but not lifting (pressing / inserting / resting)
    """
    g = rec[f"g_{arm}"].ravel()
    gc = rec[f"gc_{arm}"].ravel()
    ee = rec[f"ee_{arm}"]
    z = ee[:, 2]
    n = len(z)
    dz = np.zeros(n)
    for t in range(n):
        j = max(0, t - 15)
        dz[t] = z[t] - z[j]
    free = gc > GRIP_OPEN
    closed = gc <= GRIP_CLOSED
    hold = closed & (g <= 1.5) & (dz > 0.02)
    rest = closed & ~hold
    return free, hold, rest


# --------------------------------------------------------------------- E1 main
def run_e1(tasks, verbose=True):
    per_task = {}
    pooled = {"left": [], "right": []}
    grip_stats = {}
    for ds in tasks:
        rows = fetch_task(ds)
        eps = episodes_from_rows(rows)
        tstats = {"n_frames": 0, "n_episodes": 0, "arms": {}}
        gripper = {"stall_frac": [], "stall_max": []}
        lb_static = True
        lb_dev = 0.0
        for _, frames in eps:
            rec = stack_episode(frames)
            if rec is None:
                continue
            tstats["n_episodes"] += 1
            tstats["n_frames"] += len(rec["frame_index"])
            lb_dev = max(lb_dev, float(np.max(np.abs(rec["lb_obs"] - rec["lb_cmd"]))))
            if np.max(np.abs(rec["lb_obs"] - rec["lb_cmd"])) > 1e-6:
                lb_static = False
            for arm in ("left", "right"):
                q, qc = rec[f"q_{arm}"], rec[f"qc_{arm}"]
                ident = identify_servo(q, qc)
                r = servo_residual(q, qc, ident["kappa"], ident["lag"])
                free, hold, rest = phase_labels(rec, arm)
                # residual at frame t corresponds to transition t -> t+1
                m_free = free[:-1]
                m_hold = hold[:-1]
                m_rest = rest[:-1]
                z = r / (ident["res_med"] * 1.4826 + 1e-9)
                s = np.linalg.norm(z, axis=1)
                pooled[arm].append({
                    "res": r, "z": z, "s": s,
                    "m_free": m_free, "m_hold": m_hold, "m_rest": m_rest,
                    "kappa": ident["kappa"], "lag": ident["lag"],
                    "x_mag": np.abs(qc[:-1] - q[:-1]),
                })
                a = tstats["arms"].setdefault(arm, {"free": [], "hold": [], "rest": [], "perjoint": {}})
                a["free"].append(s[m_free])
                a["hold"].append(s[m_hold])
                a["rest"].append(s[m_rest])
                for j in range(7):
                    a["perjoint"].setdefault(j, {"free": [], "hold": []})
                    a["perjoint"][j]["free"].append(np.abs(r[m_free, j]))
                    a["perjoint"][j]["hold"].append(np.abs(r[m_hold, j]))
                g, gc = rec[f"g_{arm}"].ravel(), rec[f"gc_{arm}"].ravel()
                stall = np.maximum(0.0, gc - g)
                gripper["stall_frac"].append(float(np.mean(stall > 0.5)))
                gripper["stall_max"].append(float(np.max(stall)))
        arms_out = {}
        for arm, a in tstats["arms"].items():
            fr = np.concatenate(a["free"]) if a["free"] else np.array([])
            hd = np.concatenate(a["hold"]) if a["hold"] else np.array([])
            rs = np.concatenate(a["rest"]) if a["rest"] else np.array([])
            pj = {}
            for j, d in a["perjoint"].items():
                f = np.concatenate(d["free"]) if d["free"] else np.array([])
                h = np.concatenate(d["hold"]) if d["hold"] else np.array([])
                pj[j] = {"auroc": auroc(h, f), "free_med": float(np.median(f)) if f.size else None,
                         "hold_med": float(np.median(h)) if h.size else None,
                         "free_n": int(f.size), "hold_n": int(h.size)}
            arms_out[arm] = {"auroc_free_vs_hold": auroc(hd, fr),
                             "n_free": int(fr.size), "n_hold": int(hd.size), "n_rest": int(rs.size),
                             "free_med": float(np.median(fr)) if fr.size else None,
                             "hold_med": float(np.median(hd)) if hd.size else None,
                             "perjoint": pj}
        ident_all = {}
        for arm in ("left", "right"):
            ks = [p["kappa"] for p in pooled[arm] if p["kappa"] is not None]
            lags = [p["lag"] for p in pooled[arm]]
            if ks:
                ident_all[arm] = {"kappa_mean": np.mean(np.stack(ks), axis=0).tolist(),
                                  "lag_hist": {str(l): int(sum(1 for x in lags if x == l)) for l in LAGS}}
        per_task[ds] = {"arms": arms_out, "ident": ident_all,
                        "lower_body_action_eq_obs": lb_static, "lower_body_max_dev": lb_dev,
                        "gripper_stall_frac_mean": float(np.mean(gripper["stall_frac"])) if gripper["stall_frac"] else None,
                        "gripper_stall_max": float(np.max(gripper["stall_max"])) if gripper["stall_max"] else None,
                        "n_frames": tstats["n_frames"], "n_episodes": tstats["n_episodes"]}
        if verbose:
            print(f"[E1] {ds:22s} frames={tstats['n_frames']:6d} eps={tstats['n_episodes']:4d} "
                  f"auroc(L free-vs-hold)={arms_out['left']['auroc_free_vs_hold']:.3f} "
                  f"lagL={ident_all.get('left',{}).get('lag_hist')} "
                  f"kappaL={[round(x,3) for x in ident_all.get('left',{}).get('kappa_mean',[])]}")

    # pooled identification + pooled separability
    pooled_out = {}
    for arm in ("left", "right"):
        ps = pooled[arm]
        if not ps:
            continue
        kappa = np.mean(np.stack([p["kappa"] for p in ps]), axis=0)
        lag_hist = {str(l): int(sum(1 for p in ps if p["lag"] == l)) for l in LAGS}
        s = np.concatenate([p["s"] for p in ps])
        mf = np.concatenate([p["m_free"] for p in ps])
        mh = np.concatenate([p["m_hold"] for p in ps])
        mr = np.concatenate([p["m_rest"] for p in ps])
        xm = np.concatenate([p["x_mag"] for p in ps])
        ctrl_cmd = np.linalg.norm(xm, axis=1)
        ctrl_speed = np.concatenate([np.abs(np.diff(p["res"], axis=0)) for p in ps]) if ps else np.array([])
        allres = np.concatenate([p["res"] for p in ps], axis=0)
        sig_j = 1.4826 * np.median(np.abs(allres - np.median(allres, axis=0)), axis=0)
        pooled_out[arm] = {
            "kappa_mean": kappa.tolist(),
            "kappa_std": np.std(np.stack([p["kappa"] for p in ps]), axis=0).tolist(),
            "sigma_joint": sig_j.tolist(),
            "lag_hist": lag_hist,
            "auroc_free_vs_hold": auroc(s[mh], s[mf]),
            "auroc_free_vs_rest": auroc(s[mr], s[mf]),
            "n_free": int(mf.sum()), "n_hold": int(mh.sum()), "n_rest": int(mr.sum()),
            "control_auroc_cmd_magnitude": auroc(ctrl_cmd[mh], ctrl_cmd[mf]),
            "free_med_s": float(np.median(s[mf])), "hold_med_s": float(np.median(s[mh])),
            "rest_med_s": float(np.median(s[mr])) if mr.sum() else None,
        }
    return per_task, pooled_out


# --------------------------------------------------------------------- E2 main
def synth_episode(rng, n, kappa, sigma, fault=None, joint=0, load_phase=None,
                  deadband=0.0, latency=0, bias=0.0, sat=None):
    """Simulate the identified servo plant with an optional fault and optional load."""
    cmd = np.zeros((n, kappa.size))
    x = np.zeros((n, kappa.size))
    step = rng.normal(0, 0.01, size=(n, kappa.size)).cumsum(0) * 0.5
    for t in range(n):
        cmd[t] = step[t]
    if fault == "gain_drop":
        kappa = kappa.copy()
        kappa[joint] *= 0.55
    if fault == "saturation" and sat is not None:
        cmd = np.clip(cmd, -sat, sat)
    if fault == "encoder_bias":
        x += bias
    q = np.zeros((n, kappa.size))
    eps = rng.normal(0, 1, size=(n, kappa.size)) * sigma
    eff_cmd = cmd.copy()
    if fault == "latency":
        eff_cmd = np.concatenate([np.repeat(cmd[:1], latency, axis=0), cmd[:-latency]], axis=0)
    for t in range(n - 1):
        u = eff_cmd[t] - q[t]
        if fault == "deadband":
            u = np.sign(u) * np.maximum(0.0, np.abs(u) - deadband)
        dq = kappa * u + eps[t]
        q[t + 1] = q[t] + dq
        if load_phase is not None and t >= load_phase:
            # external load (contact / gravity) injects a constant joint disturbance
            dq_load = rng.normal(0, 1) * 0.004
            q[t + 1] = q[t + 1] + dq_load * (1.0 if joint in (0, 1, 2) else 0.4)
    r = np.zeros((n - 1, kappa.size))
    lag = latency if fault == "latency" else 0
    for t in range(lag, n - 1):
        r[t - lag] = (q[t + 1] - q[t]) - kappa * (eff_cmd[t] - q[t])
    return q, cmd, eff_cmd, r


def diagnose(q, cmd_eff, kappa_true, sigma, fault_truth, joint_truth):
    """Deterministic diagnosis rules on top of the identified model.

    Feature set per joint: fitted gain kappa_hat, best lag, signed bias, dead-zone
    width (commands that produce almost no motion), saturation rate, spike rate.
    Returns (fault_label, joint_label).
    """
    T = q.shape[0]
    # best lag and gain per joint
    lags = []
    kappas = []
    for j in range(q.shape[1]):
        best = None
        for lag in (0, 1, 2, 3, 4):
            xs, ys = [], []
            for t in range(lag, T - 1):
                xs.append(cmd_eff[t - lag, j] - q[t, j])
                ys.append(q[t + 1, j] - q[t, j])
            xs = np.asarray(xs)
            ys = np.asarray(ys)
            den = float(xs @ xs)
            k = float(xs @ ys / den) if den > 1e-12 else 0.0
            rr = ys - k * xs
            score = float(np.median(np.abs(rr))) if rr.size else 0.0
            if best is None or score < best[0]:
                best = (score, lag, k)
        lags.append(best[1])
        kappas.append(best[2])
    kappas = np.asarray(kappas)
    lags = np.asarray(lags)
    j = int(np.argmin(kappas / np.maximum(kappa_true, 1e-6)))
    gain_ratio = kappas[j] / max(kappa_true[j], 1e-6)

    # dead-zone width: commands below this produce (almost) no motion
    x = cmd_eff[:, j] - q[:, j]
    y = q[1:, j] - q[:-1, j]
    m = np.abs(x[:-1]) < np.percentile(np.abs(x[:-1]), 40)
    dead = float(np.median(np.abs(y[m]))) if m.sum() > 5 else 0.0

    # signed bias: mean residual (constant offset => encoder bias)
    lagj = lags[j]
    res = []
    for t in range(lagj, T - 1):
        res.append((q[t + 1, j] - q[t, j]) - kappas[j] * (cmd_eff[t - lagj, j] - q[t, j]))
    res = np.asarray(res)
    bias_hat = float(np.mean(res))
    mad = float(np.median(np.abs(res - np.median(res)))) * 1.4826 + 1e-9
    spike_rate = float(np.mean(np.abs(res - np.median(res)) > 8 * mad))

    if lagj >= 2:
        return "LATENCY", j
    if gain_ratio < 0.75:
        return "GAIN_DROP", j
    if dead > 2.5 * sigma[j] and abs(bias_hat) < 3 * mad:
        return "DEADBAND", j
    if abs(bias_hat) > 8 * mad:
        return "ENCODER_BIAS", j
    if spike_rate > 0.02:
        return "NOISE_SPIKE", j
    return "HEALTHY", j


def run_e2(kappa, sigma, n_ep=200, seed=7):
    rng = np.random.default_rng(seed)
    faults = ["HEALTHY", "GAIN_DROP", "DEADBAND", "LATENCY", "ENCODER_BIAS", "SATURATION", "NOISE_SPIKE"]
    labels = ["HEALTHY", "GAIN_DROP", "DEADBAND", "LATENCY", "ENCODER_BIAS", "SATURATION", "NOISE_SPIKE"]
    confusion = {f: {g: 0 for g in labels} for f in labels}
    iso_ok = 0
    iso_total = 0
    load_confusion = {f: 0 for f in labels}
    base_fp = 0
    base_tp = 0
    base_total = 0
    for f in faults:
        for ep in range(n_ep):
            joint = int(rng.integers(0, kappa.size))
            load_phase = None
            if f == "HEALTHY" and rng.random() < 0.5:
                load_phase = int(rng.integers(40, 120))     # confounder: external load
            q, cmd, cmd_eff, r = synth_episode(
                rng, 180, kappa, sigma, fault=(None if f == "HEALTHY" else f), joint=joint,
                load_phase=load_phase,
                deadband=0.02 if f == "DEADBAND" else 0.0,
                latency=3 if f == "LATENCY" else 0,
                bias=0.012 if f == "ENCODER_BIAS" else 0.0,
                sat=0.02 if f == "SATURATION" else None,
            )
            # global-threshold baseline: is max |residual| beyond 4 sigma? (no isolation)
            peak = float(np.max(np.abs(r - np.median(r)))) / (np.median(sigma) + 1e-12)
            base_total += 1
            if f != "HEALTHY":
                if peak > 4.0:
                    base_tp += 1
            else:
                if peak > 4.0:
                    base_fp += 1
            pred, pj = diagnose(q, cmd_eff, kappa, sigma, f, joint)
            confusion[f][pred] += 1
            if f != "HEALTHY":
                iso_total += 1
                if pj == joint and pred == f:
                    iso_ok += 1
            else:
                if load_phase is not None and pred != "HEALTHY":
                    load_confusion[pred] += 1
    return {
        "n_per_cell": n_ep,
        "confusion": confusion,
        "detection_rate": {f: (sum(confusion[f][g] for g in labels if g != "HEALTHY") / n_ep) for f in labels},
        "false_alarm_healthy": confusion["HEALTHY"]["HEALTHY"] / n_ep,
        "isolation_accuracy": iso_ok / max(iso_total, 1),
        "load_confusion": load_confusion,
        "baseline_global_threshold": {"tp": base_tp, "fp": base_fp, "n": base_total,
                                      "fp_rate_healthy": base_fp / n_ep,
                                      "recall_faults": base_tp / max(base_total - n_ep, 1)},
    }


def main():
    out = {"meta": {"retrieved_cached": "2026-11-02", "retrieved_fresh": "2026-11-03",
                     "source": "HuggingFace unitreerobotics/G1_Dex1_<Task> (LeRobot v3.0, 30 fps)"}}
    tasks = CONTACT_TASKS + FRESH_TASKS
    per_task, pooled = run_e1(tasks)
    out["E1_per_task"] = per_task
    out["E1_pooled"] = pooled
    kappa = np.asarray(pooled["left"]["kappa_mean"])
    sigma = np.asarray(pooled["left"]["sigma_joint"])
    out["E2"] = run_e2(kappa, sigma)
    with open(os.path.join(HERE, "r16_results.json"), "w") as f:
        json.dump(out, f, indent=1, default=float)
    print("\n[E1 pooled left]", json.dumps(pooled["left"], indent=1, default=float)[:1200])
    print("\n[E2]", json.dumps(out["E2"], indent=1, default=float)[:2000])


if __name__ == "__main__":
    main()
