"""第 16 轮（ECHO-VLA）合成实验：LoRA 秩-捕获权衡 / 共情让位收益 / 难度加权采样

输入：exp/unibot_leaderboard_20261102.json（2026-11-02 官网缓存，webfetch 复核一致）
输出：exp/round16_results.json + 控制台摘要

E1 LoRA rank-capture：任务技能原型聚类 + 低秩子空间捕获，回答「官方默认 r=16 是否够、
   秩增大在 ID 增益与泛化保持之间的权衡」。玩具模型，B 级证据。
E2 Empathetic yield：人为干扰场景下 ignore / pause / yield 三种响应的蒙特卡洛对比，
   回答「让位行为值多少分、dwell 上限与检测延迟的敏感性」。
E3 Difficulty-weighted sampling：固定训练预算下 uniform vs 难度加权 vs 榜首短板加权，
   回答「数据采样策略值多少平均分」。
E4 真数据：步骤分/成功率比值结构（得分点制推断）+ oracle 路由上界。
"""
import json
import math
import os
import random
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "unibot_leaderboard_20261102.json")
OUT = os.path.join(HERE, "round16_results.json")

random.seed(20261102)

with open(SRC, encoding="utf-8") as f:
    data = json.load(f)

tasks = data["tasks"]
models = data["models"]
G = {m["model_name"]: {t["task"]: t["success_rate"] for t in m["task_metrics"]} for m in models}
s0 = {t: st.mean(G[m][t] for m in G) / 100.0 for t in tasks}          # 跨模型均值（基底能力代理）
orc = {t: max(G[m][t] for m in G) / 100.0 for t in tasks}              # 每任务最优（可达性代理）

# 6 个技能原型：32 任务的语义分组（抓放 / 插拔 / 排列 / 收纳 / 变形柔软 / 精细倒注）
PROTO = ["pickplace", "plugunlock", "arrange", "storepack", "deform", "precision"]
CLUSTER = {
    "Hang the Cup": ["pickplace", "arrange"], "Fruit Basket Collection": ["pickplace"],
    "Pack the Doll": ["storepack", "deform"], "Fruit Sorting": ["pickplace", "arrange"],
    "Disconnect Ethernet": ["plugunlock"], "Color Arrangement": ["arrange"],
    "Place Photo Frames": ["pickplace", "arrange"], "Organize Bookshelf": ["arrange", "storepack"],
    "Toolbox Storage": ["storepack"], "Plug Charger": ["plugunlock"],
    "Pick Out Battery": ["precision", "pickplace"], "Unlock": ["plugunlock"],
    "Arrange Test Tubes": ["precision", "arrange"], "Open Pill Bottle": ["plugunlock", "precision"],
    "Organize Tools": ["storepack"], "Fold Towel": ["deform"],
    "Organize Stationery": ["arrange", "precision"], "Pack Bag": ["storepack", "deform"],
    "Zip Up": ["deform", "plugunlock"], "Paper Cup Stacking": ["pickplace", "arrange"],
    "Clear Plates": ["pickplace", "storepack"], "Spell robot": ["arrange", "precision"],
    "Store Racket": ["storepack"], "Conveyor Food Sorting": ["pickplace"],
    "Stack Cups": ["pickplace"], "Plug In Ethernet": ["plugunlock"],
    "Stack Bowls": ["pickplace"], "Store Earphones": ["storepack", "precision"],
    "Pack Phone": ["storepack"], "Remove Pinned Note": ["precision", "deform"],
    "Organize Pencil Case": ["storepack", "arrange"], "Syringe Water Transfer": ["precision"],
}

# ---------------- E1: LoRA rank-capture ----------------
def e1_rank_capture(n_rep=200):
    """任务需求矩阵 U(32x6) 的 top-r 子空间捕获率 -> 成功率增益；大秩在无增广时伤泛化。"""
    res = {"r_grid": list(range(1, 33))}
    curves = {}
    for aug in (0.0, 0.5, 1.0):        # 增广强度 0=只用官方原始数据, 1=位置/背景/物品增广全覆盖
        id_means, gen_means = [], []
        for rep in range(n_rep):
            # 每任务对原型的隶属权重（混合任务存在）
            U = [[0.0] * len(PROTO) for _ in tasks]
            for i, t in enumerate(tasks):
                cl = CLUSTER[t]
                w = [random.expovariate(1.0) if k in cl else 0.02 for k in PROTO]
                s = sum(w)
                for k in range(len(PROTO)):
                    U[i][k] = w[k] / s
            # top-r 左奇异能量（幂迭代，U 是 32x6，直接算 Gram）
            gram = [[sum(U[i][a] * U[j][a] for a in range(len(PROTO))) for j in range(len(tasks))]
                    for i in range(len(tasks))]
            # 幂迭代求前 r 个特征向量的总能量占比
            n = len(tasks)
            A = [row[:] for row in gram]
            captured = 0.0
            total = sum(A[i][i] for i in range(n))
            for _ in range(min(r_needed := len(tasks), 32)):
                if captured >= min(r_cur := 32, 32):
                    break
                break
            # 简化：用特征值近似（对 6 维因子结构，直接在原型空间度量）
            pgram = [[sum(U[i][a] * U[j][a] for i in range(n)) for j in range(len(PROTO))]
                     for a in range(len(PROTO))]
            eig = [1.0]  # placeholder
            break
        break
    # 上面通用框架过繁，改为直接在原型空间计算：需求张量 = 原型系数矩阵 W(32x6)
    # capture_t(r) = ||P_r w_t||^2 / ||w_t||^2，P_r 为 W 的 top-r 右奇异子空间
    out = {"r_grid": list(range(1, 33))}
    for aug in (0.0, 0.5, 1.0):
        id_curve, gen_curve = [], []
        for r in range(1, 33):
            acc_id, acc_gen = [], []
            for rep in range(60):
                W = [[0.0] * len(PROTO) for _ in tasks]
                for i, t in enumerate(tasks):
                    cl = CLUSTER[t]
                    w = [random.expovariate(1.0) if k in cl else 0.02 for k in PROTO]
                    s = sum(w)
                    W[i] = [x / s for x in w]
                # W^T W (6x6) 幂迭代取 top-r 特征
                g = [[sum(W[i][a] * W[i][b] for i in range(len(tasks))) for b in range(len(PROTO))]
                     for a in range(len(PROTO))]
                # 对称幂迭代：逐个提取特征向量
                K = len(PROTO)
                vecs = []
                A = [row[:] for row in g]
                for _ in range(K):
                    v = [random.random() for _ in range(K)]
                    for _ in range(200):
                        nv = [sum(A[a][b] * v[b] for b in range(K)) for a in range(K)]
                        nn = math.sqrt(sum(x * x for x in nv)) or 1.0
                        v = [x / nn for x in nv]
                    vecs.append(v[:])
                    # deflation
                    lam = sum(A[a][b] * v[a] * v[b] for a in range(K) for b in range(K))
                    for a in range(K):
                        for b in range(K):
                            A[a][b] -= lam * v[a] * v[b]
                # P_r w 的捕获率
                caps = []
                for i in range(len(tasks)):
                    w = W[i]
                    num = 0.0
                    for j in range(min(r, K)):
                        v = vecs[j]
                        pr = sum(w[a] * v[a] for a in range(K))
                        num += pr * pr
                    caps.append(min(1.0, num / (sum(x * x for x in w) + 1e-12)))
                # 成功率映射
                ids, gens = [], []
                for i, t in enumerate(tasks):
                    smax = min(0.82, orc[t] * 1.15 + 0.05)
                    data_f = 1.0  # 官方 ~1000 eps/任务，均匀覆盖，data 因子≈1
                    gain = (smax - s0[t]) * caps[i] * data_f
                    s_id = s0[t] + gain
                    # 泛化场景：增益部分按 (1 - kappa*(r/32)*(1-aug)) 折扣
                    keep = 1.0 - 0.6 * (r / 32.0) * (1.0 - aug)
                    s_gen = s0[t] + gain * keep
                    ids.append(s_id)
                    gens.append(s_gen)
                acc_id.append(st.mean(ids))
                acc_gen.append(st.mean(gens))
            id_curve.append(100 * st.mean(acc_id))
            gen_curve.append(100 * st.mean(acc_gen))
        out[f"id_aug{aug}"] = [round(x, 2) for x in id_curve]
        out[f"gen_aug{aug}"] = [round(x, 2) for x in gen_curve]
    return out

# ---------------- E2: empathetic yield ----------------
def e2_yield(n_eps=12000, T_max=600, m_points=8, mu_step=55.0):
    """人为干扰场景：ignore / pause / yield 三响应策略的蒙特卡洛成功率。"""
    def run(policy, lam, det_lat, dwell_max, p_hit, p_knock, c_resume, p_take, rng):
        # 返回 1/0 成功
        steps = 0
        done_points = 0
        prog_left = rng.expovariate(1.0 / mu_step)   # 当前得分点剩余步数（指数）
        human_until = -1
        next_human = rng.expovariate(lam) if lam > 0 else float("inf")
        reground_needed = False
        resuming = 0
        while steps < T_max and done_points < m_points:
            human_here = steps < human_until
            # 干扰事件到达
            if not human_here and steps >= next_human:
                human_until = steps + rng.randint(40, 100)
                next_human = human_until + rng.expovariate(lam)
                if policy == "yield" and steps + 2 < human_until:
                    pass
            if policy == "ignore":
                f = 0.12 if human_here else 1.0
                if human_here and rng.random() < p_hit:
                    return 0
            elif policy == "pause":
                if human_here:
                    f = 0.0
                    if rng.random() < p_knock:
                        return 0
                else:
                    f = 1.0
            else:  # yield
                if human_here:
                    f = 0.0
                else:
                    if resuming > 0:
                        resuming -= 1
                        f = 0.0
                        steps += 1
                        continue
                    f = 1.0
            # 检测延迟：ignore 无检测；pause/yield 在干扰开始后 det_lat 步内仍按 ignore 行事
            eff = f
            if policy in ("pause", "yield") and human_here:
                # 干扰刚开始的 det_lat 步内没有反应
                if human_until - steps > (100 - det_lat):
                    pass
            prog_left -= eff * rng.random() * 1.6
            steps += 1
            if prog_left <= 0:
                done_points += 1
                if done_points < m_points:
                    prog_left = rng.expovariate(1.0 / mu_step)
        return 1 if done_points >= m_points else 0

    # 干扰到达的严格实现：用显式事件调度重写（上面简化逻辑有缺陷，改为逐事件）
    def run2(policy, lam, det_lat, dwell_max, p_hit, p_knock, c_resume, p_take, rng):
        steps = 0
        done = 0
        prog_left = rng.expovariate(1.0 / mu_step)
        human_until = -1
        next_start = rng.expovariate(lam)
        wait_accum = 0            # yield 在当前干扰中已等待步数
        resume_left = 0
        took = False
        while steps < T_max and done < m_points:
            human_here = steps < human_until
            if steps >= next_start and not human_here:
                human_until = steps + rng.randint(40, 100)
                next_start = human_until + rng.expovariate(lam)
                wait_accum = 0
                took = rng.random() < p_take
                resume_left = c_resume
            if policy == "ignore":
                if human_here:
                    if rng.random() < p_hit:
                        return 0
                    eff = 0.12
                else:
                    eff = 1.0
                prog_left -= eff * rng.random() * 1.6
                steps += 1
            elif policy == "pause":
                if human_here:
                    if steps < human_until - (100 - det_lat):
                        # 干扰刚开始（未检出）——继续执行
                        if rng.random() < p_hit:
                            return 0
                        prog_left -= 0.12 * rng.random() * 1.6
                    else:
                        if rng.random() < p_knock:
                            return 0
                else:
                    prog_left -= rng.random() * 1.6
                steps += 1
            else:  # yield
                if human_here:
                    if steps < human_until - (100 - det_lat):
                        if rng.random() < p_hit:
                            return 0
                        prog_left -= 0.12 * rng.random() * 1.6
                        steps += 1
                        continue
                    wait_accum += 1
                    if wait_accum > dwell_max:
                        # 放弃等待，保守继续（低进展 + 碰撞风险）
                        if rng.random() < p_hit:
                            return 0
                        prog_left -= 0.12 * rng.random() * 1.6
                    steps += 1
                    continue
                if resume_left > 0:
                    resume_left -= 1
                    steps += 1
                    if resume_left == c_resume // 2 and took:
                        prog_left = rng.expovariate(1.0 / mu_step)  # 目标被移位，重新 grounding
                    continue
                prog_left -= rng.random() * 1.6
                steps += 1
            if prog_left <= 0:
                done += 1
                if done < m_points:
                    prog_left = rng.expovariate(1.0 / mu_step)
        return 1 if done >= m_points else 0

    out = {}
    cfgs = [
        ("base",   dict(lam=0.01, det_lat=5,  dwell_max=250, p_hit=0.003, p_knock=0.0015, c_resume=20, p_take=0.3)),
        ("busy",   dict(lam=0.03, det_lat=5,  dwell_max=250, p_hit=0.003, p_knock=0.0015, c_resume=20, p_take=0.3)),
        ("crowd",  dict(lam=0.06, det_lat=5,  dwell_max=250, p_hit=0.003, p_knock=0.0015, c_resume=20, p_take=0.3)),
        ("slowdet",dict(lam=0.03, det_lat=15, dwell_max=250, p_hit=0.003, p_knock=0.0015, c_resume=20, p_take=0.3)),
        ("dwell100",dict(lam=0.03, det_lat=5, dwell_max=100, p_hit=0.003, p_knock=0.0015, c_resume=20, p_take=0.3)),
    ]
    rng = random.Random(7)
    for name, kw in cfgs:
        row = {}
        for pol in ("ignore", "pause", "yield"):
            wins = sum(run2(pol, rng=random.Random(hash((name, pol)) & 0xffffffff), **kw) for _ in range(n_eps))
            row[pol] = round(wins / n_eps, 4)
        out[name] = row
    return out

# ---------------- E3: difficulty-weighted sampling ----------------
def e3_sampling(gamma=0.6, budget_gain=10.0, n_rep=400):
    """固定预算的增益总量 A，比较三种采样分配。Δs_t = A_norm * a_t^gamma * (1-s0_t)"""
    reps = {"uniform": [], "difficulty": [], "shortboard": []}
    for rep in range(n_rep):
        # 每次重抽一个「真实可达增益」噪声
        noise = {t: random.gauss(1.0, 0.15) for t in tasks}
        base = {t: max(0.0, 1.0 - s0[t]) for t in tasks}
        sb = {t: max(0.01, orc[t] - s0[t]) for t in tasks}
        schemes = {
            "uniform": {t: 1.0 for t in tasks},
            "difficulty": {t: base[t] ** 1.5 for t in tasks},
            "shortboard": {t: sb[t] ** 1.5 for t in tasks},
        }
        for name, a in schemes.items():
            Z = sum(a.values())
            ds = []
            for t in tasks:
                w = a[t] / Z
                ds.append(budget_gain * (32 * w) ** gamma * base[t] * noise[t])
            reps[name].append(ds)
    out = {}
    for name, lst in reps.items():
        mean_gain = st.mean(sum(d) / len(d) for d in lst)
        # 最差四分位任务的改善（防短板）
        q1_gain = st.mean(sorted(d)[len(d) // 4] for d in lst)  # 单任务视角
        worst_gain = st.mean(min((s0[t] * 100 + d[t] * 100) for t in tasks) for d in lst)
        out[name] = {
            "avg_gain_pp": round(mean_gain * 100, 2),
            "avg_success_pp": round(st.mean(st.mean(s0[t] * 100 + d[t] * 100 for t in tasks) for d in lst), 2),
            "min_task_success_pp": round(worst_gain, 2),
        }
    return out

# ---------------- E4: 真数据结构 ----------------
def e4_structure():
    ratios = {m["model_name"]: round(m["avg_step_score"] / m["avg_success_rate"], 3) for m in models}
    oracle = round(st.mean(max(G[m][t] for m in G) for t in tasks), 2)
    top = models[0]
    gaps = sorted(
        ((max(G[m][t] for m in G) - G[top["model_name"]][t], t) for t in tasks), reverse=True)
    return {"step_over_success": ratios, "oracle_route_avg": oracle,
            "top_gap_tasks": [(t, round(g, 1)) for g, t in gaps[:8]]}

if __name__ == "__main__":
    print("E1 rank-capture ...")
    e1 = e1_rank_capture()
    print("E2 empathetic yield ...")
    e2 = e2_yield(n_eps=6000)
    print("E3 sampling ...")
    e3 = e3_sampling()
    print("E4 structure ...")
    e4 = e4_structure()
    res = {"E1_rank_capture": e1, "E2_yield": e2, "E3_sampling": e3, "E4_structure": e4}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("\n=== E1（ID/泛化均分 vs rank，增广强度 aug）===")
    for aug in (0.0, 0.5, 1.0):
        row = e1[f"id_aug{aug}"]; rowg = e1[f"gen_aug{aug}"]
        pts = [(r, row[r - 1], rowg[r - 1]) for r in (2, 4, 6, 8, 12, 16, 24, 32)]
        print(f" aug={aug}: " + "  ".join(f"r={r}:{i:.1f}/{g:.1f}" for r, i, g in pts))
    print("\n=== E2（成功率，三策略 × 干扰配置）===")
    for k, v in e2.items():
        print(f" {k:>9}: ignore={v['ignore']:.3f}  pause={v['pause']:.3f}  yield={v['yield']:.3f}")
    print("\n=== E3（采样策略）===")
    for k, v in e3.items():
        print(f" {k:>11}: +{v['avg_gain_pp']}pp -> avg {v['avg_success_pp']}%, 最差任务 {v['min_task_success_pp']}%")
    print("\n=== E4 ===")
    print(" step/success:", e4["step_over_success"])
    print(" oracle route:", e4["oracle_route_avg"])
    print(" top gap tasks:", e4["top_gap_tasks"])
