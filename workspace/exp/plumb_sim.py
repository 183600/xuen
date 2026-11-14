#!/usr/bin/env python3
"""PLUMB-RAS synthetic mechanism check (round 70: 3D perception x VLA).

NOT benchmark evidence. Isolates three claims behind the round:

  A. Phantom multimodality. A discrete-token / ODE-decoder VLA emits extra
     action clusters even when the scene is a point mass. R69-style AUD
     counts every cluster (entropy over all modes) as epistemic ambiguity and
     triggers interaction. MAG (multimodality authenticity gate = decoder
     resampling stability + 3D scene-identifiability) keeps genuine modes and
     drops phantoms, cutting false interaction on (i) single-hypothesis and
     (ii) intra-equivalence-class (unresolvable) episodes, while keeping recall
     on genuinely resolvable ambiguity.

  B. Unobserved != free. A planner that treats unknown (occluded / out of
     frustum) cells as free collides at a rate that scales with the occluded
     fraction. Certified-free-space planning (unknown => occupied) removes
     collisions at a bounded task-success cost.

  C. Channel-typed routing. Scene ambiguity is resolved by LOOK (active
     viewpoint), reference/instruction ambiguity by ASK. R69 computes a single
     VoI over action modes and therefore routes by raw entropy, ignoring
     observability kappa. Typed routing (gate by identifiability first) has
     lower residual uncertainty; the gap grows as the higher-entropy channel
     has lower observability.

Pure Python (stdlib only), deterministic seed. Reproduce:
    python plumb_sim.py > plumb_results.json
"""
import json
import math
import random
import statistics

SEED = 20261114


def entropy(weights):
    s = sum(weights)
    if s <= 0:
        return 0.0
    out = 0.0
    for w in weights:
        p = w / s
        if p > 1e-12:
            out -= p * math.log(p)
    return out


# ---------------------------------------------------------------- A. MAG
def sim_mag(n_episodes=20000, rng=None):
    """Belief over H=5 scene hypotheses, some mutually indistinguishable from
    every admissible viewpoint (occlusion / symmetry / out of reach). A VLA
    emits one action mode per alive hypothesis plus tokenizer phantoms."""
    rng = rng or random.Random(SEED)
    H = 5
    d_vis = 0.40          # prob a pair is separable by some admissible view
    r_art = 0.75          # prob an alive scene spawns a tokenizer phantom
    p_det = 0.90          # prob MAG flags a phantom via decoder resampling
    p_id = 0.95           # prob MAG flags a phantom as not scene-identifiable
    tau_epi = 0.30        # R69 MINT interaction threshold on mode entropy

    false_aud = false_mag = 0
    true_aud = true_mag = 0
    n_false = n_true = 0
    for _ in range(n_episodes):
        parent = list(range(H))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for i in range(H):
            for j in range(i + 1, H):
                if rng.random() > d_vis:      # not separable -> same class
                    ri, rj = find(i), find(j)
                    if ri != rj:
                        parent[ri] = rj

        alive = [i for i in range(H) if rng.random() < 0.5] or [rng.randrange(H)]
        comps = {find(i) for i in alive}
        resolvable = len(comps) > 1

        # genuine modes: one per alive hypothesis (scene-conditioned)
        genuine = []
        for i in alive:
            genuine.append({"comp": find(i), "w": rng.uniform(0.6, 1.4)})
        # phantom modes from tokenizer/decoder, no scene support
        phantoms = []
        for _ in range(len(alive)):
            if rng.random() < r_art:
                phantoms.append({"w": rng.uniform(0.05, 0.30)})

        # ---- R69 AUD: entropy over all clusters, interact if high
        aud_w = [m["w"] for m in genuine] + [m["w"] for m in phantoms]
        aud_interact = entropy(aud_w) > tau_epi

        # ---- MAG: drop phantoms (resampling stable AND scene-identifiable),
        # then interact only if >=2 distinct scene classes remain.
        kept = list(genuine)
        for ph in phantoms:
            # a phantom must fool BOTH the decoder-resampling gate and the
            # 3D scene-identifiability gate to enter the mode set
            survives = (rng.random() > p_det) and (rng.random() > p_id)
            if survives:
                kept.append({"comp": ("phantom", rng.random()), "w": ph["w"]})
        # a surviving phantom is treated as a distinct class -> may force
        # interaction; genuine intra-class modes do NOT count.
        classes = {m["comp"] for m in kept if not isinstance(m["comp"], tuple)}
        mag_interact = len(classes) > 1 or any(
            isinstance(m["comp"], tuple) for m in kept)

        if resolvable:
            n_true += 1
            true_aud += aud_interact
            true_mag += mag_interact
        else:
            n_false += 1
            false_aud += aud_interact
            false_mag += mag_interact

    return {
        "false_interaction_rate": {
            "R69_AUD": round(false_aud / max(n_false, 1), 4),
            "MAG": round(false_mag / max(n_false, 1), 4),
        },
        "resolvable_recall": {
            "R69_AUD": round(true_aud / max(n_true, 1), 4),
            "MAG": round(true_mag / max(n_true, 1), 4),
        },
        "n_no_resolvable_ambiguity": n_false,
        "n_resolvable_ambiguity": n_true,
    }


# ------------------------------------------------------- B. unobserved != free
def sim_free_space(grid=40, episodes=2000, rng=None):
    from collections import deque
    rng = rng or random.Random(SEED + 1)
    p_occ_given_unknown = 0.10

    def path_bfs(allow):
        prev = {(0, 0): None}
        q = deque([(0, 0)])
        goal = (grid - 1, grid - 1)
        while q:
            y, x = q.popleft()
            if (y, x) == goal:
                path = []
                cur = goal
                while cur is not None:
                    path.append(cur)
                    cur = prev[cur]
                return path[::-1]
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < grid and 0 <= nx < grid and \
                        (ny, nx) not in prev and allow(ny, nx):
                    prev[(ny, nx)] = (y, x)
                    q.append((ny, nx))
        return None

    rows = []
    for f in (0.05, 0.15, 0.25, 0.35, 0.45, 0.55):
        naive_coll = naive_succ = cons_succ = 0
        for _ in range(episodes):
            unknown = [[rng.random() < f for _ in range(grid)]
                       for _ in range(grid)]
            occ = [[unknown[y][x] and rng.random() < p_occ_given_unknown
                    for x in range(grid)] for y in range(grid)]

            # naive: unknown is free at plan time; collide if the chosen path
            # crosses a truly occupied (previously unknown) cell
            p_naive = path_bfs(lambda y, x: True)
            if p_naive is not None:
                if any(occ[y][x] for y, x in p_naive):
                    naive_coll += 1
                else:
                    naive_succ += 1

            # certified free-space: only cells observed free are traversable
            p_cons = path_bfs(lambda y, x: (not unknown[y][x]) and (not occ[y][x]))
            if p_cons is not None:
                cons_succ += 1

        rows.append({
            "occluded_fraction": f,
            "naive_collision_rate": round(naive_coll / episodes, 4),
            "naive_success_rate": round(naive_succ / episodes, 4),
            "certified_free_success_rate": round(cons_succ / episodes, 4),
        })
    return rows


# ------------------------------------------------------- C. typed routing
def sim_routing(n_episodes=20000, rng=None):
    """One information action per episode. Scene entropy H_s (LOOK) and
    reference entropy H_r (ASK). LOOK observability kappa_L; ASK trust kappa_A.
    Cross-channel leakage lam > 0 (R69 fuses modalities)."""
    rng = rng or random.Random(SEED + 2)
    lam = 0.15
    res = {"typed": [], "r69": [], "always_ask": [], "always_look": []}
    misroute = 0
    for _ in range(n_episodes):
        H_s = rng.uniform(0.0, math.log(5.0))
        H_r = rng.uniform(0.0, math.log(4.0))
        kL = rng.uniform(0.0, 1.0)      # viewpoint observability
        kA = rng.uniform(0.3, 1.0)      # human answer reliability

        # TRUE expected reduction of each channel
        look = kL * H_s + lam * H_r
        ask = kA * H_r + lam * H_s

        # TYPED: choose the truly better channel (identifiability-gated)
        typed = max(look, ask)

        # R69: single VoI over action modes -> routes by RAW entropy, i.e.
        # assumes observability/trust = 1. Scored on the TRUE reduction of the
        # channel it actually picked.
        r69_choice_look = H_s >= H_r
        r69 = look if r69_choice_look else ask
        if (r69_choice_look and ask > look) or ((not r69_choice_look) and look > ask):
            misroute += 1

        total = H_s + H_r
        res["typed"].append(total - typed)
        res["r69"].append(total - r69)
        res["always_ask"].append(total - ask)
        res["always_look"].append(total - look)

    def mean(xs):
        return round(statistics.fmean(xs), 4)

    return {
        "mean_residual_entropy": {k: mean(v) for k, v in res.items()},
        "typed_improvement_vs_r69": round(mean(res["r69"]) - mean(res["typed"]), 4),
        "r69_misroute_rate": round(misroute / n_episodes, 4),
        "leakage_lambda": lam,
    }


def main():
    out = {
        "claim_A_phantom_multimodality": sim_mag(),
        "claim_B_unobserved_not_free": sim_free_space(),
        "claim_C_channel_routing": sim_routing(),
        "note": "Toy mechanism check only; not benchmark evidence.",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
