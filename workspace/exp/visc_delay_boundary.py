"""Exact stability boundary of the scalar delayed visual-servo integrator.

The linearized loop is the difference equation

    e_{t+1} = e_t - lam * e_{t-d}          (scalar, perfect plant)

with characteristic polynomial z^{d+1} - z^d + lam = 0.  The largest gain
with all roots strictly inside the unit circle is

    lam_max(d) = 2 * sin(pi / (4*d + 2)).

This script verifies the closed form with a numeric root scan and prints the
sequence used in the round-v3 artifact.  It is a local linear-analysis result,
not a robot experiment.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

EXP = Path("/home/runner/work/xuen/xuen/workspace/exp")
OUT = EXP / "visc_delay_boundary_results.json"


def scalar_stable(delay: int, lam: float) -> bool:
    coeffs = np.zeros(delay + 2)
    coeffs[0] = 1.0
    coeffs[1] = -1.0
    coeffs[-1] += lam
    if delay == 0:
        # z - 1 + lam = 0  ->  coeffs = [1, lam - 1]
        coeffs = np.array([1.0, lam - 1.0])
    roots = np.roots(coeffs)
    return bool(np.max(np.abs(roots)) < 1.0 - 1e-12)


def numeric_max(delay: int) -> float:
    lo, hi = 0.0, 3.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if scalar_stable(delay, mid):
            lo = mid
        else:
            hi = mid
    return lo


def main() -> None:
    rows = []
    for d in range(0, 9):
        closed = 2.0 * math.sin(math.pi / (4 * d + 2))
        num = numeric_max(d)
        rows.append({
            "delay_chunks": d,
            "closed_form": round(closed, 6),
            "numeric": round(num, 6),
            "abs_error": round(abs(closed - num), 6),
        })
    out = {
        "note": "local linear stability of a scalar delayed integrator; not a robot result",
        "formula": "lam_max(d) = 2 sin(pi/(4d+2))",
        "rows": rows,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT}")
    for r in rows:
        print(f"d={r['delay_chunks']} closed={r['closed_form']:.4f} "
              f"numeric={r['numeric']:.4f} err={r['abs_error']:.2e}")


if __name__ == "__main__":
    main()
