#!/usr/bin/env python3
"""XGM-RAS 代理仿真：任务空间可辨识性 + 跨任务泛化证书 (CTGC)。

对应 R69 引理 16/17：
  - 慢故障与漂移在时间频率上不可分时，仍可由跨任务签名矩阵的 off-span
    分量 (kappa_met) 判别；kappa_met=0 即 R68 的盲区。
  - 真漂移修正应跨任务泛化 (rho_tr 高)；故障吸收只改善拟合任务 (rho_tr 低/负)。
"""
import json
import numpy as np

rng = np.random.default_rng(20261113)


def make_signatures(m_tasks=10, d_c=4, d_f=2, off_span=0.5):
    """J: 漂移签名; K = J A + off_span * U_perp: 故障签名。"""
    J = rng.normal(size=(m_tasks, d_c))
    # 找到 J 列空间的正交补的一组基
    Q, _ = np.linalg.qr(J)
    U_perp = rng.normal(size=(m_tasks, d_f))
    U_perp -= Q @ (Q.T @ U_perp)
    U_perp /= np.linalg.norm(U_perp, axis=0, keepdims=True) + 1e-12
    A = rng.normal(size=(d_c, d_f)) * 0.5
    K = J @ A + off_span * U_perp
    return J, K


def kappa_met(J, K):
    Q, _ = np.linalg.qr(J)
    K_perp = K - Q @ (Q.T @ K)
    return float(np.linalg.svd(K_perp, compute_uv=False)[-1])


def identifiability_auc(off_span, sigma=0.5, trials=3000, delta=None, f=None):
    m = 10
    J, K = make_signatures(m, off_span=off_span)
    if delta is None:
        delta = rng.normal(size=J.shape[1])
        delta /= np.linalg.norm(delta)
    if f is None:
        f = rng.normal(size=K.shape[1])
        f /= np.linalg.norm(f)
    Q, _ = np.linalg.qr(J)
    P_perp = np.eye(m) - Q @ Q.T

    def statistic(r):
        return float(np.linalg.norm(P_perp @ r) ** 2)

    # H0: 只有漂移
    t0 = np.array([
        statistic(J @ delta + rng.normal(scale=sigma, size=m))
        for _ in range(trials)
    ])
    # H1: 漂移 + 慢故障（时间频率完全同带）
    t1 = np.array([
        statistic(J @ delta + K @ f + rng.normal(scale=sigma, size=m))
        for _ in range(trials)
    ])
    thr = np.quantile(t0, 0.95)  # 5% 误报
    return {
        "off_span": off_span,
        "kappa_met": kappa_met(J, K),
        "fpr": float(np.mean(t0 > thr)),
        "detect_rate": float(np.mean(t1 > thr)),
    }


def improvements(y, J, c_old, dc):
    """二次损失下的改善量 I = ||y-Jc||^2 - ||y-J(c+dc)||^2。"""
    before = np.sum((y - J @ c_old) ** 2, axis=-1)
    after = np.sum((y - J @ (c_old + dc)) ** 2, axis=-1)
    return before - after


def ctgc_experiment(off_span=0.5, sigma=0.2, trials=5000, rho_min=0.5,
                    gamma=0.0, seed=777):
    """gamma = 故障在留出任务上的共模耦合系数。

    gamma=0  -> 故障是局部的（只污染拟合任务所用的传感器/任务切片）
    gamma=1  -> 故障是共模的（所有任务看到同一偏移，CTGC 原理上不可分）
    固定 seed 使不同 gamma 共享同一 J/A/噪声，隔离共模耦合的因果效应。
    """
    r = np.random.default_rng(seed)
    m_fit, m_ho, d_c, d_f = 5, 5, 4, 2
    J = r.normal(size=(m_fit + m_ho, d_c))
    J_fit, J_ho = J[:m_fit], J[m_fit:]
    A = r.normal(size=(d_c, d_f))
    K_cm = J @ A
    K_local = np.zeros_like(K_cm)
    K_local[:m_fit] = r.normal(size=(m_fit, d_f))
    K = (1.0 - gamma) * K_local + gamma * K_cm
    c_old = np.zeros(d_c)

    def one_case(is_fault, delta, f, noise):
        y = J @ delta + K @ f + noise
        y_fit, y_ho = y[:m_fit], y[m_fit:]
        dc = np.linalg.lstsq(J_fit, y_fit, rcond=None)[0]
        i_fit = improvements(y_fit, J_fit, c_old, dc)
        i_ho = improvements(y_ho, J_ho, c_old, dc)
        g_fit = float(np.mean(i_fit))
        g_ho = float(np.mean(i_ho))
        rho = g_ho / (abs(g_fit) + 1e-9)
        g_ho_vec = np.mean([J_ho[i].T * (y_ho[i] - J_ho[i] @ c_old)
                            for i in range(m_ho)], axis=0)
        cgc = float(np.dot(dc, g_ho_vec) /
                    (np.linalg.norm(dc) * np.linalg.norm(g_ho_vec) + 1e-12))
        return g_fit, g_ho, rho, cgc

    deltas = r.normal(size=(trials, d_c))
    deltas /= np.linalg.norm(deltas, axis=1, keepdims=True)
    fs = r.normal(size=(trials, d_f))
    fs /= np.linalg.norm(fs, axis=1, keepdims=True)
    noise_d = r.normal(scale=sigma, size=(trials, J.shape[0]))
    noise_f = r.normal(scale=sigma, size=(trials, J.shape[0]))
    drift = np.array([one_case(False, deltas[i], np.zeros(d_f), noise_d[i])
                      for i in range(trials)])
    fault = np.array([one_case(True, np.zeros(d_c), fs[i], noise_f[i])
                      for i in range(trials)])

    def auc(pos, neg):
        allv = np.concatenate([pos, neg])
        order = allv.argsort()
        ranks = np.empty_like(order, dtype=float)
        ranks[order] = np.arange(1, len(allv) + 1)
        return float((ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2)
                     / (len(pos) * len(neg)))

    thr5 = float(np.quantile(drift[:, 2], 0.05))
    acc_fault5 = float(np.mean(fault[:, 2] >= thr5))
    acc_drift = float(np.mean(drift[:, 2] >= rho_min))
    acc_fault = float(np.mean(fault[:, 2] >= rho_min))
    return {
        "gamma": gamma,
        "rho_tr_drift_mean": float(drift[:, 2].mean()),
        "rho_tr_fault_mean": float(fault[:, 2].mean()),
        "rho_tr_auc_fault_vs_drift": auc(drift[:, 2], fault[:, 2]),
        "ctgc_false_reject_drift": 1.0 - acc_drift,
        "ctgc_silent_absorb_fault": acc_fault,
        "conformal_thr_5pct": thr5,
        "conformal_false_reject_drift": 0.05,
        "conformal_silent_absorb_fault": acc_fault5,
        "r68_baseline_silent_absorb_fault": 1.0,
        "cgc_drift_mean": float(drift[:, 3].mean()),
        "cgc_fault_mean": float(fault[:, 3].mean()),
        "cgc_auc_fault_vs_drift": auc(drift[:, 3], fault[:, 3]),
    }


if __name__ == "__main__":
    ident = [identifiability_auc(b, sigma=0.2) for b in (0.0, 0.25, 0.5, 1.0)]
    ctgc = [ctgc_experiment(off_span=1.0, gamma=g) for g in (0.0, 0.3, 0.6, 1.0)]
    out = {"identifiability": ident, "ctgc": ctgc,
           "seed": 20261113, "trials": 5000}
    print(json.dumps(out, indent=2))
    with open("/home/runner/work/xuen/xuen/workspace/exp/xgm_sim_results.json",
              "w") as f:
        json.dump(out, f, indent=2)
