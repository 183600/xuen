#!/usr/bin/env python3
"""第 16 轮（CIVIC-VLA）合成实验：介入式 grounding 探针 / 守礼层（deontic guard）/ 情感调制

机制检查（B 级证据）：只回答「在声明生成模型下，三个新机制各自值多少、边界在哪」。
不证明真机收益；所有参数运行前冻结于 CFG，假设预注册于 PREREG，先于任何结果写入。

对照：vla（VLA-only）、zest（第 15 轮 CUSUM+复检+fallback）、civic（+介入探针）、
civic_n（+守礼层）、civic_na（+情感调制）、naive（固定暂停）。

预注册假设（PREREG，运行前固定）：
H1  civic − zest ≥ +2.0pp（主混合 γ=0.4）；ID 成功率回归 ≤1.5pp；probe 率 ≤20%；
    OOD-G-vd 子集提升 ≥ +20pp
H2  AUROC(r_iv | G-vd vs ID) ≥ 0.85（σ_iv=0.5）；AUROC(r_iv | G-vi vs ID) ∈ [0.45,0.60]
H3  civic_n − zest ≥ +15pp（干扰臂）；civic_n 碰撞率 ≤ 0.5× noguard；无干扰回归 ≤1pp
H4' civic_na ≥ civic_n + 1.5pp（干扰臂 succ/cost）；否则情感层剪枝为诊断量
H5  EV 门控 probe ≥ probe-always（succ/cost，主混合 γ=0.4）
H6  civic_n − naive ≥ +8pp（push 子集）
"""
import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "civic_results.json")

CFG = {
    "seed": 20261103,
    "n_static": 10000, "n_int": 10000, "n_transient": 8000, "n_diag": 8000,
    "n_calib": 4000,
    "B_static": 10.0, "p_need_static": 3,
    "B_int": 12.0, "p_need_int": 4,
    "pi": 0.40, "pE": 0.45, "mapok": 0.40, "noisy_id_frac": 0.15,
    "gamma_main": 0.40,
    # 每步成功率 = c*0.9 (SERVO) / g*0.8 (FALLBACK)
    "c": {"ID": 0.90, "nID": 0.90, "E": 0.35, "S": 0.40, "G": 0.30,
          "REC": 0.72, "STALE": 0.25, "REFOUN": 0.75},
    "g": {"ID": 0.85, "E": 0.70, "S": 0.70, "G": 0.15, "REC": 0.85,
          "STALE": 0.15, "REFOUN": 0.85},
    # 残差均值 (r_tmp, r_geo, r_goal)；OOD-G 刻意与 ID 近似同分布（静默）
    "rmean": {"ID": (0.0, 0.0, 0.0), "nID": (0.0, 0.0, 0.0),
              "E": (1.6, 1.5, 0.5), "S": (0.15, 0.15, 1.8),
              "G": (0.10, 0.10, 0.05), "REC": (0.0, 0.0, 0.0)},
    "noise": {"nID": 2.5, "REC": 1.3},
    "gate": {"alpha": 0.12, "k": 0.05, "h": 2.5, "cal_alpha": 0.10},
    "probe": {"cost": 2.5, "sigma_iv": 0.5, "base_iv": 0.1, "vd_iv": 1.4,
              "recov": 0.55, "lgcc_tp": 0.60, "lgcc_fp_id": 0.04,
              "lgcc_fp_ood": 0.10, "conf_tp": 0.50, "conf_fp": 0.08,
              "false_switch_penalty": 0.10},
    "cost": {"SERVO": 1.0, "FB": 1.2, "HOLD": 0.2},
    "int": {"hover": 0.40, "block": 0.30, "push": 0.30, "t0_lo": 2, "t0_hi": 8,
            "det_sens": 0.8, "p_col": 0.25, "watch_push_detect": 0.85,
            "unwatch_push_detect": 0.40, "reground_cost": 2.0,
            "reground_ok": 0.85, "naive_pause": 4, "zn_dwell": 2,
            "affect": {"col_scale": 0.5, "resume_arousal": 0.35, "vigil": 0.07,
                       "ema": 0.35, "theta": 0.35}},
}

PREREG = {
    "H1": "civic-zest >= +2.0pp (gamma=0.4); ID reg <=1.5pp; probe rate <=20%; vd uplift >= +20pp",
    "H2": "AUROC(iv|Gvd vs ID) >= 0.85 @ sigma_iv=0.5; AUROC(iv|Gvi vs ID) in [0.45,0.60]",
    "H3": "civic_n - zest >= +15pp (int arm); col(civic_n) <= 0.5*col(noguard); clean reg <=1pp",
    "H4p": "civic_na >= civic_n + 1.5pp succ/cost (int arm); else prune affect",
    "H5": "EV-gated probe >= probe-always on succ/cost (main mix gamma=0.4)",
    "H6": "civic_n - naive >= +8pp on push subset",
}


def quantile(xs, q):
    xs = sorted(xs)
    if not xs:
        return float("inf")
    i = min(len(xs) - 1, max(0, int(math.ceil(q * len(xs))) - 1))
    return xs[i]


def auroc(pos, neg):
    """Mann-Whitney rank AUROC."""
    if not pos or not neg:
        return float("nan")
    allv = [(v, 1) for v in pos] + [(v, 0) for v in neg]
    allv.sort(key=lambda t: t[0])
    ranks = {}
    i = 0
    while i < len(allv):
        j = i
        while j < len(allv) and allv[j][0] == allv[i][0]:
            j += 1
        r = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[k] = r
        i = j
    s = sum(ranks[k] for k, (_, lab) in enumerate(allv) if lab == 1)
    n1, n0 = len(pos), len(neg)
    return (s - n1 * (n1 + 1) / 2.0) / (n1 * n0)


def make_static_episode(i):
    rng = random.Random(CFG["seed"] * 1000003 + i)
    u = rng.random()
    if u < 1 - CFG["pi"]:
        typ = "nID" if rng.random() < CFG["noisy_id_frac"] else "ID"
    else:
        typ = "E" if rng.random() < CFG["pE"] else (
            "S" if rng.random() < CFG["mapok"] else "G")
    pr = CFG["probe"]
    if typ in ("ID", "nID"):
        lgcc = rng.random() < pr["lgcc_fp_id"]
        conf = rng.random() < pr["conf_fp"]
    elif typ == "G":
        lgcc = rng.random() < pr["lgcc_tp"]
        conf = rng.random() < pr["conf_tp"]
    else:
        lgcc = rng.random() < pr["lgcc_fp_ood"]
        conf = rng.random() < pr["conf_tp"]
    return {"i": i, "typ": typ, "lgcc": lgcc, "conf": conf,
            "u_iv": rng.random(), "seed": CFG["seed"] * 1000003 + i}


def nscale_of(typ):
    return CFG["noise"].get(typ, 1.0)


def sample_s(rng, typ):
    m = CFG["rmean"][typ if typ in CFG["rmean"] else "G"]
    n = nscale_of(typ)
    return sum(mk + rng.gauss(0, 1) * n for mk in m)


def calibrate():
    rng = random.Random(CFG["seed"] + 777)
    cal_s, cal_iv = [], []
    for _ in range(CFG["n_calib"]):
        typ = "nID" if rng.random() < CFG["noisy_id_frac"] else "ID"
        for _t in range(8):
            cal_s.append(sample_s(rng, typ))
        cal_iv.append(CFG["probe"]["base_iv"] + rng.gauss(0, CFG["probe"]["sigma_iv"]))
    sigma = _std(cal_s)
    q_z = quantile([v / sigma for v in cal_s], 1 - CFG["gate"]["cal_alpha"])
    tau_iv = quantile(cal_iv, 1 - CFG["gate"]["cal_alpha"])
    return {"sigma": sigma, "q_z": q_z, "tau_iv": tau_iv}


def _std(xs):
    mu = sum(xs) / len(xs)
    return math.sqrt(sum((x - mu) ** 2 for x in xs) / (len(xs) - 1))


def run_static(ep, policy, cal, gamma=None):
    """policy: vla / zest / civic / civic_probealways."""
    rng = random.Random(ep["seed"] + 991)
    typ = ep["typ"]
    if policy in ("civic", "civic_probealways") and typ == "G" and gamma is not None:
        typ = "Gvd" if ep["u_iv"] > gamma else "Gvi"
    gate_on = policy in ("zest", "civic", "civic_probealways")
    B, p_need = CFG["B_static"], CFG["p_need_static"]
    ga = CFG["gate"]
    pr = CFG["probe"]
    sigma, q_z, tau_iv = cal["sigma"], cal["q_z"], cal["tau_iv"]
    c = CFG["c"][typ if typ in CFG["c"] else "G"]
    g = CFG["g"].get(typ, CFG["g"]["G"])
    prog = 0.0
    cost = 0.0
    mode = "TRUST"
    S = 0.0
    fbsince = 0
    probed = False
    recovered = False
    fb_steps = 0
    t = 0
    while prog < p_need and cost < B:
        if policy == "vla":
            act = "SERVO"
        else:
            if mode == "TRUST":
                want_probe = (policy == "civic_probealways" or
                              (policy == "civic" and (ep["lgcc"] or ep["conf"])))
                if not probed and want_probe and cost + pr["cost"] <= B:
                    act = "PROBE"
                else:
                    act = "SERVO"
            else:
                act = "FB" if fbsince < 2 else "RECHECK"
        if act == "PROBE":
            probed = True
            cost += pr["cost"]
            iv = (pr["vd_iv"] if typ == "Gvd" else pr["base_iv"]) \
                + rng.gauss(0, pr["sigma_iv"])
            unstable = iv > tau_iv
            if unstable and typ == "Gvd":
                if rng.random() < pr["recov"]:
                    typ = "REC"
                    c = CFG["c"]["REC"]
                    g = CFG["g"]["REC"]
                    recovered = True
                    S = 0.0
            elif unstable:
                c = max(0.10, c - pr["false_switch_penalty"])
        elif act == "FB":
            cost += CFG["cost"]["FB"]
            fb_steps += 1
            fbsince += 1
            if rng.random() < g * 0.8:
                prog += 1
        elif act == "RECHECK":
            cost += CFG["cost"]["SERVO"]
            fbsince = 0
            if rng.random() < c * 0.9:
                prog += 1
            if gate_on:
                e = 1 if sample_s(rng, typ) / sigma > q_z else 0
                if e == 0:
                    mode = "TRUST"
                    S = 0.0
        else:  # SERVO
            cost += CFG["cost"]["SERVO"]
            if rng.random() < c * 0.9:
                prog += 1
            if gate_on:
                e = 1 if sample_s(rng, typ) / sigma > q_z else 0
                S = max(0.0, S + e - ga["alpha"] - ga["k"])
                if S > ga["h"]:
                    mode = "FALLBACK"
                    S = 0.0
                    fbsince = 0
        t += 1
    return {"succ": 1 if prog >= p_need else 0, "cost": cost,
            "probed": 1 if probed else 0, "recovered": 1 if recovered else 0,
            "fb_frac": fb_steps / max(t, 1)}


def make_int_episode(i):
    rng = random.Random(CFG["seed"] * 7 + i)
    r = rng.random()
    kind = "hover" if r < CFG["int"]["hover"] else (
        "block" if r < CFG["int"]["hover"] + CFG["int"]["block"] else "push")
    t0 = rng.randint(CFG["int"]["t0_lo"], CFG["int"]["t0_hi"])
    dur = {"hover": rng.randint(3, 6), "block": rng.randint(4, 8),
           "push": rng.randint(3, 6)}[kind]
    tp = t0 + rng.randint(1, max(1, dur - 1)) if kind == "push" else -1
    return {"i": i, "kind": kind, "t0": t0, "dur": dur, "tp": tp,
            "seed": CFG["seed"] * 7 + i}


def run_int(ep, policy, cal):
    """policy: noguard / naive / civic_n / civic_na. 基础类型恒为 ID。

    事件语义：hover/block 期间 SERVO 会碰撞（p_col）且无进度；push 在 t=tp
    把目标移走——没看见（或看见了但无 re-ground 能力）则从此抓旧位置（STALE）；
    civic 看见位移会在人离开后 REGROUND（reground_ok 概率找回目标）。
    """
    rng = random.Random(ep["seed"] + 991)
    ia = CFG["int"]
    af = ia["affect"]
    B, p_need = CFG["B_int"], CFG["p_need_int"]
    ga = CFG["gate"]
    sigma, q_z = cal["sigma"], cal["q_z"]
    c = CFG["c"]["ID"]
    prog = 0.0
    cost = 0.0
    mode = "TRUST"
    S = 0.0
    fbsince = 0
    t = 0
    detected = False
    clear_run = 0
    arousal = 0.0
    pause_left = 0
    paused_yet = False
    push_seen = False
    regrounded = False
    stale = False
    collided = False
    regrounds = 0
    while prog < p_need and cost < B:
        active = ep["t0"] <= t < ep["t0"] + ep["dur"]
        if active:
            det = detected or (rng.random() < ia["det_sens"])
            if det:
                detected = True
                clear_run = 0
        else:
            det = False
            if detected:
                clear_run += 1
        # arousal 每步向「环境搅动指示」回归
        bad = 1.0 if active else 0.0
        arousal = (1 - af["ema"]) * arousal + af["ema"] * bad
        # ---- push 判定 ----
        push_now = (ep["tp"] == t)
        if push_now:
            watching = detected or (pause_left > 0)
            if policy in ("civic_n", "civic_na"):
                p_det = ia["watch_push_detect"] + (af["vigil"] if (policy == "civic_na" and watching) else 0.0)
            else:
                p_det = ia["watch_push_detect"] if watching else ia["unwatch_push_detect"]
            push_seen = rng.random() < p_det
            can_reground = policy in ("civic_n", "civic_na")
            if not push_seen or not can_reground:
                stale = True
                c = CFG["c"]["STALE"]
        # ---- 选动作 ----
        if policy == "noguard":
            act = "SERVO"
        elif policy == "naive":
            if not paused_yet and detected:
                paused_yet = True
                pause_left = ia["naive_pause"]
            if pause_left > 0:
                act = "HOLD"
                pause_left -= 1
            else:
                act = "SERVO"  # 暂停结束后无条件恢复，不看人是否离开
        else:
            need_reground = push_seen and not regrounded
            resume = (clear_run >= ia["zn_dwell"]) if policy == "civic_n" \
                else (clear_run >= 1 and arousal < af["resume_arousal"])
            if detected and active:
                act = "HOLD"
            elif detected and not active and need_reground and cost + ia["reground_cost"] <= B:
                act = "REGROUND"
            elif detected and not active and resume:
                detected = False
                clear_run = 0
                act = "SERVO"
            elif detected and not active:
                act = "HOLD"
            else:
                act = "SERVO"
        # ---- 执行 ----
        if act == "HOLD":
            cost += CFG["cost"]["HOLD"]
        elif act == "REGROUND":
            cost += ia["reground_cost"]
            regrounds += 1
            regrounded = True
            if rng.random() < ia["reground_ok"]:
                c = CFG["c"]["REFOUN"]
            else:
                c = CFG["c"]["STALE"]
        else:  # SERVO
            cost += CFG["cost"]["SERVO"]
            if active:
                p_col = ia["p_col"]
                if policy == "civic_na" and arousal > af["theta"]:
                    p_col *= af["col_scale"]
                if rng.random() < p_col:
                    collided = True
                    break
            else:
                if rng.random() < c * 0.9:
                    prog += 1
                # ZEST 门在 ID 残差下基本惰性，保留以对齐第 15 轮
                e = 1 if sample_s(rng, "ID") / sigma > q_z else 0
                S = max(0.0, S + e - ga["alpha"] - ga["k"])
                if S > ga["h"]:
                    mode = "FALLBACK"
                    S = 0.0
                    fbsince = 0
        t += 1
    return {"succ": 1 if prog >= p_need else 0, "cost": cost,
            "collided": 1 if collided else 0,
            "stale": 1 if stale else 0, "regrounds": regrounds}


def run_transient(ep, policy, cal):
    """前 4 步 OOD-E，之后恢复 ID（第 15 轮瞬态场景的回归检查）。"""
    rng = random.Random(ep["seed"] + 991)
    ga = CFG["gate"]
    sigma, q_z = cal["sigma"], cal["q_z"]
    B, p_need = CFG["B_int"], CFG["p_need_int"]
    prog = 0.0
    cost = 0.0
    mode = "TRUST"
    S = 0.0
    fbsince = 0
    t = 0
    probed = False
    while prog < p_need and cost < B:
        typ = "E" if t < 4 else "ID"
        c = CFG["c"][typ]
        g = CFG["g"][typ]
        if policy == "vla":
            act = "SERVO"
        else:
            if mode == "TRUST":
                if policy == "civic" and not probed and t == 0 and \
                        (ep["lgcc"] or ep["conf"]) and cost + CFG["probe"]["cost"] <= B:
                    act = "PROBE"
                else:
                    act = "SERVO"
            else:
                act = "FB" if fbsince < 2 else "RECHECK"
        if act == "PROBE":
            probed = True
            cost += CFG["probe"]["cost"]
            # 瞬态期探针无效（r_iv 对 OOD-E 无设计信号）；只浪费成本
            c = max(0.10, c - CFG["probe"]["false_switch_penalty"])
        elif act == "FB":
            cost += CFG["cost"]["FB"]
            fbsince += 1
            if rng.random() < g * 0.8:
                prog += 1
        elif act == "RECHECK":
            cost += CFG["cost"]["SERVO"]
            fbsince = 0
            if rng.random() < c * 0.9:
                prog += 1
            e = 1 if sample_s(rng, typ) / sigma > q_z else 0
            if e == 0:
                mode = "TRUST"
                S = 0.0
        else:
            cost += CFG["cost"]["SERVO"]
            if rng.random() < c * 0.9:
                prog += 1
            e = 1 if sample_s(rng, typ) / sigma > q_z else 0
            S = max(0.0, S + e - ga["alpha"] - ga["k"])
            if S > ga["h"]:
                mode = "FALLBACK"
                S = 0.0
                fbsince = 0
        t += 1
    return {"succ": 1 if prog >= p_need else 0, "cost": cost,
            "probed": 1 if probed else 0}


def agg(rows):
    n = len(rows)
    succ = sum(r["succ"] for r in rows) / n
    cost = sum(r["cost"] for r in rows) / n
    se = math.sqrt(max(succ * (1 - succ), 1e-9) / n)
    out = {"n": n, "succ": round(succ, 4), "cost": round(cost, 3),
           "succ_se": round(se, 4), "succ_per_cost": round(succ / max(cost, 1e-9), 4)}
    for k in ("probed", "recovered", "collided", "stale"):
        if k in rows[0]:
            out[k + "_rate"] = round(sum(r[k] for r in rows) / n, 4)
    if "fb_frac" in rows[0]:
        out["fb_frac_mean"] = round(sum(r["fb_frac"] for r in rows) / n, 4)
    return out


def subset(rows, key, val):
    return [r for r in rows if r[key] == val]


def main():
    cal = calibrate()
    res = {"config": CFG, "prereg": PREREG,
           "calibration": {k: round(v, 4) for k, v in cal.items()}}

    # ---------- E1 静态混合 ----------
    eps = [make_static_episode(i) for i in range(CFG["n_static"])]
    base = {}
    for pol in ("vla", "zest"):
        base[pol] = agg([run_static(ep, pol, cal) for ep in eps])
    civic_by_gamma = {}
    for gamma in (0.0, 0.4, 0.7, 1.0):
        civic_by_gamma[str(gamma)] = agg(
            [run_static(ep, "civic", cal, gamma=gamma) for ep in eps])
    res["E1_static"] = {"vla": base["vla"], "zest": base["zest"],
                        "civic_by_gamma": civic_by_gamma}
    # per-type 诊断（γ=0.4）
    diag_types = {}
    for typ in ("ID", "nID", "E", "S", "G"):
        rows = [run_static(ep, "civic", cal, gamma=0.4)
                for ep in eps if ep["typ"] == typ][:3000]
        diag_types[typ] = agg(rows)
    res["E1_static"]["civic_per_type_g04"] = diag_types
    # H5：EV 门控 vs probe-always
    res["E1_static"]["civic_probealways_g04"] = agg(
        [run_static(ep, "civic_probealways", cal, gamma=0.4) for ep in eps])

    # ---------- E2 干扰臂 ----------
    ieps = [make_int_episode(i) for i in range(CFG["n_int"])]
    intres = {}
    for pol in ("noguard", "naive", "civic_n", "civic_na"):
        intres[pol] = agg([run_int(ep, pol, cal) for ep in ieps])
        intres[pol + "_push"] = agg([run_int(ep, pol, cal)
                                     for ep in ieps if ep["kind"] == "push"])
        intres[pol + "_hover"] = agg([run_int(ep, pol, cal)
                                      for ep in ieps if ep["kind"] == "hover"])
        intres[pol + "_block"] = agg([run_int(ep, pol, cal)
                                      for ep in ieps if ep["kind"] == "block"])
    res["E2_interference"] = intres

    # ---------- E3 瞬态回归 ----------
    teps = [make_static_episode(i) for i in range(CFG["n_transient"])]
    res["E3_transient"] = {pol: agg([run_transient(ep, pol, cal) for ep in teps])
                           for pol in ("vla", "zest", "civic")}

    # ---------- E4 诊断：r_iv 的 AUROC 与 σ_iv 扫描 ----------
    pr = CFG["probe"]
    rng = random.Random(CFG["seed"] + 4242)
    pos_vd, pos_vi, pos_s, pos_e, neg = [], [], [], [], []
    n_diag = CFG["n_diag"]
    for k in range(n_diag):
        typ = ("nID" if rng.random() < CFG["noisy_id_frac"] else "ID")
        neg.append(pr["base_iv"] + rng.gauss(0, pr["sigma_iv"]))
        for bucket, dist in ((pos_vd, pr["vd_iv"]), (pos_vi, pr["base_iv"])):
            bucket.append(dist + rng.gauss(0, pr["sigma_iv"]))
        pos_s.append(pr["base_iv"] + rng.gauss(0, pr["sigma_iv"]))
        pos_e.append(pr["base_iv"] + rng.gauss(0, pr["sigma_iv"]))
    diag = {"auroc_vd_vs_ID": round(auroc(pos_vd, neg), 4),
            "auroc_vi_vs_ID": round(auroc(pos_vi, neg), 4),
            "auroc_S_vs_ID": round(auroc(pos_s, neg), 4),
            "auroc_E_vs_ID": round(auroc(pos_e, neg), 4)}
    sweep = {}
    for s_iv in (0.25, 0.5, 1.0):
        rng2 = random.Random(CFG["seed"] + 4242 + int(s_iv * 100))
        p_, n_ = [], []
        for _ in range(n_diag):
            p_.append(pr["vd_iv"] + rng2.gauss(0, s_iv))
            n_.append(pr["base_iv"] + rng2.gauss(0, s_iv))
        sweep[str(s_iv)] = round(auroc(p_, n_), 4)
    res["E4_diag"] = {"auroc": diag, "sigma_iv_sweep_vd": sweep}

    with open(OUT, "w") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)

    # ---------- 控制台摘要 ----------
    print("calib:", res["calibration"])
    print("\nE1 static (pi=%.2f, pE=%.2f, mapok=%.2f):" %
          (CFG["pi"], CFG["pE"], CFG["mapok"]))
    for pol in ("vla", "zest"):
        print(f"  {pol:8s}", base[pol])
    for gam, a in civic_by_gamma.items():
        print(f"  civic γ={gam}", a)
    print("  probealways", res["E1_static"]["civic_probealways_g04"])
    print("\nE2 interference:")
    for pol in ("noguard", "naive", "civic_n", "civic_na"):
        print(f"  {pol:9s}", intres[pol])
    print("\nE2 push subset:")
    for pol in ("noguard", "naive", "civic_n", "civic_na"):
        print(f"  {pol:9s}", intres[pol + "_push"])
    print("\nE3 transient:")
    for pol in ("vla", "zest", "civic"):
        print(f"  {pol:8s}", res["E3_transient"][pol])
    print("\nE4 diag:", diag, "sweep:", sweep)

    # 预注册判定
    z, c04 = base["zest"], civic_by_gamma["0.4"]
    d1 = (c04["succ"] - z["succ"]) * 100
    idc = diag_types["ID"]
    print("\nPREREG checks:")
    print(f"  H1 civic-zest={d1:+.2f}pp (>=+2.0?) ; ID succ {idc['succ']:.4f} vs zest-ID? ; "
          f"probe_rate={c04['probed_rate']:.3f} (<=0.20?)")
    print(f"  H2 auroc vd={diag['auroc_vd_vs_ID']:.3f} (>=0.85?) vi={diag['auroc_vi_vs_ID']:.3f} (in [.45,.60]?)")
    z2, n2, nn2 = intres["zest"] if "zest" in intres else None, intres["civic_n"], intres["noguard"]
    d3 = (n2["succ"] - 0)  # zest 无干扰处理；与 noguard 比较见下
    print(f"  H3 civic_n={n2['succ']:.4f} vs noguard={nn2['succ']:.4f} col {n2['collided_rate']} vs {nn2['collided_rate']}")
    print(f"  H4' civic_na={intres['civic_na']['succ']:.4f} vs civic_n={n2['succ']:.4f} "
          f"spc {intres['civic_na']['succ_per_cost']:.3f} vs {n2['succ_per_cost']:.3f}")
    print(f"  H5 probealways spc={res['E1_static']['civic_probealways_g04']['succ_per_cost']:.3f} "
          f"vs civic spc={c04['succ_per_cost']:.3f}")
    print(f"  H6 push: civic_n={intres['civic_n_push']['succ']:.4f} vs naive={intres['naive_push']['succ']:.4f}")


if __name__ == "__main__":
    main()
