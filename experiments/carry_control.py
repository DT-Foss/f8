#!/usr/bin/env python3
"""
Carry control: does the signal actually come from the carry chain?

F8's thesis is that modular addition leaks its carry chain across the round
boundary. That thesis makes a sharp, falsifiable prediction:

    replace `+` with `^` in the round function, leave everything else
    identical, and the signal must DISAPPEAR.

XOR is addition without carries. If a measured signal survives -- or grows --
when addition is replaced by XOR, then whatever produced it was not the carry
chain. It is the topology of the round function: a state word that meets a
transform of itself across the round boundary correlates with its own
difference regardless of which operation produced it.

This control is cheap and it should have been in the repository from the start.
Applied retroactively it kills two previously published results.

RESULTS (N = 20,000, best cell over bits 1..7, bit 0 excluded as an identity):

    cipher            MI with ADD    MI with XOR    verdict
    Speck 32/64 R22      0.034261       0.000001    carry-dependent
    TEA R32              0.000778       0.002578    topology
    Threefish-256 R72    0.134574       0.693147    topology
    Threefish-1024 R80   (same shape)   (same)      topology

Speck's signal vanishes without carries -- a factor of 34,000. That is a real
carry leak, and it is what the beta-masking mechanism describes.

Threefish's signal is STRONGER without carries. The MIX function computes
e0 = x0 + x1, e1 = ROL(x1,r) XOR e0 -- so e0 is contained in e1 by construction.
Observing e1 against its own cross-round difference finds a correlation that was
built in, and modular addition actually damps it relative to XOR. The Threefish
result was never a carry distinguisher.

Usage:  python experiments/carry_control.py
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(REPO, "results")
os.makedirs(RESULTS, exist_ok=True)

M64 = (1 << 64) - 1
MASK32 = np.uint64(0xFFFFFFFF)
DELTA = np.uint64(0x9E3779B9)


def mi_binary(a, b):
    n = len(a)
    n11 = int(np.count_nonzero(a & b))
    n10 = int(np.count_nonzero(a & ~b))
    n01 = int(np.count_nonzero(~a & b))
    n00 = n - n11 - n10 - n01
    H = 0.0
    for c in (n00, n01, n10, n11):
        if c > 0:
            p = c / n
            H -= p * math.log(p)
    pa = (n10 + n11) / n
    pb = (n01 + n11) / n
    Ha = -pa*math.log(pa) - (1-pa)*math.log(1-pa) if 0 < pa < 1 else 0.0
    Hb = -pb*math.log(pb) - (1-pb)*math.log(1-pb) if 0 < pb < 1 else 0.0
    return max(0.0, Ha + Hb - H)


def _bit(w, b):
    return ((w >> np.uint64(b)) & np.uint64(1)).astype(bool)


def best_mi(a, b, n_bits, lo=1):
    """Best cell over bits lo..n_bits-1. bit 0 excluded by default: it is an
    algebraic identity, (u+v)[0] = u[0] XOR v[0]."""
    best = 0.0
    for si in range(len(a)):
        for sb in range(lo, n_bits):
            xb = _bit(a[si], sb)
            for ti in range(len(b)):
                d = a[ti] ^ b[ti]
                for tb in range(lo, n_bits):
                    m = mi_binary(xb, _bit(d, tb))
                    if m > best:
                        best = m
    return best


# ------------------------------------------------------------------ ciphers

def speck(N, rounds, use_add=True, ws=16, al=7, be=2, seed=1):
    mask = (1 << ws) - 1
    rng = np.random.default_rng(seed)
    key = [int(v) for v in rng.integers(0, 1 << ws, size=4)]
    rk = [0] * max(rounds + 2, 40)
    l = list(key[1:])
    rk[0] = key[0]
    for i in range(rounds + 1):
        rl = ((l[i % len(l)] >> al) | (l[i % len(l)] << (ws - al))) & mask
        nl = ((rk[i] + rl) & mask) ^ i
        l.append(nl)
        rk[i + 1] = ((((rk[i] << be) | (rk[i] >> (ws - be))) & mask) ^ nl)
    xs = np.zeros(N, dtype=np.uint64)
    ys = np.zeros(N, dtype=np.uint64)
    for blk in range(N):
        x, y = (blk >> ws) & mask, blk & mask
        for r in range(rounds):
            rx = ((x >> al) | (x << (ws - al))) & mask
            x = ((rx + y) & mask) if use_add else (rx ^ y)
            x ^= rk[r]
            y = ((((y << be) | (y >> (ws - be))) & mask)) ^ x
        xs[blk], ys[blk] = x, y
    return [xs, ys]


def tea(N, rounds, use_add=True, seed=0):
    rng = np.random.default_rng(1000 + seed)
    k = tuple(np.uint64(int(rng.integers(0, 1 << 32))) for _ in range(4))
    r2 = np.random.default_rng(seed)
    y = r2.integers(0, 1 << 32, size=N, dtype=np.uint64) & MASK32
    z = r2.integers(0, 1 << 32, size=N, dtype=np.uint64) & MASK32
    s = np.uint64(0)
    for _ in range(rounds):
        s = (s + DELTA) & MASK32
        t1 = (((z << np.uint64(4)) + k[0]) ^ (z + s) ^
              ((z >> np.uint64(5)) + k[1])) & MASK32
        y = ((y + t1) & MASK32) if use_add else ((y ^ t1) & MASK32)
        t2 = (((y << np.uint64(4)) + k[2]) ^ (y + s) ^
              ((y >> np.uint64(5)) + k[3])) & MASK32
        z = ((z + t2) & MASK32) if use_add else ((z ^ t2) & MASK32)
    return [y, z]


def threefish_mix(N, rounds, use_add=True, seed=3):
    """Threefish-256 MIX + permutation topology, unkeyed. The key schedule,
    tweak and the eight rotation constants were ablated separately and change
    nothing (0.128-0.136 across every combination)."""
    def rol(v, r):
        r %= 64
        return ((v << np.uint64(r)) | (v >> np.uint64(64 - r))) if r else v
    rng = np.random.default_rng(seed)
    ws = [rng.integers(0, 1 << 62, N, dtype=np.uint64) for _ in range(4)]
    for _ in range(rounds):
        if use_add:
            e0 = (ws[0] + ws[1]) & np.uint64(M64)
            e2 = (ws[2] + ws[3]) & np.uint64(M64)
        else:
            e0 = ws[0] ^ ws[1]
            e2 = ws[2] ^ ws[3]
        e1 = (rol(ws[1], 14) ^ e0) & np.uint64(M64)
        e3 = (rol(ws[3], 16) ^ e2) & np.uint64(M64)
        ws = [e0, e3, e2, e1]        # Threefish-256 permutation [0,3,2,1]
    return ws


def main():
    N = 20000
    print("=" * 92)
    print("CARRY CONTROL -- replace modular addition with XOR, change nothing else")
    print("   A carry leak MUST die when the carries are removed.")
    print("=" * 92)
    print(f"{'cipher':>20} {'MI with ADD':>13} {'MI with XOR':>13} {'ratio':>10}  verdict")

    cases = [
        ("Speck 32/64 R22", lambda ua: (speck(N, 22, ua), speck(N, 23, ua)), 16),
        ("TEA R32", lambda ua: (tea(N, 32, ua), tea(N, 33, ua)), 32),
        ("Threefish MIX R72",
         lambda ua: (threefish_mix(N, 72, ua), threefish_mix(N, 73, ua)), 8),
    ]
    rows = []
    for label, gen, nb in cases:
        a, b = gen(True)
        m_add = best_mi(a, b, nb)
        a, b = gen(False)
        m_xor = best_mi(a, b, nb)
        carry_dependent = m_xor < 0.5 * m_add
        verdict = "CARRY-DEPENDENT" if carry_dependent else "topology, not carry"
        ratio = m_add / m_xor if m_xor > 1e-12 else float("inf")
        print(f"{label:>20} {m_add:>13.6f} {m_xor:>13.6f} {ratio:>10.1f}  {verdict}")
        rows.append(dict(cipher=label, mi_add=m_add, mi_xor=m_xor,
                         carry_dependent=bool(carry_dependent), verdict=verdict))

    print()
    print("  Speck's signal vanishes without carries (factor ~34,000): a real carry")
    print("  leak, exactly as the beta-masking mechanism describes.")
    print()
    print("  Threefish and TEA measure STRONGER with XOR than with addition, so the")
    print("  carry chain is not their source. In the Threefish MIX,")
    print("      e0 = x0 + x1,   e1 = ROL(x1, r) XOR e0")
    print("  puts e0 inside e1 by construction; observing e1 against its own")
    print("  cross-round difference recovers a correlation that was built in.")

    path = os.path.join(RESULTS, "carry_control.json")
    with open(path, "w") as f:
        json.dump({"N": N, "bit0_excluded": True, "results": rows}, f,
                  indent=2, default=float)
    print(f"\nSaved to {path}")


if __name__ == "__main__":
    main()
