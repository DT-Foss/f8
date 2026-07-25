#!/usr/bin/env python3
"""
The permutation-retention rule, stated as a prediction and tested as one.

RULE
    A cross-round leak exists iff an addition output stays in the MIX pair that
    produced it.

    For a round computing  e_add = w[2k] + w[2k+1],
                           e_xor = ROL(w[2k+1], r) XOR e_add
    followed by a word permutation P, the condition is:
        e_add from pair k lands in slot 2k or 2k+1.

The rule was derived by exhaustive search over all 24 four-word permutations,
then tested on constructions and ciphers it was never fitted to.

VALIDATION
    all 24 four-word permutations                     24/24
    14 random six-word permutations (unseen shape)    14/14
    Threefish-512, Salsa20, Alzette (real ciphers)      3/3
                                                    -------
                                                     41/41

Leaking configurations measure MI ~ 0.12-0.14; non-leaking ones 0.0002-0.0007,
the noise floor. There is no middle ground.

WHAT THE RULE EXPLAINS
    Threefish-256  perm [0,3,2,1]      slots 0,2 retain their sums   LEAKS
    Threefish-512  perm [2,1,4,7,6,5,0,3]  no pair retains its sum   IMMUNE
    Threefish-1024 perm has fixed points                              LEAKS

    That Threefish-512 -- the middle size -- is the immune one had been an open
    puzzle. The rule answers it from the specification, without measuring.

WHAT THE RULE DOES NOT CLAIM
    It predicts the leak in a round function plus word permutation. A linear
    diffusion layer on top can still remove it entirely:

        Alzette (SPARKLE ARX-box) alone     MI = 0.1332   leaks
        full SPARKLE384 permutation         MI = 0.0004   immune, from step 1

    This is the same relationship SPARX shows: the ARX-box leaks in isolation
    and the linear inter-round layer is the whole protection. Alzette was
    previously classified immune on the basis of the full permutation; the
    primitive itself is not.

Usage:  python experiments/retention_rule.py
"""
import itertools
import json
import math
import os
import random

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(REPO, "results")
os.makedirs(RESULTS, exist_ok=True)

M64 = (1 << 64) - 1
M32 = np.uint64(0xFFFFFFFF)
N = 12000


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


def _bit(w, b):
    return ((w >> np.uint64(b)) & np.uint64(1)).astype(bool)


def best_mi(a, b, nb=6, lo=1):
    """Best cell over bits lo..nb-1. bit 0 excluded: algebraic identity."""
    best = 0.0
    for si in range(len(a)):
        for sb in range(lo, nb):
            xb = _bit(a[si], sb)
            for ti in range(len(b)):
                d = a[ti] ^ b[ti]
                for tb in range(lo, nb):
                    m = mi(xb, _bit(d, tb))
                    if m > best:
                        best = m
    return best


def rol64(v, r):
    r %= 64
    return ((v << np.uint64(r)) | (v >> np.uint64(64 - r))) if r else v


def rol32(v, r):
    r %= 32
    return (((v << np.uint64(r)) | (v >> np.uint64(32 - r))) & M32) if r else v


def retention_rule(perm):
    """THE RULE. perm[i] = which pre-permutation slot lands in slot i.
    Pre-permutation layout is [add_0, xor_0, add_1, xor_1, ...]."""
    npairs = len(perm) // 2
    return any(perm[2*k] == 2*k or perm[2*k+1] == 2*k for k in range(npairs))


def mix_construction(rounds, perm, n_words=4, seed=3):
    rng = np.random.default_rng(seed)
    w = [rng.integers(0, 1 << 62, N, dtype=np.uint64) for _ in range(n_words)]
    for _ in range(rounds):
        nw = []
        for k in range(n_words // 2):
            a, b = w[2*k], w[2*k+1]
            e_add = (a + b) & np.uint64(M64)
            e_xor = (rol64(b, 14 + k) ^ e_add) & np.uint64(M64)
            nw.extend([e_add, e_xor])
        w = [nw[perm[i]] for i in range(n_words)]
    return w


# ------------------------------------------------------------- real ciphers
TF512_PERM = [2, 1, 4, 7, 6, 5, 0, 3]
TF512_ROT = [[46, 36, 19, 37], [33, 27, 14, 42], [17, 49, 36, 39],
             [44, 9, 54, 56], [39, 30, 34, 24], [13, 50, 10, 17],
             [25, 29, 39, 43], [8, 35, 56, 22]]


def threefish512(rounds, seed=5):
    rng = np.random.default_rng(seed)
    w = [rng.integers(0, 1 << 62, N, dtype=np.uint64) for _ in range(8)]
    for d in range(rounds):
        nw = []
        for k in range(4):
            a, b = w[2*k], w[2*k+1]
            e0 = (a + b) & np.uint64(M64)
            e1 = (rol64(b, TF512_ROT[d % 8][k]) ^ e0) & np.uint64(M64)
            nw.extend([e0, e1])
        w = [nw[TF512_PERM[i]] for i in range(8)]
    return w


ALZ_ROT = [(31, 24), (17, 17), (0, 31), (24, 16)]


def alzette(rounds, c=0xB7E15162, seed=9):
    rng = np.random.default_rng(seed)
    x = rng.integers(0, 1 << 32, N, dtype=np.uint64) & M32
    y = rng.integers(0, 1 << 32, N, dtype=np.uint64) & M32
    for r in range(rounds):
        ra, rb = ALZ_ROT[r % 4]
        x = (x + rol32(y, ra)) & M32
        y = y ^ rol32(x, rb)
        x = x ^ np.uint64(c)
    return [x, y]


def salsa20(rounds, seed=7):
    rng = np.random.default_rng(seed)
    st = [rng.integers(0, 1 << 32, N, dtype=np.uint64) & M32 for _ in range(16)]
    col = [(0,4,8,12), (5,9,13,1), (10,14,2,6), (15,3,7,11)]
    row = [(0,1,2,3), (5,6,7,4), (10,11,8,9), (15,12,13,14)]
    for r in range(rounds):
        for (ia, ib, ic, idd) in (col if r % 2 == 0 else row):
            a, b, c, d = st[ia], st[ib], st[ic], st[idd]
            b = b ^ rol32((a + d) & M32, 7)
            c = c ^ rol32((b + a) & M32, 9)
            d = d ^ rol32((c + b) & M32, 13)
            a = a ^ rol32((d + c) & M32, 18)
            st[ia], st[ib], st[ic], st[idd] = a, b, c, d
    return st


def main():
    out = {"rule": "leak iff an addition output stays in the pair that produced it"}

    print("=" * 92)
    print("PART 1 -- all 24 four-word permutations (rule derived here)")
    print("=" * 92)
    ok = tot = 0
    for perm in itertools.permutations(range(4)):
        pred = retention_rule(perm)
        m = best_mi(mix_construction(72, perm), mix_construction(73, perm))
        tot += 1; ok += (pred == (m > 0.01))
    print(f"  {ok}/{tot} correct")
    out["four_word"] = {"correct": ok, "total": tot}

    print()
    print("=" * 92)
    print("PART 2 -- six-word permutations (shape never used to derive the rule)")
    print("=" * 92)
    random.seed(11)
    perms = random.sample(list(itertools.permutations(range(6))), 14)
    ok6 = 0
    for perm in perms:
        pred = retention_rule(perm)
        m = best_mi(mix_construction(48, perm, n_words=6),
                    mix_construction(49, perm, n_words=6), nb=6)
        ok6 += (pred == (m > 0.01))
    print(f"  {ok6}/{len(perms)} correct on an unseen shape")
    out["six_word"] = {"correct": ok6, "total": len(perms)}

    print()
    print("=" * 92)
    print("PART 3 -- real ciphers, prediction stated from the specification first")
    print("=" * 92)
    cases = []

    pred = retention_rule(TF512_PERM)
    m = best_mi(threefish512(72), threefish512(73))
    cases.append(("Threefish-512", 72, pred, m))
    print(f"  Threefish-512  perm {TF512_PERM}")
    print(f"    predicted {'LEAK' if pred else 'NO LEAK'} -> measured MI = {m:.6f}  "
          f"{'MATCH' if pred == (m > 0.01) else 'MISMATCH'}")

    m = best_mi(salsa20(20), salsa20(21))
    cases.append(("Salsa20", 20, False, m))
    print(f"  Salsa20        every sum is consumed immediately by an XOR of another word")
    print(f"    predicted NO LEAK -> measured MI = {m:.6f}  "
          f"{'MATCH' if not (m > 0.01) else 'MISMATCH'}")

    m = best_mi(alzette(16), alzette(17), nb=8)
    cases.append(("Alzette (SPARKLE ARX-box)", 16, True, m))
    print(f"  Alzette        x = x + ROL(y,a) retains the sum in x")
    print(f"    predicted LEAK -> measured MI = {m:.6f}  "
          f"{'MATCH' if m > 0.01 else 'MISMATCH'}")

    ok3 = sum(1 for _, _, p, m in cases if p == (m > 0.01))
    print(f"\n  {ok3}/{len(cases)} correct")
    out["real_ciphers"] = [dict(cipher=c, rounds=r, predicted=bool(p),
                                mi=float(m), match=bool(p == (m > 0.01)))
                           for c, r, p, m in cases]

    total_ok = ok + ok6 + ok3
    total = tot + len(perms) + len(cases)
    print()
    print("=" * 92)
    print(f"  TOTAL: {total_ok}/{total} predictions correct")
    print("=" * 92)
    out["total"] = {"correct": total_ok, "total": total}

    path = os.path.join(RESULTS, "retention_rule.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2, default=float)
    print(f"\nSaved to {path}")


if __name__ == "__main__":
    main()
