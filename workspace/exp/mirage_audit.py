"""MIRAGE-RAS toy audit (two modes, two info actions; synthetic, not real robot).

Question: does ranking info actions by simulation separability (R69-style VoI)
select an irreversible contact probe whose REAL separability collapsed
(sim-to-real mirage)?  Compare with a certificate-gated VoI (MIRAGE).

Decision rule uses the balanced (minimax) binary error, for which Le Cam gives
the exact achievable error (1 - delta)/2, so the gain over the 0.5 prior is
delta/2.  This makes the certified gain delta_LB/2 a rigorous lower bound.

Run: python exp/mirage_audit.py
"""
import json
import random

SEED = 20261115
N = 20000


def gain(delta):
    # Balanced binary decision: prior error 0.5, optimal error (1-delta)/2.
    return max(0.0, delta / 2.0)


def pick(cands, certified):
    best = None
    for g in cands:
        delta = g["dl"] if certified else g["ds"]
        value = gain(delta) - g["c"]
        if certified:
            value -= g["r"]          # R69 does not charge irreversible cost
        if best is None or value > best[1]:
            best = (g, value)
    return None if best is None or best[1] <= 0 else best[0]


def run():
    rng = random.Random(SEED)
    stats = {k: dict(probe=0, contact=0, low_sep=0, util=0.0)
             for k in ("r69", "mirage", "oracle")}
    inversion = 0
    for _ in range(N):
        ds_v, ds_c = rng.uniform(0.15, 0.35), rng.uniform(0.85, 0.99)
        g_v, g_c = rng.uniform(0.02, 0.08), rng.uniform(0.10, 0.50)
        L_v, L_c, q = 1.0, 2.0, 0.05
        dr_v = min(1, max(0, ds_v - L_v * g_v + rng.gauss(0, 0.02)))
        dr_c = min(1, max(0, ds_c - L_c * g_c + rng.gauss(0, 0.02)))
        dl_v = min(1, max(0, ds_v - L_v * g_v - q))
        dl_c = min(1, max(0, ds_c - L_c * g_c - q))
        if ds_c > ds_v and dl_c < dl_v:
            inversion += 1
        cands = [
            dict(name="vision", ds=ds_v, dl=dl_v, dr=dr_v, c=0.01, r=0.00),
            dict(name="contact", ds=ds_c, dl=dl_c, dr=dr_c, c=0.03, r=0.10),
        ]
        for kind in ("r69", "mirage", "oracle"):
            g = pick(cands, certified=(kind != "r69"))
            if g is None:
                continue
            stats[kind]["probe"] += 1
            stats[kind]["util"] += gain(g["dr"]) - g["c"] - g["r"]
            if g["name"] == "contact":
                stats[kind]["contact"] += 1
                if g["dr"] < 0.30:
                    stats[kind]["low_sep"] += 1
    out = {"seed": SEED, "N": N, "inversion_rate": inversion / N}
    for k, s in stats.items():
        out[k] = {
            "probe_rate": s["probe"] / N,
            "contact_rate": s["contact"] / N,
            "contact_low_sep_rate": s["low_sep"] / N,
            "mean_net_utility": s["util"] / N,
        }
    return out


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
