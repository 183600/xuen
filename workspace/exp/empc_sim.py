"""Synthetic mechanism check for EMPC (round: 应用落地 x 运动规划).

NOT benchmark evidence. It isolates one deployment question:

    When a remote VLA returns an *open-loop action chunk* that is sometimes
    semantically wrong and sometimes kinematically infeasible, does a cheap
    deadline-bounded motion-repair shield buy more success / step score than
    an expensive semantic verifier alone, and at what latency cost?

Declared generative model (not fit to real data):
  - planar 2-link arm, joint-space chunks, no feedback inside a chunk;
  - VLA belief may be shifted by a semantic/perception error (wrong object);
  - chunks also contain action noise, occasional jerks, obstacle collisions
    and joint-limit violations;
  - VLM verifier detects the semantic shift with TPR/FPR, costs 120 ms;
  - EMPC repairs geometry by anytime coordinate descent under a deadline;
  - a repaired chunk that is still infeasible falls back to a safe hold.

All numbers are proxy numbers. The point is the ordering and the
latency / repair-quality trade-off, not the absolute success rate.
"""
import json
import math
import random
import statistics

L1 = L2 = 0.45
QMIN, QMAX = -2.9, 2.9
OBST_R = 0.085
ARM_R = 0.025
TOL = 0.055
H = 6                    # waypoints per returned chunk
MAX_CHUNKS = 10
BASE_MS = 15.0           # policy forward + serialization
VLM_MS = 120.0
REPAIR_C0 = 8.0
REPAIR_C_ITER = 1.2
DEADLINE_MS = 60.0


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def fk(q):
    x = L1 * math.cos(q[0]) + L2 * math.cos(q[0] + q[1])
    y = L1 * math.sin(q[0]) + L2 * math.sin(q[0] + q[1])
    return x, y


def link_points(q, n=3):
    pts = []
    for i in range(n + 1):
        s = i / n
        x1 = L1 * math.cos(q[0]) * s
        y1 = L1 * math.sin(q[0]) * s
        x2 = L1 * math.cos(q[0]) + L2 * math.cos(q[0] + q[1]) * s
        y2 = L1 * math.sin(q[0]) + L2 * math.sin(q[0] + q[1]) * s
        pts.append((x1, y1))
        pts.append((x2, y2))
    return pts


def ik(x, y, seed):
    r = math.hypot(x, y)
    r = min(max(r, 1e-4), L1 + L2 - 1e-4)
    c2 = (r * r - L1 * L1 - L2 * L2) / (2 * L1 * L2)
    c2 = max(-1.0, min(1.0, c2))
    s2 = math.sqrt(max(0.0, 1.0 - c2 * c2))
    cands = []
    for sign in (1.0, -1.0):
        q2 = math.atan2(sign * s2, c2)
        q1 = math.atan2(y, x) - math.atan2(L2 * math.sin(q2),
                                            L1 + L2 * math.cos(q2))
        for k in (-1, 0, 1):
            cands.append([wrap(q1 + 2 * math.pi * k), wrap(q2 + 2 * math.pi * k)])
    return min(cands, key=lambda q: (q[0] - seed[0]) ** 2 + (q[1] - seed[1]) ** 2)


def collides_waypoint(q, obs):
    ox, oy, orad = obs
    for x, y in link_points(q):
        if math.hypot(x - ox, y - oy) < orad + ARM_R:
            return True
    return False


def collides_segment(qa, qb, obs, n=1):
    for i in range(n + 1):
        s = i / n
        q = [qa[0] + (qb[0] - qa[0]) * s, qa[1] + (qb[1] - qa[1]) * s]
        if collides_waypoint(q, obs):
            return True
    return False


def limit_violation(q):
    return max(0.0, QMIN - q[0]) + max(0.0, q[0] - QMAX) + \
        max(0.0, QMIN - q[1]) + max(0.0, q[1] - QMAX)


def deviation(chunk, ref):
    return sum((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
               for a, b in zip(chunk, ref))


def smoothness(chunk):
    s = 0.0
    for i in range(len(chunk) - 1):
        s += (chunk[i + 1][0] - chunk[i][0]) ** 2 + \
             (chunk[i + 1][1] - chunk[i][1]) ** 2
    for i in range(1, len(chunk) - 1):
        s += 2.0 * ((chunk[i + 1][0] - 2 * chunk[i][0] + chunk[i - 1][0]) ** 2 +
                    (chunk[i + 1][1] - 2 * chunk[i][1] + chunk[i - 1][1]) ** 2)
    return s


def chunk_penalty(chunk, ref, obs, lam_dev=0.35, lam_smooth=0.8):
    p = lam_dev * deviation(chunk, ref) + lam_smooth * smoothness(chunk)
    for i, q in enumerate(chunk):
        p += 200.0 * limit_violation(q)
        if collides_waypoint(q, obs):
            p += 300.0
        if i + 1 < len(chunk) and collides_segment(q, chunk[i + 1], obs):
            p += 300.0
    return p


def feasible(chunk, obs):
    for i, q in enumerate(chunk):
        if limit_violation(q) > 1e-9 or collides_waypoint(q, obs):
            return False
        if i + 1 < len(chunk) and collides_segment(q, chunk[i + 1], obs):
            return False
    return True


def repair(chunk, obs, iters, rng, sigma=0.09):
    if iters <= 0:
        return [list(q) for q in chunk]
    ref = [list(q) for q in chunk]
    best = [list(q) for q in chunk]
    best_p = chunk_penalty(best, ref, obs)
    cur = [list(q) for q in best]
    cur_p = best_p
    for it in range(iters):
        i = rng.randrange(1, len(cur))
        cand = [list(q) for q in cur]
        cand[i][0] += rng.gauss(0.0, sigma)
        cand[i][1] += rng.gauss(0.0, sigma)
        cp = chunk_penalty(cand, ref, obs)
        if cp <= cur_p or rng.random() < 0.02:
            cur, cur_p = cand, cp
            if cp < best_p:
                best, best_p = [list(q) for q in cand], cp
    # cheap smoothing pass keeps the repaired trajectory natural
    for i in range(1, len(best) - 1):
        for j in (0, 1):
            best[i][j] += 0.15 * (best[i - 1][j] + best[i + 1][j] - 2 * best[i][j])
    return best


def vla_chunk(q, belief, rng, semantic_error):
    jitter = 0.17 if semantic_error else 0.018
    bx = belief[0] + rng.gauss(0.0, jitter)
    by = belief[1] + rng.gauss(0.0, jitter)
    goal = ik(bx, by, q)
    chunk = []
    for i in range(1, H + 1):
        s = i / H
        qq = [wrap(q[0] + (goal[0] - q[0]) * s + rng.gauss(0.0, 0.012)),
              wrap(q[1] + (goal[1] - q[1]) * s + rng.gauss(0.0, 0.012))]
        chunk.append(qq)
    if rng.random() < 0.10:   # occasional jerk / mode switch
        k = rng.randrange(H)
        chunk[k][0] += rng.choice((-1.0, 1.0)) * rng.uniform(0.15, 0.45)
        chunk[k][1] += rng.choice((-1.0, 1.0)) * rng.uniform(0.15, 0.45)
    return chunk


def hold_chunk(q, obs, rng):
    # if the current pose is already in collision, back away from the obstacle
    if not collides_waypoint(q, obs):
        target = list(q)
    else:
        ox, oy, _ = obs
        x, y = fk(q)
        dx, dy = x - ox, y - oy
        n = max(1e-6, math.hypot(dx, dy))
        target = ik(x + 0.10 * dx / n, y + 0.10 * dy / n, q)
    return [[target[0], target[1]] for _ in range(H)]


def plan_detour(q, goal_xy, obs, rng):
    """Cheap circular-obstacle detour: try both sides, return a feasible chunk."""
    x, y = fk(q)
    gx, gy = goal_xy
    ox, oy, orad = obs
    dx, dy = gx - x, gy - y
    L = max(1e-6, math.hypot(dx, dy))
    ux, uy = dx / L, dy / L
    # closest point on the current->goal segment to the obstacle
    t = max(0.0, min(1.0, ((ox - x) * ux + (oy - y) * uy)))
    cx, cy = x + t * dx, y + t * dy
    dist = math.hypot(ox - cx, oy - cy)
    if dist >= orad + ARM_R + 0.02:
        vias = [((x + gx) / 2, (y + gy) / 2)]
    else:
        rx, ry = -uy, ux
        push = orad + ARM_R + 0.06
        vias = [(ox + rx * push, oy + ry * push),
                (ox - rx * push, oy - ry * push),
                (ox + rx * push * 1.4, oy + ry * push * 1.4),
                (ox - rx * push * 1.4, oy - ry * push * 1.4)]
    best = None
    best_p = 1e18
    for vx, vy in vias:
        qv = ik(vx, vy, q)
        qg = ik(gx, gy, qv)
        pts = [q, qv, qg]
        chunk = []
        for i in range(1, H + 1):
            s = i / H
            if s <= 0.5:
                a, b, u = q, qv, s / 0.5
            else:
                a, b, u = qv, qg, (s - 0.5) / 0.5
            chunk.append([wrap(a[0] + (b[0] - a[0]) * u),
                          wrap(a[1] + (b[1] - a[1]) * u)])
        p = chunk_penalty(chunk, pts, obs)
        if feasible(chunk, obs) and p < best_p:
            best, best_p = chunk, p
    if best is None:
        return None
    for i in range(1, len(best) - 1):
        for j in (0, 1):
            best[i][j] += 0.12 * (best[i - 1][j] + best[i + 1][j] - 2 * best[i][j])
    return best


def execute(chunk, q, obs, rng, collision_flag):
    # execute the whole chunk; feedback only at the next boundary
    x_prev, y_prev = fk(q)
    for i, qq in enumerate(chunk):
        if limit_violation(qq) > 1e-9 or collides_waypoint(qq, obs):
            collision_flag[0] = True
        x, y = fk(qq)
        if collides_segment(q, qq, obs, n=3):
            collision_flag[0] = True
        q = [wrap(qq[0] + rng.gauss(0.0, 0.010)),
             wrap(qq[1] + rng.gauss(0.0, 0.010))]
    return q


def episode(policy, rng):
    q = [0.55, -0.95]
    r = rng.uniform(0.34, 0.78)
    ang = rng.uniform(-1.05, 1.05)
    target = (r * math.cos(ang), r * math.sin(ang))
    t = rng.uniform(0.35, 0.65)
    ox = target[0] * t + rng.uniform(-0.10, 0.10)
    oy = target[1] * t + rng.uniform(-0.10, 0.10)
    obs = (ox, oy, OBST_R + rng.uniform(-0.01, 0.02))

    semantic_error = rng.random() < 0.38
    if semantic_error:
        shift = rng.uniform(0.12, 0.26)
        a = rng.uniform(0, 2 * math.pi)
        belief = (target[0] + shift * math.cos(a), target[1] + shift * math.sin(a))
    else:
        belief = target

    q0 = list(q)
    x0, y0 = fk(q)
    d0 = math.hypot(x0 - target[0], y0 - target[1])
    min_d = d0
    collided = [False]
    latencies = []
    bg_ms = 0.0
    pending_vlm = False

    for c in range(MAX_CHUNKS):
        chunk = vla_chunk(q, belief, rng, semantic_error)
        ms = BASE_MS
        # ambiguity proxy: a visual/novelty signal, declared and calibrated
        ambiguous = (semantic_error and rng.random() < 0.85) or \
                    ((not semantic_error) and rng.random() < 0.12)

        # apply a VLM result that was computed in the previous execution window
        if policy in ("combined_async", "combined_async_periodic") and pending_vlm:
            pending_vlm = False
            hit = (semantic_error and rng.random() < 0.78) or \
                  ((not semantic_error) and rng.random() < 0.10)
            if hit and semantic_error and rng.random() < 0.85:
                semantic_error = False
                belief = target

        if policy == "vlm" or (policy == "combined" and ambiguous):
            ms += VLM_MS
            hit = (semantic_error and rng.random() < 0.78) or \
                  ((not semantic_error) and rng.random() < 0.10)
            if hit and semantic_error and rng.random() < 0.85:
                semantic_error = False
                belief = target

        if policy in ("empc", "combined", "combined_async", "combined_async_periodic"):
            budget = max(0, int((DEADLINE_MS - BASE_MS - REPAIR_C0) /
                                REPAIR_C_ITER))
            ms += REPAIR_C0 + REPAIR_C_ITER * budget
            repaired = repair(chunk, obs, budget, rng)
            if not feasible(repaired, obs):
                det = plan_detour(q, belief, obs, rng)
                repaired = det if det is not None else hold_chunk(q, obs, rng)
            chunk = repaired

        latencies.append(ms)
        q = execute(chunk, q, obs, rng, collided)
        x, y = fk(q)
        d = math.hypot(x - target[0], y - target[1])
        min_d = min(min_d, d)
        if d < TOL:
            break

        # launch asynchronous semantic verification after the chunk is released
        if policy == "combined_async" and ambiguous and not pending_vlm:
            pending_vlm = True
            bg_ms += VLM_MS
        if policy == "combined_async_periodic" and (c % 2 == 0) and not pending_vlm:
            pending_vlm = True
            bg_ms += VLM_MS

    x, y = fk(q)
    success = (min_d < TOL) and not collided[0]
    progress = max(0.0, min(1.0, (d0 - min_d) / max(d0, 1e-6)))
    safety = 0.0 if collided[0] else 1.0
    step_score = max(0.0, min(100.0, 55.0 * progress + 35.0 * safety +
                              10.0 * (1.0 if success else 0.0)))
    if collided[0]:
        step_score *= 0.45
    return {
        "success": 1.0 if success else 0.0,
        "step_score": step_score,
        "collision": 1.0 if collided[0] else 0.0,
        "latency_mean": statistics.mean(latencies),
        "latency_p95": sorted(latencies)[max(0, int(0.95 * len(latencies)) - 1)],
        "overrun": 1.0 if max(latencies) > DEADLINE_MS else 0.0,
        "bg_ms": bg_ms,
        "chunks": len(latencies),
    }


def run(policy, n, seed0=0):
    rng = random.Random(seed0)
    rows = [episode(policy, rng) for _ in range(n)]
    def m(k):
        return statistics.mean(r[k] for r in rows)
    def q(k, p):
        ys = sorted(r[k] for r in rows)
        return ys[min(len(ys) - 1, max(0, int(p * len(ys)) - 1))]
    return {
        "policy": policy,
        "n": n,
        "success": round(m("success"), 4),
        "step_score": round(m("step_score"), 2),
        "collision": round(m("collision"), 4),
        "latency_mean_ms": round(m("latency_mean"), 1),
        "latency_p95_ms": round(q("latency_p95", 0.95), 1),
        "overrun_rate": round(m("overrun"), 4),
        "mean_chunks": round(m("chunks"), 2),
        "bg_ms_per_episode": round(m("bg_ms"), 1),
    }


if __name__ == "__main__":
    N = 1800
    out = {
        "assumptions": {
            "chunk_H": H, "max_chunks": MAX_CHUNKS, "deadline_ms": DEADLINE_MS,
            "vlm_ms": VLM_MS, "policy_base_ms": BASE_MS,
            "semantic_error_prob": 0.38, "vlm_tpr": 0.78, "vlm_fpr": 0.10,
        },
        "rows": [run(p, N) for p in
                 ("openloop", "vlm", "empc", "combined", "combined_async",
                  "combined_async_periodic")],
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
