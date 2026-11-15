"""Synthetic mechanism check for FlowArmGauge (this thread, round 4).

NOT benchmark evidence. Claims isolated here:
  A. Flow-ODE error scales with 1/NFE; Lipschitz L<1 attenuates, L>1 amplifies.
  B. On a 2-link arm under inertia-model bias:
     - endpoint-only plan (no guard) collides on an on-path obstacle;
     - a runtime braking guard alone is too late for an unsafe plan;
     - a plan-level braking-safe time-scaling + runtime guard stops safely.
     - with no obstacle, plan-level guard does not false-stop.
Stdlib only, seeded, ~10s.
"""
import json, math, random

SEED = 20261115
L1 = L2 = 0.55
QMIN, QMAX = -2.6, 2.6
VMAX = 2.0
TAUMAX = 18.0
DT = 0.005
T = 1.5
I1 = I2 = 0.08
OBST_R = 0.16
GUARD_MARGIN = 0.10
GUARD_INERTIA = 3.5
SCALES = (1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 6.0, 8.0)


def fk(q):
    q1, q2 = q
    x1 = L1 * math.cos(q1); y1 = L1 * math.sin(q1)
    x2 = x1 + L2 * math.cos(q1 + q2); y2 = y1 + L2 * math.sin(q1 + q2)
    return (0.0, 0.0), (x1, y1), (x2, y2)


def seg_dist(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    den = dx * dx + dy * dy
    t = 0.0 if den < 1e-12 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / den))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def clear(q, obst):
    pts = fk(q)
    return min(seg_dist(obst, pts[i], pts[i + 1]) for i in range(2)) - OBST_R


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * t * (10 - 15 * t + 6 * t * t)


def traj(q0, q1, t):
    s = smooth(t / T)
    ds = (30 * (t / T) ** 2 * (1 - t / T) ** 2) / T if 0 < t < T else 0.0
    dds = (60 * (t / T) * (1 - t / T) * (1 - 2 * t / T)) / (T * T) if 0 < t < T else 0.0
    q = (q0[0] + (q1[0] - q0[0]) * s, q0[1] + (q1[1] - q0[1]) * s)
    qd = ((q1[0] - q0[0]) * ds, (q1[1] - q0[1]) * ds)
    qdd = ((q1[0] - q0[0]) * dds, (q1[1] - q0[1]) * dds)
    return q, qd, qdd


def brake_ok(q, qd, obst, inertia_hi):
    qq = [q[0], q[1]]; vv = [qd[0], qd[1]]
    a = TAUMAX / inertia_hi
    for _ in range(80):
        if max(abs(x) for x in vv) < 1e-3:
            break
        for j in range(2):
            vv[j] = 0.0 if abs(vv[j]) <= a * DT else vv[j] - math.copysign(a * DT, vv[j])
        for j in range(2):
            qq[j] += vv[j] * DT
        if any(qq[j] < QMIN + GUARD_MARGIN or qq[j] > QMAX - GUARD_MARGIN for j in range(2)):
            return False
        if clear(qq, obst) < GUARD_MARGIN:
            return False
    return True


def safe_scale(q0, q1, obst, inertia_hi, m=400):
    for sc in SCALES:
        ok = True
        for k in range(m):
            tau = T * k / (m - 1)
            q, qd, _ = traj(q0, q1, tau)
            if not brake_ok(q, [x / sc for x in qd], obst, inertia_hi):
                ok = False
                break
        if ok:
            return sc
    return None


def run_case(q0, q1, obst, bias, guard, plan_safe):
    inn = I1 + I2
    iact = inn * (1.0 + bias)
    sc = safe_scale(q0, q1, obst, inn * GUARD_INERTIA) if plan_safe else 1.0
    if plan_safe and sc is None:
        return dict(collided=False, limit=False, min_clear=9.0,
                    stopped=True, reached=False, scale=0.0, rejected=True)
    Ttot = T * sc
    nstep = int(Ttot / DT)
    q = [q0[0], q0[1]]; qd = [0.0, 0.0]
    kp, kd = 60.0, 12.0
    collided = limit = False
    min_clear = 9.0
    stopped = False
    for k in range(nstep):
        t = k * DT
        tau = min(T, t / sc)
        qb, qdb, qddb = traj(q0, q1, tau)
        qdes = qb
        qddes = [x / sc for x in qdb]
        qdddes = [x / (sc * sc) for x in qddb]
        err = [qdes[j] - q[j] for j in range(2)]
        derr = [qddes[j] - qd[j] for j in range(2)]
        u = [inn * qdddes[j] + kp * err[j] + kd * derr[j] for j in range(2)]
        u = [max(-TAUMAX, min(TAUMAX, x)) for x in u]
        if guard and not stopped:
            qn = [q[j] + qd[j] * DT for j in range(2)]
            qdn = [qd[j] + (u[j] / inn) * DT for j in range(2)]
            hi = inn * GUARD_INERTIA
            if not brake_ok(q, qd, obst, hi) or not brake_ok(qn, qdn, obst, hi):
                stopped = True
        if stopped:
            u = [-TAUMAX * (1 if qd[j] > 0 else -1) if abs(qd[j]) > 1e-6 else -kp * q[j]
                 for j in range(2)]
        c = clear(q, obst)
        min_clear = min(min_clear, c)
        if c < 0:
            collided = True
        if any(q[j] <= QMIN or q[j] >= QMAX for j in range(2)):
            limit = True
        qdd = [u[j] / iact for j in range(2)]
        for j in range(2):
            qd[j] = max(-VMAX, min(VMAX, qd[j] + qdd[j] * DT))
            q[j] += qd[j] * DT
        if stopped and max(abs(x) for x in qd) < 0.02:
            break
    reached = math.hypot(q[0] - q1[0], q[1] - q1[1]) < 0.08
    return dict(collided=collided, limit=limit, min_clear=min_clear,
                stopped=stopped, reached=reached, scale=sc, rejected=False)


def summarize(rs):
    return dict(
        n=len(rs),
        collision_rate=sum(r["collided"] for r in rs) / len(rs),
        limit_rate=sum(r["limit"] for r in rs) / len(rs),
        reached_rate=sum(r["reached"] for r in rs) / len(rs),
        stop_rate=sum(r["stopped"] for r in rs) / len(rs),
        mean_scale=round(sum(r["scale"] for r in rs) / len(rs), 3),
        reject_rate=sum(r["rejected"] for r in rs) / len(rs),
        min_clear_p05=round(sorted(r["min_clear"] for r in rs)[max(0, int(0.05 * len(rs)) - 1)], 4),
    )


def nominal_clear(q0, q1, obst, m=300):
    return min(clear(traj(q0, q1, T * k / (m - 1))[0], obst) for k in range(m))


def part_b(n=100):
    rng = random.Random(SEED + 7)
    variants = {"baseline": (False, False), "guard_only": (True, False), "plan_guard": (True, True)}
    groups = {"no_obstacle": [], "tight": [], "on_path": []}
    for group in groups:
        made = 0
        while made < n:
            q0 = (-1.15 + rng.uniform(-0.15, 0.15), 0.75 + rng.uniform(-0.15, 0.15))
            q1 = (0.95 + rng.uniform(-0.15, 0.15), -0.55 + rng.uniform(-0.15, 0.15))
            if group == "no_obstacle":
                obst = (10.0, 10.0)
            else:
                obst = (rng.uniform(-0.5, 1.4), rng.uniform(-1.0, 1.0))
            nc = nominal_clear(q0, q1, obst)
            if group == "tight" and not (0.0 <= nc <= 0.15):
                continue
            if group == "on_path" and not (nc < -0.02):
                continue
            made += 1
            bias = rng.uniform(0.1, 1.5)
            for name, (g, p) in variants.items():
                groups[group].append((name, run_case(q0, q1, obst, bias, g, p)))
    out = {}
    for group, items in groups.items():
        out[group] = {name: summarize([r for nme, r in items if nme == name]) for name in variants}
    return out


def part_a():
    out = {}
    for lam in (2.0, 0.0, -2.0):
        rows = []
        for N in (4, 8, 16, 32, 64):
            errs = []
            for x0 in (-2.0, -1.0, 0.0, 1.0, 2.0):
                exact = x0 * math.exp(-lam)
                x = x0
                for _ in range(N):
                    x += (-lam * x) / N
                errs.append(abs(x - exact))
            rows.append(dict(N=N, max_abs_err=round(max(errs), 6)))
        out[str(lam)] = dict(flow_lipschitz=round(math.exp(-lam), 4), rows=rows)
    return out


if __name__ == "__main__":
    print(json.dumps(dict(part_a=part_a(), part_b=part_b()), indent=2, ensure_ascii=False))
