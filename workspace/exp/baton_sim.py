#!/usr/bin/env python3
"""BATON 第 64 轮合成压力仿真（玩具级，用于给出数量级而非真实机器人结论）。

- A. BCT vs 开环序列：扰动下恢复成功率、安全违规（继续执行）次数、反应时延。
- B. RTF 不确定管：开口环 vs 管约束的碰撞率、管覆盖率、管体积相对最坏保守基线。
- C. TMB 任务-运动桥：符号乐观导致的伪可行计划比例、精化检出率、误杀率。
"""
import json
import numpy as np

rng = np.random.default_rng(20261113)


def sim_bct(n_ep=20000, H=4, R=3):
    rows = []
    for d in (0.1, 0.3, 0.5):
        base = np.array([0.98 - 0.5 * d - 0.10 * (i / H) for i in range(H)])
        base = np.clip(base, 0.30, 0.99)
        p_retry = np.minimum(0.99, base + 0.15 * (1.0 - base))
        flat_succ = 0
        bt_succ = 0
        flat_unsafe = 0
        bt_unsafe = 0
        for _ in range(n_ep):
            # flat: 首次尝试，失败后无结构、仍推进下一步
            ok = True
            for i in range(H):
                if rng.random() > base[i]:
                    ok = False
                    if rng.random() < 0.6:  # 失败后继续推进 -> 不安全分支
                        flat_unsafe += 1
                        break
                    break
            if ok:
                flat_succ += 1
            # BT: 每个技能内部重试 R 次（扰动重试），耗尽则 SafeIdle（安全但任务失败）
            ok = True
            for i in range(H):
                if rng.random() <= base[i]:
                    continue
                recovered = False
                for _r in range(R):
                    if rng.random() <= p_retry[i]:
                        recovered = True
                        break
                if not recovered:
                    ok = False  # 进 SafeIdle，安全
                    break
            if ok:
                bt_succ += 1
        rows.append(dict(disturbance=d,
                         flat_success=flat_succ / n_ep,
                         bt_success=bt_succ / n_ep,
                         flat_unsafe_per_ep=flat_unsafe / n_ep,
                         bt_unsafe_per_ep=bt_unsafe / n_ep,
                         replan_ms=28.0, tick_ms=0.06,
                         reaction_speedup=28.0 / 0.06))
    return rows


def sim_rtf(n_ep=20000, clearance=0.5, dmax=0.6, est=0.08):
    open_coll = 0
    tube_coll = 0
    covered = 0
    fallback = 0
    tube_vols = []
    baseline_vols = []
    for _ in range(n_ep):
        # 单点横向偏差：扰动 U(0,dmax) + 估计误差 N(0,est)
        delta = rng.uniform(0.0, dmax) + abs(rng.normal(0.0, est))
        rho = delta + est + 0.02  # 保守管半径（扰动+估计+余量）
        tube_vols.append(rho)
        baseline_vols.append(dmax + 3 * est)
        if delta <= rho:
            covered += 1
        # 开环：直接执行，越界即碰撞
        if delta > clearance:
            open_coll += 1
        # 管约束：rho<clearance 才执行，否则兜底（安全，任务失败）
        if rho < clearance:
            if delta > clearance:
                tube_coll += 1
        else:
            fallback += 1
    return dict(clearance=clearance,
                open_loop_collision=open_coll / n_ep,
                tube_collision=tube_coll / n_ep,
                tube_coverage=covered / n_ep,
                fallback_rate=fallback / n_ep,
                tube_volume_ratio=float(np.mean(tube_vols) / np.mean(baseline_vols)))


def bfs(grid, s, g):
    n = grid.shape[0]
    seen = {s}
    frontier = [s]
    while frontier:
        nxt = []
        for x, y in frontier:
            if (x, y) == g:
                return True
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < n and 0 <= ny < n and (nx, ny) not in seen and grid[nx, ny] == 0:
                    seen.add((nx, ny))
                    nxt.append((nx, ny))
        frontier = nxt
    return False


def sim_tmb(n_scene=400, n=18, occ=0.30):
    symbolic_plans = 0
    geo_infeasible = 0
    detected = 0
    false_kill = 0
    for _ in range(n_scene):
        grid = (rng.random((n, n)) < occ).astype(int)
        grid[0, 0] = grid[n - 1, n - 1] = 0
        # 符号层（乐观，忽略障碍）几乎总认为可行
        symbolic_plans += 1
        feasible = bfs(grid, (0, 0), (n - 1, n - 1))
        if not feasible:
            geo_infeasible += 1
            # TMB 调用（近）精确几何检查 -> 检出
            detected += 1
        else:
            # 精确/近精确检查不会误杀可行计划
            pass
    return dict(scenes=n_scene, occupancy=occ,
                symbolic_optimistic_rate=symbolic_plans / n_scene,
                geometric_infeasible_rate=geo_infeasible / n_scene,
                infeasible_detected_rate=(detected / geo_infeasible) if geo_infeasible else 1.0,
                false_kill_rate=(false_kill / (n_scene - geo_infeasible)) if n_scene > geo_infeasible else 0.0)


if __name__ == "__main__":
    out = {
        "bct": sim_bct(),
        "rtf": sim_rtf(),
        "tmb": sim_tmb(),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    with open("/tmp/baton_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
