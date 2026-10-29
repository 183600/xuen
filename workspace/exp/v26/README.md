# exp/v26 — CPS parallel / Monte-Carlo prototypes (v2.2 round 3)

Core CPS lives in `exp/v25/cps_lib.py` and is integrated in `exp/v25/pace_v25.py`.
This directory contains only the round-3 scaling prototypes:

- `par_cps.py` — fork-based PAR-CPS over placements (no /dev/shm needed).
- `mc_chain.py` — random-chain portfolio under a per-placement node cap.
- `chain_analysis.py` — critical vs longest chain on the 5 held-out residuals.
- `res_par.json`, `res_mc.json`, `res_chain.json` — measured results.

Run from the workspace root:

```bash
python exp/v26/par_cps.py
python exp/v26/mc_chain.py
python exp/v26/chain_analysis.py
```
