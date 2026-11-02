"""CHOIR / FLEET-SM synthetic mechanism check (new inspiration cycle; words:
multi-robot collaboration / state machine / disturbance rejection).

Round-15 ZEST-VLA gates every port independently: action-observation residuals
are self-normalized (sliding MAD) then passed to a conformal/CUSUM trust gate.
Two residues (round-15 s5.8):
  (i)  a *shared* environmental change (lighting/calibration drift hitting every
       robot at once) inflates every port's raw residual; if it lasts longer than
       the MAD window, the per-port CUSUM trips -> false FALLBACK on every robot;
  (ii) a *local* disturbance and a *shared* one look identical inside a single
       port's stream, so the per-port machine cannot choose the right recovery
       branch.

UniBot runs N robots concurrently on one submission (README s4: N consecutive
ports, episode state isolated, optionally one shared model backend).  That gives
one signal no single agent has: are surprise events *simultaneous* across ports?

CHOIR = fleet-level hierarchical state machine.  Meta-state from the cross-port
surprise fraction f_t (#surprised / N):
    f_t >= majority -> GLOBAL: veto per-port FALLBACK (treat as shared event);
    f_t <  majority -> LOCAL : per-port CUSUM exactly as ZEST.
Only surprise *indicators* + timestamps are shared; no episode state.

NOT benchmark evidence.  Declared generative model, never fitted.  Cross-port
synchronisation is assumed via a short server-side wall-clock window; the async
cost is a stated validity threat.
"""
import json
import math
import os
import random
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "choir_results.json")


def q(xs, p):
    ys = sorted(xs)
    if not ys:
        return 0.0
    i = min(len(ys) - 1, max(0, int(math.ceil(p * len(ys))) - 1))
    return ys[i]


def make_env(rng, T, p_nuis, L_nuis, shared_ood):
    """Shared per-tick environment: (nuisance, shared_ood)."""
    env = [(0, 0)] * T
    t = 0
    while t < T:
        if rng.random() < p_nuis:
            L = rng.randint(max(2, L_nuis // 2), L_nuis)
            for i in range(t, min(T, t + L)):
                env[i] = (1, 0)
            t += L
        else:
            t += 1
    if shared_ood:
        start = rng.randint(0, max(0, T - 4))
        L = rng.randint(4, max(4, T // 2))
        for i in range(start, min(T, start + L)):
            env[i] = (0, 1)
    return env


def run_fleet(policy, rng, N, T, p_need, pi_local, local_L, p_nuis, L_nuis,
              shared_ood, qz, alpha=0.12, k=0.05, h=2.5, W=5, q_raw=0.42,
              g_mult=4.0, g_fb=0.55, fb_cost=1.4, p_id=0.80, p_ood=0.20):
    onset = []
    local_Ls = []
    for _ in range(N):
        if rng.random() < pi_local:
            onset.append(rng.randint(1, max(1, T - 2)))
            local_Ls.append(rng.randint(2, local_L))
        else:
            onset.append(None)
            local_Ls.append(0)
    env = make_env(rng, T, p_nuis, L_nuis, shared_ood)
    maj = max(2, int(math.ceil(0.6 * N))) if N > 1 else 10 ** 9

    progress = [0.0] * N
    win = [[] for _ in range(N)]
    cusum = [0.0] * N
    mode = ["vla"] * N
    dwell = [0] * N
    n_fb_id = n_fb_ood = n_fb_tot = n_fb_nuis = 0
    n_ood_ticks = n_local_ticks = 0
    recalib = 1.0

    for t in range(T):
        nuis, shood = env[t]
        comp = []
        sur = []
        zs = []
        for i in range(N):
            loc = onset[i] is not None and onset[i] <= t < onset[i] + local_Ls[i]
            c = (not loc) and (not shood)
            comp.append(c)
            mu = 0.20 if c else 0.90
            raw = max(0.0, rng.gauss(mu, 0.15))
            if nuis or shood:
                raw *= g_mult
            win[i].append(raw)
            if len(win[i]) > W:
                win[i].pop(0)
            med = st.median(win[i])
            mad = st.median([abs(x - med) for x in win[i]])
            scale = (1.4826 * mad + 0.05) * recalib
            z = raw / scale
            zs.append(z)
            s = 1 if z > qz else 0
            sur.append(s)
            cusum[i] = max(0.0, cusum[i] + s - alpha - k)
            if loc:
                n_local_ticks += 1
            if not c:
                n_ood_ticks += 1

        f = sum(sur) / N
        global_alert = (N > 1) and (f >= maj / N - 1e-9)
        recalib = 1.6 if global_alert else max(1.0, recalib - 0.2)

        for i in range(N):
            c = comp[i]
            if policy == "vla":
                act = "servo"
            elif policy == "oracle":
                act = "servo" if c else "fallback"
            elif policy == "fixed":
                act = "fallback" if (len(win[i]) >= W and
                                     st.mean(win[i]) > q_raw) else "servo"
            else:  # zest / choir
                veto = policy == "choir" and global_alert
                if mode[i] == "fallback":
                    dwell[i] += 1
                    if dwell[i] >= 3:
                        act = "servo"
                        mode[i] = "probe"
                    else:
                        act = "fallback"
                else:
                    if cusum[i] > h and not veto:
                        mode[i] = "fallback"
                        dwell[i] = 0
                        act = "fallback"
                    else:
                        act = "servo"
            if act == "servo":
                ok = rng.random() < (p_id if c else p_ood)
            else:
                ok = rng.random() < g_fb
                n_fb_tot += 1
                if c:
                    n_fb_id += 1
                    if nuis or shood:
                        n_fb_nuis += 1
                else:
                    n_fb_ood += 1
            if ok:
                progress[i] += 1.0

    succ = st.mean([1.0 if progress[i] >= p_need else 0.0 for i in range(N)])
    return (succ, n_fb_id / N, n_fb_ood / N,
            n_fb_nuis / max(1, n_fb_tot), n_fb_tot / N,
            n_local_ticks, n_ood_ticks)


def evaluate(policy, n_ep=8000, seed=11, **kw):
    rng = random.Random(seed)
    acc = [run_fleet(policy, rng, **kw) for _ in range(n_ep)]
    m = lambda j: st.mean(a[j] for a in acc)
    succ = m(0)
    return dict(succ=succ, fb_id=m(1), fb_ood=m(2),
                fb_nuis_frac=m(3), fb_tot=m(4),
                local_ticks=m(5), ood_ticks=m(6),
                spc=succ / max(1e-9, 1 + m(4) * 0.4))


def calibrate_qz(n=4000, seed=99):
    rng = random.Random(seed)
    cal = []
    for _ in range(n):
        w = []
        for _ in range(6):
            raw = max(0.0, rng.gauss(0.20, 0.15))
            w.append(raw)
            med = st.median(w)
            mad = st.median([abs(x - med) for x in w])
            cal.append(raw / (1.4826 * mad + 0.05))
    return q(cal, 0.90)


if __name__ == "__main__":
    qz = calibrate_qz()
    print("calibrated q_z =", round(qz, 3))
    base = dict(N=3, T=14, p_need=3.0, pi_local=0.10, local_L=5, p_nuis=0.0,
                L_nuis=12, shared_ood=False, qz=qz)
    rows = []

    def show(tag, pols, **kw):
        print(f"\n## {tag}")
        for pol in pols:
            r = evaluate(pol, **kw)
            r.update(policy=pol, scenario=tag, N=kw.get("N", base["N"]))
            rows.append(r)
            print(f"{pol:7s} succ {r['succ']:.3f} fb_id {r['fb_id']:.2f} "
                  f"fb_ood {r['fb_ood']:.2f} fb_nuisfrac {r['fb_nuis_frac']:.2f} "
                  f"fb_tot {r['fb_tot']:.2f}")

    pols = ["vla", "fixed", "zest", "choir", "oracle"]
    show("A. sustained shared nuisance (VLA still competent)", pols,
         **dict(base, pi_local=0.10, p_nuis=0.35, L_nuis=14))
    show("B. local OOD only, no nuisance", pols,
         **dict(base, pi_local=0.45, p_nuis=0.0))
    show("C. boundary: genuinely SHARED OOD (all ports incompetent)",
         ["vla", "zest", "choir", "oracle"],
         **dict(base, pi_local=0.0, p_nuis=0.0, shared_ood=True))
    show("D. mixed: shared nuisance + one genuinely disturbed port",
         ["zest", "choir", "oracle"],
         **dict(base, pi_local=0.60, local_L=8, p_nuis=0.35, L_nuis=14))

    print("\n## E. correlation-test power vs N (scenario A)")
    sweep = []
    for N in (1, 2, 3, 4, 6):
        kw = dict(base, N=N, pi_local=0.10, p_nuis=0.35, L_nuis=14)
        rz = evaluate("zest", n_ep=6000, **kw)
        rc = evaluate("choir", n_ep=6000, **kw)
        row = dict(N=N, zest_fb_id=round(rz["fb_id"], 2),
                   choir_fb_id=round(rc["fb_id"], 2),
                   zest_succ=round(rz["succ"], 3),
                   choir_succ=round(rc["succ"], 3),
                   fb_id_reduction_pct=round(
                       100 * (rz["fb_id"] - rc["fb_id"]) /
                       max(1e-9, rz["fb_id"]), 1))
        sweep.append(row)
        print(row)

    out = {"calibration_qz": qz, "rows": rows, "N_sweep": sweep,
           "note": "synthetic mechanism check; not benchmark evidence; "
                   "cross-port sync assumed via server wall-clock window"}
    json.dump(out, open(OUT, "w"), indent=2)
    print("\nwrote", OUT)
