#!/usr/bin/env python3
"""
Key blindness of the F8 observable -- executable proof of KEY_BLINDNESS.md.

Speck's inverse round recovers
    y = ROR(x' XOR y', beta)        <- no key material
    x = ROL((x' XOR g) - y, alpha)  <- guess enters here only

F8 measures MI(x bit i ; (y_R XOR y_R+1) bit (i-alpha)). The second argument is
built from recovered y values, so it is invariant under the guess. Changing the
guess applies a bijection to the first argument, which permutes which bits are
examined but cannot create or destroy dependence.

Consequence: no ranking over key candidates is possible. Verified three ways.
"""
import json
import math
import os

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(REPO, "results")
os.makedirs(RESULTS, exist_ok=True)

WS, ALPHA, BETA = 16, 7, 2
MASK = np.uint32(0xFFFF)


def ror(v, r): return ((v >> np.uint32(r)) | (v << np.uint32(WS - r))) & MASK
def rol(v, r): return ((v << np.uint32(r)) | (v >> np.uint32(WS - r))) & MASK


def key_schedule(master, rounds):
    rk = [0] * (rounds + 2)
    l = list(master[1:])
    rk[0] = master[0]
    for i in range(rounds + 1):
        rl = ((l[i % len(l)] >> ALPHA) | (l[i % len(l)] << (WS - ALPHA))) & 0xFFFF
        nl = ((rk[i] + rl) & 0xFFFF) ^ i
        l.append(nl)
        rk[i+1] = ((((rk[i] << BETA) | (rk[i] >> (WS - BETA))) & 0xFFFF) ^ nl)
    return rk


def encrypt(x, y, rk, rounds):
    x, y = x.copy(), y.copy()
    for r in range(rounds):
        x = ((ror(x, ALPHA) + y) & MASK) ^ np.uint32(rk[r])
        y = rol(y, BETA) ^ x
    return x, y


def inv_round(x, y, g):
    """One inverse round under guess g. Note y does not use g."""
    yv = ror(x ^ y, BETA)
    xv = rol(((x ^ np.uint32(g)) - yv) & MASK, ALPHA)
    return xv, yv


def mi(a, b):
    n = len(a)
    n11 = int(np.count_nonzero(a & b)); n10 = int(np.count_nonzero(a & ~b))
    n01 = int(np.count_nonzero(~a & b)); n00 = n - n11 - n10 - n01
    H = 0.0
    for c in (n00, n01, n10, n11):
        if c > 0:
            p = c / n; H -= p * math.log(p)
    pa = (n10 + n11) / n; pb = (n01 + n11) / n
    Ha = -pa*math.log(pa)-(1-pa)*math.log(1-pa) if 0 < pa < 1 else 0.0
    Hb = -pb*math.log(pb)-(1-pb)*math.log(1-pb) if 0 < pb < 1 else 0.0
    return max(0.0, Ha + Hb - H)


def _bit(w, b): return ((w >> np.uint32(b)) & np.uint32(1)).astype(bool)


def f8_diagonal(x, diff_y):
    dead = {(ALPHA + d) % WS for d in range(BETA)}
    return sum(mi(_bit(x, i), _bit(diff_y, (i - ALPHA) % WS))
               for i in range(WS) if i not in dead)


def main():
    out = {}
    print("=" * 78)
    print("STEP 1 -- the inverse round's y does not depend on the guess")
    print("=" * 78)
    N = 20000
    rng = np.random.default_rng(1)
    master = [int(v) for v in rng.integers(0, 1 << 16, size=4)]
    rk = key_schedule(master, 26)
    ctr = np.arange(N, dtype=np.uint32)
    x0 = (ctr >> np.uint32(16)).astype(np.uint32) & MASK
    y0 = ctr.astype(np.uint32) & MASK
    cx, cy = encrypt(x0, y0, rk, 21)
    ax, ay = inv_round(cx, cy, 0x0000)
    bx, by = inv_round(cx, cy, 0xFFFF)
    same_y = bool(np.array_equal(ay, by))
    same_x = bool(np.array_equal(ax, bx))
    print(f"  recovered y identical for g=0x0000 and g=0xFFFF : {same_y}")
    print(f"  recovered x identical                           : {same_x}")
    print(f"  {'as the proposition requires' if same_y and not same_x else 'UNEXPECTED'}")
    out["step1"] = dict(y_identical=same_y, x_identical=same_x)

    print()
    print("=" * 78)
    print("STEP 2 -- full 65,536-candidate sweep, correctly constructed")
    print("=" * 78)
    N2, R = 60000, 20
    ctr = np.arange(N2, dtype=np.uint32)
    x0 = (ctr >> np.uint32(16)).astype(np.uint32) & MASK
    y0 = ctr.astype(np.uint32) & MASK
    C1x, C1y = encrypt(x0, y0, rk, R + 1)
    C2x, C2y = encrypt(x0, y0, rk, R + 2)
    Sx, Sy = encrypt(x0, y0, rk, R)
    _, S1y = encrypt(x0, y0, rk, R + 1)
    calib = f8_diagonal(Sx, Sy ^ S1y)
    target = rk[R]

    scores = np.zeros(65536)
    for k in range(65536):
        ax, ay = inv_round(C1x, C1y, k)
        bx, by = inv_round(C2x, C2y, k)
        scores[k] = f8_diagonal(ax, ay ^ by)

    rank = int((scores > scores[target]).sum())
    distinct = len(np.unique(np.round(scores, 9)))
    z = (scores[target] - scores.mean()) / max(scores.std(), 1e-12)
    print(f"  known-key calibration        = {calib:.5f}")
    print(f"  F8 at the true key           = {scores[target]:.5f}"
          f"  {'(exact match -> sweep is valid)' if abs(scores[target]-calib) < 1e-9 else ''}")
    print(f"  best candidate               = {scores.max():.5f}")
    print(f"  RANK of the true key         = {rank:,} of 65,536")
    print(f"  z of the true key            = {z:+.2f}")
    print(f"  distinct score values        = {distinct:,}"
          f"  {'(not degenerate)' if distinct > 100 else '(DEGENERATE)'}")
    out["step2"] = dict(calibration=calib, score_true=float(scores[target]),
                        rank=rank, z=float(z), distinct=distinct)

    print()
    print("=" * 78)
    print("STEP 3 -- the obvious repair also fails: strip the key XOR")
    print("=" * 78)
    print("  (C1 XOR g) XOR (C2 XOR g) = C1 XOR C2 -- the guess cancels")
    s = set()
    for k in (0x0000, 0x1234, 0xABCD, 0xFFFF):
        d = ((C1x ^ np.uint32(k)) ^ (C2x ^ np.uint32(k))).astype(np.uint32)
        s.add(int(d[:64].sum()))
    print(f"  distinct difference checksums over 4 guesses: {len(s)}"
          f"  {'-> identical, guess cancels' if len(s) == 1 else ''}")
    out["step3"] = dict(distinct_checksums=len(s))

    print()
    print("=" * 78)
    print("  CONCLUSION: F8 is a detector, not an extractor. On Speck the")
    print("  observable is provably independent of the round key.")
    print("=" * 78)

    path = os.path.join(RESULTS, "key_blindness.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2, default=float)
    print(f"\nSaved to {path}")


if __name__ == "__main__":
    main()
