"""Synthetic mechanism checks for UniBot round-2 (contact-mode + path-critic).

NOT benchmark evidence. Two independent toys:
  A) insertion funnel: success vs clearance / perception floor / best-of-K critic
  B) clutter escape: reactive local policy vs A* recovery in random clutter
Written to be deterministic (fixed seeds) and dependency-light (numpy only).
"""
import json, math
import numpy as np

RNG = np.random.default_rng(20261118)

# ---------- A. insertion funnel ----------
def rayleigh_success(c_mm, sigma_mm):
    if sigma_mm <= 0:
        return 1.0
    return float(1.0 - math.exp(-(c_mm ** 2) / (2.0 * sigma_mm ** 2)))

def funnel_grid():
    cs = [0.5, 1.0, 2.0, 3.0, 5.0]
    sigmas = {"mono_lit": 1.0, "mono": 3.0, "mono_hard": 5.0, "stereo": 1.2}
    out = {}
    for name, s in sigmas.items():
        out[name] = {str(c): round(rayleigh_success(c, s), 4) for c in cs}
    return {"clearance_mm": cs, "sigma_mm": sigmas, "success": out}

def best_of_k(n_trials=200000, c=2.0, sigma_true=4.0, ks=(1, 2, 4, 8, 16),
              ratios=(0.0, 0.25, 0.5, 1.0, 2.0)):
    """e_true ~ N(0, sigma_true^2 I2); e_obs = e_true + N(0, sigma_obs^2 I2).
    Select argmin ||e_obs||; success if ||e_true|| <= c."""
    res = {}
    for r in ratios:
        so = r * sigma_true
        row = {}
        for K in ks:
            et = RNG.normal(0, sigma_true, size=(n_trials, K, 2))
            eo = et + RNG.normal(0, so if so > 0 else 1e-12, size=(n_trials, K, 2))
            idx = np.argmin((eo ** 2).sum(-1), axis=1)
            chosen = et[np.arange(n_trials), idx]
            row[str(K)] = round(float((np.linalg.norm(chosen, axis=1) <= c).mean()), 4)
        res["obs/true=" + str(r)] = row
    return {"c_mm": c, "sigma_true_mm": sigma_true, "n_trials": n_trials,
            "success": res}

# ---------- B. clutter escape ----------
def make_grid(n=80, density=0.15, seed=0):
    rng = np.random.default_rng(seed)
    g = np.zeros((n, n), dtype=np.uint8)
    # random rectangular obstacles covering ~density of cells
    target = int(density * n * n)
    cells = 0
    for _ in range(10000):
        if cells >= target:
            break
        w = rng.integers(3, 18); h = rng.integers(3, 18)
        x = rng.integers(1, n - w - 1); y = rng.integers(1, n - h - 1)
        add = (g[y:y+h, x:x+w] == 0).sum()
        g[y:y+h, x:x+w] = 1
        cells += int(add)
    # clear start/goal disks
    for cx, cy, r in [(6, 6, 4), (n - 7, n - 7, 4)]:
        g[max(0, cy-r):cy+r, max(0, cx-r):cx+r] = 0
    return g

def astar(g, start, goal):
    import heapq
    n = g.shape[0]
    if g[start] or g[goal]:
        return None
    openq = [(0.0, start)]
    dist = {start: 0.0}
    prev = {}
    seen = set()
    while openq:
        f, u = heapq.heappop(openq)
        if u in seen:
            continue
        seen.add(u)
        if u == goal:
            path = [u]
            while path[-1] in prev:
                path.append(prev[path[-1]])
            return path[::-1]
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                v = (u[0] + dx, u[1] + dy)
                if not (0 <= v[0] < n and 0 <= v[1] < n) or g[v]:
                    continue
                step = math.hypot(dx, dy)
                nd = dist[u] + step
                if nd < dist.get(v, 1e9):
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(openq, (nd + math.hypot(v[0]-goal[0], v[1]-goal[1]), v))
    return None

def local_policy(g, start, goal, max_steps=400, step=0.7):
    """Gradient of attractive + repulsive potential; deadlock if little progress."""
    n = g.shape[0]
    pos = np.array(start, float)
    goal = np.array(goal, float)
    obs = np.argwhere(g == 1).astype(float)
    # precompute obstacle influence on the fly (grid small)
    best = 1e9; stall = 0
    for t in range(max_steps):
        att = goal - pos
        d = np.linalg.norm(att)
        if d < 1.0:
            return True, t + 1
        u = att / (d + 1e-9)
        if len(obs):
            rel = obs - pos
            dd = np.linalg.norm(rel, axis=1)
            near = dd < 8.0
            if near.any():
                rep = -(rel[near] / (dd[near, None] + 1e-9)
                        * np.exp(-(dd[near] ** 2) / (2 * 3.0 ** 2))[:, None]).sum(0)
                u = u + 1.2 * rep
                u = u / (np.linalg.norm(u) + 1e-9)
        new = pos + step * u
        ix, iy = int(round(new[0])), int(round(new[1]))
        if 0 <= ix < n and 0 <= iy < n and not g[iy, ix]:
            pos = new
        else:
            # slide: try axis moves
            moved = False
            for cand in [(new[0], pos[1]), (pos[0], new[1])]:
                cx, cy = int(round(cand[0])), int(round(cand[1]))
                if 0 <= cx < n and 0 <= cy < n and not g[cy, cx]:
                    pos = np.array(cand); moved = True; break
            if not moved:
                stall += 1
        d = np.linalg.norm(goal - pos)
        if d < best - 0.5:
            best = d; stall = 0
        else:
            stall += 1
        if stall > 30:
            return False, t + 1
    return False, max_steps

def clutter_sweep():
    out = {}
    for density in [0.05, 0.10, 0.15, 0.20, 0.25]:
        succ_local = succ_astar = 0; trials = 60
        steps_l = steps_a = 0
        for s in range(trials):
            g = make_grid(density=density, seed=1000 + s)
            start = (6, 6); goal = (g.shape[0]-7, g.shape[0]-7)
            ok, st = local_policy(g, start, goal)
            succ_local += ok; steps_l += st
            path = astar(g, start, goal)
            if path is not None:
                succ_astar += 1; steps_a += len(path)
        out[str(density)] = {
            "local_success": round(succ_local / trials, 3),
            "astar_success": round(succ_astar / trials, 3),
            "local_avg_steps": round(steps_l / trials, 1),
            "astar_avg_steps": round(steps_a / max(succ_astar, 1), 1),
            "trials": trials,
        }
    return out

if __name__ == "__main__":
    res = {
        "meta": {
            "purpose": "synthetic mechanism checks, NOT UniBot benchmark evidence",
            "seed": 20261118,
            "note": "A tests when resampling/critic helps vs perception floor; B tests path planning as recovery in clutter.",
        },
        "funnel": funnel_grid(),
        "best_of_k": best_of_k(),
        "clutter": clutter_sweep(),
    }
    with open("exp/r2_cma/geometry_critic_results.json", "w") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))
