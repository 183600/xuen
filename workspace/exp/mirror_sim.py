"""UniBot-MIRROR 机制校验仿真（非真机）。

三个子实验，只验证"结构/机制"，不声称真机数值：
  A. staleness / delay-compensated inference: 观测时滞 tau 与执行时滞下的插入成功率
  B. twin fidelity: 低成本物理孪生对候选策略的排序，与"真机"排序的一致性 / 选优概率
  C. system-ID: 用 m 条标定探针估计硬件参数，残余误差与插入成功率

运行: python exp/mirror_sim.py  ->  exp/mirror_results.json
"""
import json
import numpy as np

rng = np.random.default_rng(20261117)

# ------------------------------------------------------------------ A
def sim_delay(v=0.15, a=0.5, sigma0=1.0, eps=5.0, n=40000):
    """2D 插入: 真机在决策时刻到执行时刻之间继续运动。

    delta = tau_obs + tau_exec (ms)。
    - raw: 用滞后状态 -> 平均偏置 = v*delta
    - predict: 一阶速度外推，残余 = 0.25*v*delta + 0.5*a*delta^2 + sigma0
    成功率 = P(径向误差 < eps_mm)。
    """
    out = {}
    for delta_ms in [33, 66, 100, 150, 200, 300]:
        d = delta_ms / 1000.0
        bias = v * d * 1000.0                      # mm
        # raw: 纯偏置 + 观测噪声
        rx = rng.normal(bias, sigma0, n)
        ry = rng.normal(0.0, sigma0, n)
        raw = float(np.mean(np.hypot(rx, ry) < eps))
        # predict: 偏差被一阶项吃掉，残余为模型误差
        res = np.sqrt((0.25 * v * d * 1000.0) ** 2 + (0.5 * a * d * d * 1000.0) ** 2 + sigma0 ** 2)
        px = rng.normal(0.0, res, n)
        py = rng.normal(0.0, res, n)
        pred = float(np.mean(np.hypot(px, py) < eps))
        out[str(delta_ms)] = {"raw": round(raw, 4), "predict": round(pred, 4),
                              "bias_mm": round(bias, 2), "resid_mm": round(float(res), 2)}
    return out


# ------------------------------------------------------------------ B
def kendall_tau(x, y):
    n = len(x)
    c = d = 0
    for i in range(n):
        for j in range(i + 1, n):
            a = np.sign(x[i] - x[j])
            b = np.sign(y[i] - y[j])
            if a * b > 0:
                c += 1
            elif a * b < 0:
                d += 1
    return (c - d) / (c + d) if (c + d) else 0.0


def sim_twin(n_pol=16, n_rep=400):
    """候选策略有潜在真值 q；孪生 = q + 系统偏差 + 评估噪声；真机 = q + 评估噪声。

    关键量: 用孪生选出 argmax，它落在"真机 top-3"的概率，及两榜 Kendall tau。
    """
    q = rng.uniform(20.0, 35.0, n_pol)      # 潜在真机成功率(%)
    out = {}
    for sigma_sys in [0.0, 1.0, 2.0, 3.0, 4.0]:   # 孪生系统偏差(pp)
        for n_trial in [1, 4, 16]:                 # 每策略每榜试验次数
            taus, hits = [], []
            for _ in range(n_rep):
                yt = q + rng.normal(0, sigma_sys, n_pol) + rng.normal(0, 4.0 / np.sqrt(n_trial), n_pol)
                yg = q + rng.normal(0, 4.0 / np.sqrt(n_trial), n_pol)
                taus.append(kendall_tau(yt, yg))
                sel = int(np.argmax(yt))
                top3 = set(np.argsort(-yg)[:3])
                hits.append(sel in top3)
            out[f"sys{sigma_sys}_n{n_trial}"] = {
                "kendall_tau": round(float(np.mean(taus)), 4),
                "p_select_in_g1_top3": round(float(np.mean(hits)), 4),
            }
    return out


# ------------------------------------------------------------------ C
def sim_sysid(eps=5.0, sigma_probe=2.0, prior_sd=6.0, lever=1.0, n=40000):
    """m 条探针估计 4 个硬件参数(连杆尺度/两个零位/夹爪间隙)。

    参数后验协方差 ~ sigma_probe^2 (X^T X)^-1 (岭 + 先验 prior)。
    残余末端误差 RMS ~ sqrt(trace(cov)) * lever, 成功率 = P(径向 < eps)。
    """
    out = {}
    k = 4
    for m in [0, 3, 5, 10, 20, 50, 100]:
        # 每个参数的 Fisher 信息累积 ~ m / k; 用对角近似
        # m=0 -> 只有先验 prior_sd; m 增大 -> 方差按 1/m 降
        post_var = 1.0 / (1.0 / prior_sd ** 2 + m / (sigma_probe ** 2 * k))
        resid = np.sqrt(k * post_var) * lever
        rx = rng.normal(0.0, resid, n)
        ry = rng.normal(0.0, resid, n)
        succ = float(np.mean(np.hypot(rx, ry) < eps))
        out[str(m)] = {"resid_mm": round(float(resid), 3),
                       "insert_success": round(succ, 4)}
    return out


if __name__ == "__main__":
    res = {
        "meta": {"seed": 20261117, "note": "mechanism sanity-check only, not real-robot"},
        "A_delay_compensation": sim_delay(),
        "B_twin_fidelity": sim_twin(),
        "C_system_id": sim_sysid(),
    }
    with open("exp/mirror_results.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))
