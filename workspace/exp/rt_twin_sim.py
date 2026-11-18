#!/usr/bin/env python3
"""第 2 轮机制仿真（合成参数，不是真机证据）。

问题：N 个端口共享一个推理后端时，"chunk 请求相位"是不是一个免费的实时性杠杆？
     官方评测在 N 台真机上随机顺序执行、每端口独立跑完整交互；chunk 边界
     由选手的 action_chunk_size 决定 ⇒ 请求时刻其实部分可控。

模型（全部为显式假设，输出 JSON 中复核）：
  * 每端口每 P=266 ms 请求一个 chunk（s=8 动作 × 33.3 ms）
  * 单请求推理时间 S ~ LogNormal(median=m, sigma=0.40)
  * 动态批处理：batch 大小 b 时服务时间 = S * (1 + k*(b-1))，k=0.15
  * 单后端 FIFO、非抢占；batch 上限 B=N
  * 相位：sync = 所有端口同一时刻请求；desync = 端口 i 偏移 i*P/N；
          jitter = 每端口每轮随机抖动
  * 指标：每端口 p50/p99 延迟、chunk 下溢率（latency > P 即机器人在等动作）

结论形状（见表格）：批处理越"省"（b 越大单请求边际成本越低），相位锁定越有利；
     批处理收益不足时，错峰更稳。实时性不是"更快"，而是"把到达过程整形"。

Run: PYTHONPATH=.pylibs python3 exp/rt_twin_sim.py
"""
import json
import os
import time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "rt_twin_results.json")

P = 266.0          # ms, chunk consumption period (s=8 @ 33.3ms)
S_SIG = 0.40       # lognormal sigma
BATCH_K = 0.15     # batching efficiency (marginal cost per extra item)
HORIZON = 60_000.0 # ms per seed
SEEDS = 24
MEDIANS = (30.0, 60.0, 90.0)
NS = (4, 8, 16, 32)
MODES = ("sync", "desync", "jitter")


def service(rng, b, med):
    s = rng.lognormal(mean=np.log(med), sigma=S_SIG)
    return s * (1.0 + BATCH_K * (b - 1))


def make_arrivals(n, mode, rng):
    ev = []
    for p in range(n):
        if mode == "sync":
            t = 0.0
        elif mode == "desync":
            t = p * P / n
        else:
            t = rng.uniform(0.0, P)
        while t < HORIZON:
            ev.append((t, p))
            t += rng.uniform(0.5 * P, 1.5 * P) if mode == "jitter" else P
    ev.sort()
    return ev


def simulate(n, mode, med, seed):
    rng = np.random.default_rng(seed)
    ev = make_arrivals(n, mode, rng)
    lat = []
    underrun = 0
    free = 0.0
    i, m = 0, len(ev)
    while i < m:
        if ev[i][0] > free:
            free = ev[i][0]
        batch = []
        while i < m and ev[i][0] <= free + 1e-9 and len(batch) < n:
            batch.append(ev[i])
            i += 1
        dur = service(rng, len(batch), med)
        end = free + dur
        for (arr, _p) in batch:
            l = end - arr
            lat.append(l)
            if l > P:
                underrun += 1
        free = end
    a = np.array(lat)
    return {
        "p50": float(np.percentile(a, 50)),
        "p99": float(np.percentile(a, 99)),
        "max": float(a.max()),
        "underrun_rate": underrun / len(a),
    }


def main():
    t0 = time.time()
    rows = []
    for med in MEDIANS:
        for n in NS:
            for mode in MODES:
                rs = [simulate(n, mode, med, 1000 + s) for s in range(SEEDS)]
                rows.append({
                    "median_ms": med, "n": n, "mode": mode,
                    "p50": float(np.mean([r["p50"] for r in rs])),
                    "p99": float(np.mean([r["p99"] for r in rs])),
                    "max": float(np.mean([r["max"] for r in rs])),
                    "underrun_rate": float(np.mean([r["underrun_rate"] for r in rs])),
                })
    res = {
        "assumptions": {
            "P_ms": P, "service_lognormal_sigma": S_SIG,
            "batching_marginal_cost_k": BATCH_K, "max_batch": "N",
            "horizon_ms": HORIZON, "seeds": SEEDS,
            "note": "synthetic mechanism check; NOT robot evidence",
        },
        "rows": rows,
        "runtime_sec": round(time.time() - t0, 2),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("median  n  mode    p50    p99    max   underrun")
    for r in rows:
        print(f"{r['median_ms']:6.0f} {r['n']:3d} {r['mode']:<7} "
              f"{r['p50']:6.1f} {r['p99']:6.1f} {r['max']:6.1f} {r['underrun_rate']:8.3f}")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
