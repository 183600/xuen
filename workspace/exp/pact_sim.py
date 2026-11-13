"""第 16 轮 · PACT-VLA 合成实验（B 级证据）

三个词：预训练 / 并发推理 / 力矩控制。

E0  真数据：排行榜结构（32 任务 × 8 模型）
    - 哪些任务对所有模型都难（共同瓶颈）
    - 任务难度跨模型相关性（是否存在共同难度因子）
    - oracle 路由上界（互补专长能兑现多少）
    - 步骤分/成功率结构
E1  并发推理：N 端口共享单模型的排队-僵化实验
    - 每端口独立副本 / 共享串行 / 共享连续批处理 / 投机分块（世界模型）
    - 指标：p50/p99 延迟、平均动作僵化(age)、成功率、GPU 成本
    - 结论：连续批处理让「短块」可行，短块降低僵化；投机分块把重推成本压回
E2  力矩控制：位置接口下的虚拟阻抗（接触刚度匹配）
    - 固定刚度 / oracle 刚度 / 带噪接触估计（收缩估计，质量 rho）
    - 指标：成功率、过刚违反率、欠力停滞率，随 OOD 刚度分布变化
E3  预训练：接触先验随预训练数据量的提升，如何传导到 E2
    - rho(H) 饱和曲线，映射到 E2 成功率
    - 对应官方 WLA-1.0 基座 2500h/64 任务 vs 挑战集 169h/32 任务

所有数值均为显式建模的玩具量，不是真机证据。固定种子，可复现。
"""
import json
import math
import os
import random
import heapq
import statistics as st
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
LB = os.path.join(HERE, "unibot_leaderboard_20261102.json")
OUT = os.path.join(HERE, "pact_results.json")

random.seed(20261102)

# ============================================================
# E0  真数据：排行榜结构
# ============================================================
def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    sy = math.sqrt(sum((b - my) ** 2 for b in ys))
    if sx == 0 or sy == 0:
        return float("nan")
    return sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / (sx * sy)


def e0_leaderboard():
    d = json.load(open(LB, encoding="utf-8"))
    tasks = d["tasks"]
    models = d["models"]
    names = [m["model_name"] for m in models]
    S = {m["model_name"]: {t["task"]: t["success_rate"] for t in m["task_metrics"]} for m in models}
    D = {m["model_name"]: {t["task"]: t["avg_duration_sec"] for t in m["task_metrics"]} for m in models}
    K = {m["model_name"]: {t["task"]: t["step_score"] for t in m["task_metrics"]} for m in models}

    per_task = []
    for t in tasks:
        vals = [S[m][t] for m in names]
        durs = [D[m][t] for m in names]
        per_task.append({
            "task": t,
            "mean_succ": round(st.mean(vals), 2),
            "max_succ": round(max(vals), 2),
            "std_succ": round(st.pstdev(vals), 2),
            "mean_dur": round(st.mean(durs), 1),
            "best_model": names[max(range(len(vals)), key=lambda i: vals[i])],
        })
    per_task.sort(key=lambda r: r["mean_succ"])

    # 共同难度因子：任务难度向量（8 个模型的成功率）之间的平均相关
    vecs = [[S[m][t] for m in names] for t in tasks]
    cors = []
    for i in range(len(tasks)):
        for j in range(i + 1, len(tasks)):
            c = pearson(vecs[i], vecs[j])
            if not math.isnan(c):
                cors.append(c)
    mean_inter_task_corr = st.mean(cors)

    # oracle 路由上界：每个任务取最好模型
    oracle = st.mean(max(S[m][t] for m in names) for t in tasks)
    best_single = max(st.mean(S[m][t] for t in tasks) for m in names)

    # 步骤分/成功率
    ratio = st.mean(m["avg_step_score"] / m["avg_success_rate"] for m in models)

    # 接触/精细/形变任务分组（人工归类的硬瓶颈代理）
    CONTACT = ["Plug In Ethernet", "Disconnect Ethernet", "Unlock", "Open Pill Bottle",
               "Plug Charger", "Hang the Cup", "Syringe Water Transfer"]
    group_contact = st.mean(S[m][t] for m in names for t in CONTACT)
    group_all = st.mean(S[m][t] for m in names for t in tasks)

    return {
        "n_tasks": len(tasks), "n_models": len(models),
        "leader": {"model": names[0], "succ": models[0]["avg_success_rate"],
                   "step": models[0]["avg_step_score"]},
        "per_task_sorted": per_task,
        "hardest5": per_task[:5],
        "easiest5": per_task[-5:],
        "mean_inter_task_corr_of_model_profiles": round(mean_inter_task_corr, 3),
        "oracle_routing_ceiling": round(oracle, 2),
        "best_single_model": {"model": names[max(range(len(names)), key=lambda i: st.mean(S[names[i]][t] for t in tasks))],
                              "succ": round(best_single, 2)},
        "routing_headroom_pp": round(oracle - best_single, 2),
        "step_over_success_ratio": round(ratio, 3),
        "contact_group_mean_succ": round(group_contact, 2),
        "all_group_mean_succ": round(group_all, 2),
        "contact_tasks": CONTACT,
    }


# ============================================================
# E1  并发推理：N 端口共享单模型
# ============================================================
def run_batch_server(requests, t_heavy, t_wm, batch):
    """离散事件批处理服务器：最多 batch 个请求同批，批服务时间=批内最大服务时间。

    requests: list of (arrival_s, port, kind)  kind in {'H','W'}
    返回 (served, total_service_seconds)
      served: list of (arrival, start, end, port, kind, batch_id)
      total_service_seconds: 每批服务时间之和（GPU 秒；同批共享一次前向）
    """
    reqs = sorted(requests, key=lambda r: r[0])
    heap = [(r[0], i, r[1], r[2]) for i, r in enumerate(reqs)]
    heapq.heapify(heap)
    pending = deque()
    free = 0.0
    served = []
    total_svc = 0.0
    bid = 0
    while heap or pending:
        if not pending and heap:
            free = max(free, heap[0][0])
        while heap and heap[0][0] <= free + 1e-12:
            arr, idx, port, kind = heapq.heappop(heap)
            pending.append((arr, port, kind))
        if not pending:
            continue
        b = [pending.popleft() for _ in range(min(batch, len(pending)))]
        svc = max(t_heavy if k == 'H' else t_wm for _, _, k in b)
        for arr, port, kind in b:
            served.append((arr, free, free + svc, port, kind, bid))
        free += svc
        total_svc += svc
        bid += 1
    return served, total_svc


E1_DT = 0.033          # 30 fps
E1_T_HEAVY = 0.055     # 6B 单次前向 55ms（示意）
E1_T_WM = 0.008        # 世界模型头 8ms
E1_S0 = 0.30           # 无僵化时每 episode 成功率上限
E1_SCALE = 250.0       # 僵化时间常数 (ms)
E1_W0, E1_DRIFT = 0.95, 0.06


def sim_policy(N, chunk_steps, spec_every, batch, horizon=120.0,
               dt=E1_DT, t_heavy=E1_T_HEAVY, t_wm=E1_T_WM,
               s0=E1_S0, scale=E1_SCALE, w0=E1_W0, drift=E1_DRIFT):
    """单一策略模拟：返回延迟/僵化/成功率/GPU 成本。

    GPU 成本按「批」计：同一批共享一次前向，因此连续批处理降低每端口成本。
    """
    P = chunk_steps * dt
    reqs = []
    for p in range(N):
        k, t = 0, 0.0
        while t < horizon:
            reqs.append((t, p, 'W' if (spec_every > 1 and k % spec_every != 0) else 'H'))
            k += 1
            t += P
    served, total_svc = run_batch_server(reqs, t_heavy, t_wm, batch)
    byp = {p: [] for p in range(N)}
    for arr, start, end, p, kind, bid in served:
        byp[p].append((arr, end, kind))
    ages, quals, lat = [], [], []
    for p in range(N):
        since = 0
        for arr, end, kind in sorted(byp[p]):
            latency = end - arr
            lat.append(latency * 1000)
            ages.append(latency + P / 2)
            if kind == 'H':
                since = 0
                quals.append(1.0)
            else:
                since += 1
                quals.append(w0 * math.exp(-drift * (since - 1)))
    age_ms = st.mean(ages) * 1000
    succ = s0 * st.mean(quals) * math.exp(-0.5 * (age_ms / scale) ** 2)
    cost = total_svc / horizon / N          # GPU 秒 / 端口秒
    return {
        "chunk_steps": chunk_steps, "spec_every": spec_every, "batch": batch,
        "p50_latency_ms": round(st.median(lat), 1),
        "p99_latency_ms": round(sorted(lat)[int(0.99 * len(lat)) - 1], 1),
        "mean_age_ms": round(age_ms, 1),
        "wm_quality": round(st.mean(quals), 3),
        "success": round(succ, 4),
        "gpu_cost": round(cost, 4),
        "success_per_cost": round(succ / max(cost, 1e-9), 2),
    }


def e1_concurrency(n_ports=5, horizon=120.0):
    def copies(N, chunk_steps=8):
        dt = E1_DT
        P = chunk_steps * dt
        served_all, svc_all = [], 0.0
        for p in range(N):
            reqs = []
            t = 0.0
            while t < horizon:
                reqs.append((t, p, 'H'))
                t += P
            s, svc = run_batch_server(reqs, E1_T_HEAVY, E1_T_WM, 1)
            served_all += s
            svc_all += svc
        lat = [(e - a) * 1000 for a, s, e, p, k, b in served_all]
        age = st.mean([(e - a) + P / 2 for a, s, e, p, k, b in served_all]) * 1000
        succ = E1_S0 * math.exp(-0.5 * (age / E1_SCALE) ** 2)
        cost = svc_all / horizon / N
        return {"chunk_steps": chunk_steps, "spec_every": 1, "batch": 1,
                "p50_latency_ms": round(st.median(lat), 1),
                "p99_latency_ms": round(sorted(lat)[int(0.99 * len(lat)) - 1], 1),
                "mean_age_ms": round(age, 1), "wm_quality": 1.0,
                "success": round(succ, 4), "gpu_cost": round(cost, 4),
                "success_per_cost": round(succ / max(cost, 1e-9), 2)}

    policies = {
        "A_per_port_copies_c8": copies(n_ports, 8),
        "B_shared_serial_c8":   sim_policy(n_ports, 8, 1, 1, horizon),
        "C_shared_batch4_c8":   sim_policy(n_ports, 8, 1, 4, horizon),
        "D_shared_batch4_c4":   sim_policy(n_ports, 4, 1, 4, horizon),
        "E_spec_batch4_c4_R4":  sim_policy(n_ports, 4, 4, 4, horizon),
        "F_spec_batch4_c8_R3":  sim_policy(n_ports, 8, 3, 4, horizon),
        "G_spec_batch4_c2_R3":  sim_policy(n_ports, 2, 3, 4, horizon),
    }
    ref = policies["A_per_port_copies_c8"]["gpu_cost"]
    for v in policies.values():
        v["gpu_cost_rel"] = round(v["gpu_cost"] / ref, 3)

    scaling = {}
    for N in [3, 5, 8, 12]:
        scaling[N] = {
            "serial_c8":          sim_policy(N, 8, 1, 1, horizon),
            "copies_c8":          copies(N, 8),
            "batch4_c8":          sim_policy(N, 8, 1, 4, horizon),
            "spec_batch4_c4_R4":  sim_policy(N, 4, 4, 4, horizon),
        }

    return {"dt": E1_DT, "t_heavy_ms": E1_T_HEAVY * 1000, "t_wm_ms": E1_T_WM * 1000,
            "n_ports": n_ports, "policies": policies, "scaling": scaling}


# ============================================================
# E2  力矩控制：位置接口下的虚拟阻抗（接触刚度匹配）
# ============================================================
def e2_torque(n=200000, sigma_oob=0.7, tau=0.7, tau_hi=1.1, sigma_est=0.35):
    """log 刚度 logk ~ N(0, sigma_oob^2)。
    控制器估计 logk_hat = rho*logk + noise；命令 logk_cmd = logk_hat。
    误差 e = logk_cmd - logk = (rho-1) logk + noise。
    成功 = |e|<=tau；过刚 = e>tau_hi；停滞 = e<-tau。
    """
    def evaluate(rho):
        succ = viol = stall = 0
        for _ in range(n):
            lk = random.gauss(0.0, sigma_oob)
            noise = random.gauss(0.0, sigma_est * math.sqrt(max(1e-9, 1 - rho * rho)))
            e = (rho - 1.0) * lk + noise
            if e > tau_hi:
                viol += 1
            elif e < -tau:
                stall += 1
            elif abs(e) <= tau:
                succ += 1
        return succ / n, viol / n, stall / n

    rows = {}
    for rho in [0.0, 0.25, 0.5, 0.75, 0.9, 1.0]:
        s, v, stl = evaluate(rho)
        rows[rho] = {"success": round(s, 4), "overstiff_violation": round(v, 4),
                     "stall": round(stl, 4)}
    # 刚度不匹配扫描（固定刚度，rho=0）：成功率 vs OOD 分布宽度
    sweep = {}
    for sig in [0.2, 0.4, 0.7, 1.0, 1.3]:
        s0_, v0, st0 = e2_eval_fixed(sig, tau, tau_hi, sigma_est)
        s1_, v1, st1 = e2_eval_fixed(sig, tau, tau_hi, sigma_est, rho=1.0)
        sweep[sig] = {"fixed_success": round(s0_, 4), "oracle_success": round(s1_, 4),
                      "fixed_violation": round(v0, 4), "oracle_violation": round(v1, 4)}
    return {"sigma_oob": sigma_oob, "tau": tau, "tau_hi": tau_hi,
            "sigma_est": sigma_est, "by_rho": rows, "ood_width_sweep": sweep}


def e2_eval_fixed(sigma_oob, tau, tau_hi, sigma_est, rho=0.0, n=80000):
    succ = viol = stall = 0
    for _ in range(n):
        lk = random.gauss(0.0, sigma_oob)
        noise = random.gauss(0.0, sigma_est * math.sqrt(max(1e-9, 1 - rho * rho)))
        e = (rho - 1.0) * lk + noise
        if e > tau_hi:
            viol += 1
        elif e < -tau:
            stall += 1
        elif abs(e) <= tau:
            succ += 1
    return succ / n, viol / n, stall / n


# ============================================================
# E3  预训练：接触先验随数据量提升 -> 传导到 E2
# ============================================================
def e3_pretraining(rho_curve):
    """rho(H) = rho_max - (rho_max-rho0) exp(-H/H0)
    接触任务成功率直接由 E2 实测的 rho->success 曲线线性插值（不另设近似）。"""
    rho0, rho_max, H0 = 0.20, 0.92, 900.0
    curve = {float(k): v["success"] for k, v in rho_curve.items()}
    ks = sorted(curve)

    def interp(rho):
        if rho <= ks[0]:
            return curve[ks[0]]
        for i in range(len(ks) - 1):
            if ks[i] <= rho <= ks[i + 1]:
                w = (rho - ks[i]) / (ks[i + 1] - ks[i])
                return curve[ks[i]] * (1 - w) + curve[ks[i + 1]] * w
        return curve[ks[-1]]

    rows = {}
    for H in [0, 169, 500, 1000, 1500, 2500, 4000]:
        rho = rho_max - (rho_max - rho0) * math.exp(-H / H0)
        rows[H] = {"rho": round(rho, 3), "contact_task_success": round(interp(rho), 4)}
    base, full = rows[169]["contact_task_success"], rows[2500]["contact_task_success"]
    return {"rho0": rho0, "rho_max": rho_max, "H0_hours": H0,
            "by_pretrain_hours": rows,
            "gain_169h_to_2500h_pp": round((full - base) * 100, 1),
            "note": "169h=挑战集单独; 2500h=官方WLA-1.0基座量级; 含 G1_Dex1/WBT/R1 同类数据"}


def main():
    e2 = e2_torque()
    out = {"round": 16, "name": "PACT-VLA", "date": "2026-11-02",
           "E0_leaderboard": e0_leaderboard(),
           "E1_concurrency": e1_concurrency(),
           "E2_torque": e2,
           "E3_pretraining": e3_pretraining(e2["by_rho"])}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    e0 = out["E0_leaderboard"]
    print("=== E0 leaderboard ===")
    print("leader", e0["leader"], "oracle ceiling", e0["oracle_routing_ceiling"],
          "headroom", e0["routing_headroom_pp"], "pp")
    print("inter-task corr of model profiles:", e0["mean_inter_task_corr_of_model_profiles"])
    print("contact group", e0["contact_group_mean_succ"], "vs all", e0["all_group_mean_succ"])
    print("hardest5:", [(r["task"], r["mean_succ"]) for r in e0["hardest5"]])

    print("\n=== E1 concurrency (N=5) ===")
    for k, v in out["E1_concurrency"]["policies"].items():
        print(f"  {k:28s} p50={v['p50_latency_ms']:6.1f} p99={v['p99_latency_ms']:7.1f} "
              f"age={v['mean_age_ms']:6.1f} succ={v['success']:.3f} cost={v['gpu_cost']:.3f} "
              f"succ/cost={v['success_per_cost']}")
    print("  scaling:")
    for N, row in out["E1_concurrency"]["scaling"].items():
        print(f"    N={N:2d} serial={row['serial_c8']['success']:.3f} "
              f"batch4={row['batch4_c8']['success']:.3f} "
              f"spec={row['spec_batch4_c4_R4']['success']:.3f}")

    print("\n=== E2 torque ===")
    for rho, v in out["E2_torque"]["by_rho"].items():
        print(f"  rho={rho:.2f} succ={v['success']:.3f} overstiff={v['overstiff_violation']:.3f} stall={v['stall']:.3f}")
    print("  OOD width sweep (fixed vs oracle):")
    for sig, v in out["E2_torque"]["ood_width_sweep"].items():
        print(f"    sigma={sig:.1f} fixed={v['fixed_success']:.3f} oracle={v['oracle_success']:.3f}")

    print("\n=== E3 pretraining ===")
    for H, v in out["E3_pretraining"]["by_pretrain_hours"].items():
        print(f"  H={H:5d}h rho={v['rho']:.3f} contact_success={v['contact_task_success']:.3f}")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
