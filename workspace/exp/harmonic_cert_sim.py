#!/usr/bin/env python3
"""DeployCert / HarmonicCert 模拟：谐波减速器传动误差 -> 区间证书 -> 落地阶梯。

纯标准库实现，避免依赖。输出 exp/harmonic_cert_results.json。
所有数字均为合成模型上的模拟，不是实机测量。
"""
import json
import math
import random
import statistics as st

random.seed(20261115)

TAU_NOM = 12.0          # Nm, 额定负载
TAU0 = 6.0              # Nm, 滞回饱和尺度
LEVER = 0.40            # m, 等效力臂（把关节角误差换成末端位置误差）
E_LAB = 1.00e-3         # rad, 实验室认证半径（~0.40 mm @0.4m）
E_DEPLOY = 1.60e-3      # rad, 部署可接受上限
ALPHA = 0.05            # 目标覆盖率 95%


def gauss(mu, sigma):
    return random.gauss(mu, sigma)


class Unit:
    def __init__(self, name):
        self.name = name
        self.a1 = random.uniform(0.01e-3, 0.05e-3)
        self.a2 = random.uniform(0.10e-3, 0.30e-3)
        self.phi1 = random.uniform(0, 2 * math.pi)
        self.phi2 = random.uniform(0, 2 * math.pi)
        self.beta = random.uniform(0.06e-3, 0.26e-3)      # 滞回半宽
        self.k_t = random.uniform(3.0e4, 8.0e4)           # 扭转刚度
        self.rho_max = random.uniform(0.05e-3, 0.55e-3)   # 磨损终值
        self.tau_wear = random.uniform(150.0, 600.0)      # h
        self.sigma = random.uniform(0.01e-3, 0.03e-3)

    def true_error(self, theta, tau, direction, t_h):
        periodic = (self.a1 * math.sin(theta + self.phi1)
                    + self.a2 * math.sin(2 * theta + self.phi2))
        hyst = self.beta * math.tanh(tau / TAU0) * direction
        comp = tau / self.k_t
        wear = self.rho_max * (1.0 - math.exp(-t_h / self.tau_wear))
        return periodic + hyst + comp + wear + gauss(0.0, self.sigma)


FEATS = 6


def features(theta, tau):
    return [1.0, tau, math.sin(theta), math.cos(theta),
            math.sin(2 * theta), math.cos(2 * theta)]


def solve(a, b):
    n = len(a)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        d = m[c][c]
        if abs(d) < 1e-18:
            continue
        for j in range(c, n + 1):
            m[c][j] /= d
        for r in range(n):
            if r != c and m[r][c] != 0.0:
                f = m[r][c]
                for j in range(c, n + 1):
                    m[r][j] -= f * m[c][j]
    return [m[i][n] for i in range(n)]


def fit(samples):
    xtx = [[0.0] * FEATS for _ in range(FEATS)]
    xty = [0.0] * FEATS
    for theta, tau, tau_load, direction, t_h, y in samples:
        f = features(theta, tau)
        for i in range(FEATS):
            xty[i] += f[i] * y
            for j in range(FEATS):
                xtx[i][j] += f[i] * f[j]
    return solve(xtx, xty)


def calibrate(unit, n=3000, t_h=0.0):
    samples, ys, thetas, taus = [], [], [], []
    for _ in range(n):
        theta = random.uniform(0, 2 * math.pi)
        tau = abs(gauss(TAU_NOM, 4.0)) + 1.0
        direction = random.choice((-1.0, 1.0))
        y = unit.true_error(theta, tau, direction, t_h)
        samples.append((theta, tau, tau, direction, t_h, y))
        ys.append(y)
        thetas.append(theta)
        taus.append(tau)
    coef = fit(samples)
    resid = []
    for (theta, tau, _tl, _d, _t, y) in samples:
        f = features(theta, tau)
        resid.append(y - sum(c * v for c, v in zip(coef, f)))
    resid.sort()
    lo = resid[int(math.floor((ALPHA / 2) * n))]
    hi = resid[int(math.ceil((1 - ALPHA / 2) * n)) - 1]
    return coef, lo, hi


def predict(coef, theta, tau):
    f = features(theta, tau)
    return sum(c * v for c, v in zip(coef, f))


def eval_unit(unit, coef, lo, hi, t_h, n=2000):
    covered = 0
    false_safe = 0
    width = []
    bound_max = 0.0
    for _ in range(n):
        theta = random.uniform(0, 2 * math.pi)
        tau = abs(gauss(TAU_NOM, 4.0)) + 1.0
        direction = random.choice((-1.0, 1.0))
        y = unit.true_error(theta, tau, direction, t_h)
        ehat = predict(coef, theta, tau)
        a, b = ehat + lo, ehat + hi
        width.append(b - a)
        bound_max = max(bound_max, abs(a), abs(b))
        if a <= y <= b:
            covered += 1
        if y > b or y < a:
            false_safe += 1
    return {
        "coverage": covered / n,
        "false_safe": false_safe / n,
        "mean_width": st.mean(width),
        "radius": bound_max,
    }


def derating_factor(unit, coef, lo, hi, t_h):
    """最小速度/加速度缩放 s（力矩 ~ s^2），使证书半径回到 E_LAB 以内。"""
    for s in [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2]:
        bound = 0.0
        for _ in range(600):
            theta = random.uniform(0, 2 * math.pi)
            tau = (abs(gauss(TAU_NOM, 4.0)) + 1.0) * (s * s)
            direction = random.choice((-1.0, 1.0))
            ehat = predict(coef, theta, tau)
            bound = max(bound, abs(ehat + lo), abs(ehat + hi))
        if bound <= E_LAB:
            return s
    return 0.2


def true_radius(unit, t_h, n=400):
    m = 0.0
    for _ in range(n):
        theta = random.uniform(0, 2 * math.pi)
        tau = abs(gauss(TAU_NOM, 4.0)) + 1.0
        direction = random.choice((-1.0, 1.0))
        m = max(m, abs(unit.true_error(theta, tau, direction, t_h)))
    return m


def lifetime(unit, horizon=1200, step=10):
    for t in range(0, horizon + 1, step):
        if true_radius(unit, t) > E_LAB:
            return t
    return horizon


def main():
    units = [Unit(f"U{i:02d}") for i in range(40)]
    rows = []

    for u in units:
        coef0, lo0, hi0 = calibrate(u, t_h=0.0)
        r0 = eval_unit(u, coef0, lo0, hi0, 0.0)
        stale = eval_unit(u, coef0, lo0, hi0, 100.0)      # 用出厂标定看 100h
        coef1, lo1, hi1 = calibrate(u, t_h=100.0)         # D1 再标定
        fresh = eval_unit(u, coef1, lo1, hi1, 100.0)
        s = derating_factor(u, coef1, lo1, hi1, 100.0)
        rows.append({
            "unit": u.name,
            "radius_t0_mrad": r0["radius"] * 1e3,
            "true_radius_t0_mrad": true_radius(u, 0.0) * 1e3,
            "coverage_t0": r0["coverage"],
            "false_safe_t0": r0["false_safe"],
            "radius_100h_stale_mrad": stale["radius"] * 1e3,
            "coverage_100h_stale": stale["coverage"],
            "false_safe_100h_stale": stale["false_safe"],
            "radius_100h_recal_mrad": fresh["radius"] * 1e3,
            "true_radius_100h_mrad": true_radius(u, 100.0) * 1e3,
            "coverage_100h_recal": fresh["coverage"],
            "false_safe_100h_recal": fresh["false_safe"],
            "derating_s": s,
            "life_h": lifetime(u),
        })

    def frac(pred):
        return sum(1 for r in rows if pred(r)) / len(rows)

    summary = {
        "n_units": len(rows),
        "target_coverage": 1 - ALPHA,
        "mean_coverage_t0": st.mean(r["coverage_t0"] for r in rows),
        "min_coverage_t0": min(r["coverage_t0"] for r in rows),
        "mean_coverage_100h_stale": st.mean(r["coverage_100h_stale"] for r in rows),
        "mean_false_safe_100h_stale": st.mean(r["false_safe_100h_stale"] for r in rows),
        "mean_coverage_100h_recal": st.mean(r["coverage_100h_recal"] for r in rows),
        "transfer_accept_t0": frac(lambda r: r["radius_t0_mrad"] <= E_LAB * 1e3),
        "transfer_accept_100h_recal": frac(
            lambda r: r["radius_100h_recal_mrad"] <= E_LAB * 1e3),
        "need_derating_100h": frac(lambda r: r["derating_s"] < 1.0),
        "median_derating_s": st.median(r["derating_s"] for r in rows),
        "median_derating_when_needed": st.median(
            [r["derating_s"] for r in rows if r["derating_s"] < 1.0]),
        "median_life_h": st.median(r["life_h"] for r in rows),
        "mean_radius_t0_mrad": st.mean(r["radius_t0_mrad"] for r in rows),
        "mean_true_radius_t0_mrad": st.mean(
            r["true_radius_t0_mrad"] for r in rows),
        "mean_radius_100h_recal_mrad": st.mean(
            r["radius_100h_recal_mrad"] for r in rows),
        "mean_true_radius_100h_mrad": st.mean(
            r["true_radius_100h_mrad"] for r in rows),
        "conservativeness_t0": st.mean(r["radius_t0_mrad"] for r in rows)
            / st.mean(r["true_radius_t0_mrad"] for r in rows),
        "conservativeness_100h": st.mean(r["radius_100h_recal_mrad"] for r in rows)
            / st.mean(r["true_radius_100h_mrad"] for r in rows),
        "max_false_safe_100h_recal": max(r["false_safe_100h_recal"] for r in rows),
        "derating_fail_100h": frac(lambda r: r["derating_s"] <= 0.2
                                    and r["radius_100h_recal_mrad"] > E_LAB * 1e3),
        "E_LAB_mrad": E_LAB * 1e3,
        "cartesian_um_per_mrad_at_0.4m": LEVER * 1e3,
        "cartesian_um_at_E_LAB": E_LAB * LEVER * 1e6,
        "max_false_safe_t0": max(r["false_safe_t0"] for r in rows),
    }
    out = {"summary": summary, "units": rows}
    with open("exp/harmonic_cert_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
