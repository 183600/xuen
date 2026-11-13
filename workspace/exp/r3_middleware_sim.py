#!/usr/bin/env python3
"""Round-3 synthetic mechanism check: multi-port inference middleware.

NOT robot evidence.  Isolates ONE question raised by the UniBot reference
server (policy/web_policy.py): the bundled PolicyService handles one websocket
connection sequentially inside the asyncio event loop, so sharing one model
across N ports requires the participant to build the dispatch layer.  What do
naive vs batched dispatch do to per-request latency and its tail?

Model (all assumptions explicit):
  * N ports, each port issues one get_action every T_a control steps.
  * control rate 30 Hz (same anchor as r16_rubric_latency_sim.py); T_a in
    {8, 15, 30} => per-port period 267 / 500 / 1000 ms.
  * one shared inference backend with service time
        s(B) = s0 + s_extra * (B - 1)      (batched items share some work)
    s0 = 150 ms, s_extra = 40 ms.
  * dispatch policies:
      - independent : N private backends, no queue (memory N x); reference case
      - serial      : one backend, FIFO, no batching (B=1)
      - batch(w)    : one backend; when idle, wait up to w ms to collect queued
                      requests, then serve them as one batch
  * latency = queue wait + service time.  deadline miss = latency > 500 ms.
  * port phases: "staggered" (evenly spread over one period) and "aligned"
    (all ports request together), because the evaluator's cross-robot phase is
    unknown and is exactly what decides whether batching can help.

This is a queueing sanity check, not a benchmark of any real model.
Run: python exp/r3_middleware_sim.py
"""
import json
import os
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
CTRL_HZ = 30.0
DURATION_MS = 600_000.0
N_PORT = 3
S0_MS = 150.0
S_EXTRA_MS = 40.0
DEADLINE_MS = 500.0
JITTER_MS = 2.0


def service_ms(batch):
    return S0_MS + S_EXTRA_MS * max(0, batch - 1)


def arrivals(ta, phase, seed_shift=0.0):
    period = 1000.0 * ta / CTRL_HZ
    out = []
    for p in range(N_PORT):
        if phase == "staggered":
            t = (p + 0.5) * period / N_PORT
        else:
            t = 0.0
        t += phase_offset(seed_shift, p)
        while t < DURATION_MS:
            out.append(t)
            t += period
    return sorted(out)


def phase_offset(x, p):
    # deterministic pseudo-jitter in [-2, 2] ms
    v = ((p + 1) * 2654435761 + int(x * 97)) % 1000 / 1000.0
    return (v * 2 - 1) * JITTER_MS


def summarize(lat, backend_calls):
    lat = sorted(lat)
    n = len(lat)
    if not n:
        return {}
    def q(p):
        return lat[min(n - 1, int(p * (n - 1)))]
    return {
        "n_requests": n,
        "mean_ms": round(sum(lat) / n, 1),
        "p50_ms": round(q(0.50), 1),
        "p95_ms": round(q(0.95), 1),
        "p99_ms": round(q(0.99), 1),
        "max_ms": round(lat[-1], 1),
        "deadline_miss_pct": round(100.0 * sum(x > DEADLINE_MS for x in lat) / n, 2),
        "backend_calls": backend_calls,
    }


def sim_independent(arr):
    lat = [service_ms(1) for _ in arr]
    return summarize(lat, len(arr))


def sim_serial(arr):
    free = 0.0
    lat = []
    calls = 0
    for a in arr:
        start = max(a, free)
        free = start + service_ms(1)
        lat.append(free - a)
        calls += 1
    return summarize(lat, calls)


def sim_batch(arr, window_ms):
    n = len(arr)
    i = 0
    free = 0.0
    lat = []
    calls = 0
    while i < n:
        a = arr[i]
        start = max(a, free)
        # collect requests that can be served by this batch without waiting
        # beyond the batch window after the batch starts
        j = i
        while j < n and arr[j] <= start + window_ms:
            j += 1
        batch = j - i
        finish = start + service_ms(batch)
        for k in range(i, j):
            lat.append(finish - arr[k])
        free = finish
        calls += 1
        i = j
    return summarize(lat, calls)


def util(ta, batch=1):
    period = 1000.0 * ta / CTRL_HZ
    return round(N_PORT * service_ms(batch) / (batch * period), 3)


def main():
    out = {"note": "B-level synthetic middleware queueing check; not robot evidence",
           "assumptions": {"N_PORT": N_PORT, "CTRL_HZ": CTRL_HZ,
                           "s0_ms": S0_MS, "s_extra_ms": S_EXTRA_MS,
                           "deadline_ms": DEADLINE_MS, "duration_s": DURATION_MS / 1000,
                           "phase_jitter_ms": JITTER_MS},
           "utilization_serial": {}, "runs": {}}
    for ta in (8, 15, 30):
        out["utilization_serial"][f"Ta{ta}"] = util(ta)
        for phase in ("staggered", "aligned"):
            arr = arrivals(ta, phase)
            key = f"Ta{ta}_{phase}"
            row = {"independent": sim_independent(arr),
                   "serial": sim_serial(arr)}
            for w in (0.0, 10.0, 30.0, 60.0, 120.0, 240.0):
                row[f"batch_{int(w)}ms"] = sim_batch(arr, w)
            out["runs"][key] = row
    with open(os.path.join(HERE, "r3_middleware_sim.json"), "w") as fh:
        json.dump(out, fh, indent=1)

    print("serial utilization (arrival rate * s0):",
          out["utilization_serial"])
    for key, row in out["runs"].items():
        print(f"== {key} ==")
        print(f"{'policy':16s} {'mean':>7s} {'p50':>7s} {'p95':>7s} {'p99':>7s} {'miss%':>6s} {'calls':>6s}")
        for k, v in row.items():
            print(f"{k:16s} {v['mean_ms']:7.1f} {v['p50_ms']:7.1f} {v['p95_ms']:7.1f} "
                  f"{v['p99_ms']:7.1f} {v['deadline_miss_pct']:6.2f} {v['backend_calls']:6d}")


if __name__ == "__main__":
    main()
