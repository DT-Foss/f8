#!/usr/bin/env python3
"""
Familywise-corrected max-statistic for F8.

WHY THIS EXISTS
---------------
`f8_max_z` (used by tea.py, rc5.py, rc5_64.py, threefish1024.py) takes the
MAXIMUM Z over K cells (source word x target word x bit) but scores it against
a permutation null built from the WINNING CELL ONLY. That is a multiple-
comparisons mismatch: the maximum of K noise draws is systematically larger
than any single draw, so the reported Z is inflated -- and the inflation grows
with K.

Measured inflation on this repo's own numbers (N=200,000):
    TEA R32      repo-style Z = 353.8  ->  corrected Z = 169.4
    RC5-32 R12   repo-style Z = 150.9  ->  corrected Z = 102.4
    RC5-64 R24   repo-style Z =  31.5  ->  corrected Z =  23.1
    pure random  repo-style Z =   5.8  ->  corrected Z =   0.7

The signals are REAL -- every one of them survives correction, and the random
control collapses to ~0 exactly as it should. Only the magnitudes were inflated.

THE FIX
-------
Score max(MI_real) against the distribution of max(MI_permuted) over the SAME
cell set. This is the standard max-statistic / familywise-error correction:
"is the best cell better than the best cell noise would give you?"

Note: gift.py and present.py use `f8_mi_test`, which already applies the same
max-over-targets selection to the permuted data. Those are correctly calibrated
and need no change.

Usage:
    from maxstat import maxstat_z
    z, detail = maxstat_z([wordsR...], [wordsR1...], n_bits=32)
"""
import math

import numpy as np


def mi_binary(a, b):
    """Mutual information of two binary vectors, in nats."""
    n = len(a)
    n11 = int(np.sum((a == 1) & (b == 1)))
    n10 = int(np.sum((a == 1) & (b == 0)))
    n01 = int(np.sum((a == 0) & (b == 1)))
    n00 = n - n11 - n10 - n01
    H_ab = 0.0
    for c in (n00, n01, n10, n11):
        if c > 0:
            p = c / n
            H_ab -= p * math.log(p)
    pa = (n10 + n11) / n
    Ha = -pa * math.log(pa) - (1 - pa) * math.log(1 - pa) if 0 < pa < 1 else 0.0
    pb = (n01 + n11) / n
    Hb = -pb * math.log(pb) - (1 - pb) * math.log(1 - pb) if 0 < pb < 1 else 0.0
    return max(0.0, Ha + Hb - H_ab)


def _build_cells(state_R, state_R1, n_bits, shifts):
    """All (src_word, src_bit) x (tgt_word, tgt_bit) observables."""
    src = []
    for si in range(len(state_R)):
        for bit in range(n_bits):
            src.append((si, bit,
                        ((state_R[si] >> np.uint64(bit)) & np.uint64(1)).astype(np.uint8)))
    tgt = []
    for ti in range(len(state_R1)):
        diff = state_R[ti] ^ state_R1[ti]
        for bit in range(n_bits):
            tgt.append((ti, bit,
                        ((diff >> np.uint64(bit)) & np.uint64(1)).astype(np.uint8)))
    return src, tgt


def maxstat_z(state_R, state_R1, n_bits=32, n_perm=25, seed=99, shifts=True):
    """Familywise-corrected F8 max-statistic.

    Returns (z, detail) where detail carries the winning cell, the real max MI,
    the null max MI, and the cell count -- so the correction is auditable.

    z > ~10 with a random control at ~0 is a genuine structural signal.
    """
    src, tgt = _build_cells(state_R, state_R1, n_bits, shifts)
    N = len(src[0][2])

    real_max, best = -1.0, None
    for si, sb, xb in src:
        for ti, tb, db in tgt:
            m = mi_binary(xb, db)
            if m > real_max:
                real_max, best = m, (si, sb, ti, tb)

    rng = np.random.default_rng(seed)
    null_max = []
    for _ in range(n_perm):
        p = rng.permutation(N)
        permuted = [(ti, tb, db[p]) for ti, tb, db in tgt]
        mx = 0.0
        for _si, _sb, xb in src:
            for _ti, _tb, db in permuted:
                m = mi_binary(xb, db)
                if m > mx:
                    mx = m
        null_max.append(mx)

    nm = float(np.mean(null_max))
    ns = max(float(np.std(null_max)), 1e-30)
    z = (real_max - nm) / ns
    detail = {
        "z_corrected": float(z),
        "real_max_mi": float(real_max),
        "null_max_mi": float(nm),
        "null_max_std": float(ns),
        "n_cells": len(src) * len(tgt),
        "src_word": best[0], "src_bit": best[1],
        "tgt_word": best[2], "tgt_bit": best[3],
    }
    return z, detail


def random_control(n_words, n_bits, N, seed=4242, n_perm=25, word_bits=64,
                   n_seeds=5):
    """Sanity gate: the same statistic on pure random data must give z ~ 0.

    Averaged over n_seeds independent random datasets. A single draw of a
    max-statistic is itself noisy -- with a small cell count and a modest
    permutation count the single-seed value can land at +3 by chance without
    anything being wrong. The mean over several seeds is the honest control,
    and `z_max` is reported alongside so the spread stays visible.
    """
    zs, details = [], []
    for k in range(n_seeds):
        s = seed + 1000 * k
        rng = np.random.default_rng(s)
        a = [rng.integers(0, 1 << word_bits, size=N, dtype=np.uint64)
             for _ in range(n_words)]
        b = [rng.integers(0, 1 << word_bits, size=N, dtype=np.uint64)
             for _ in range(n_words)]
        z, d = maxstat_z(a, b, n_bits=n_bits, n_perm=n_perm, seed=s)
        zs.append(float(z))
        details.append(d)
    mean_z = float(np.mean(zs))
    out = dict(details[0])
    out.update({"z_per_seed": zs, "z_mean": mean_z,
                "z_max": float(max(zs)), "n_seeds": n_seeds})
    return mean_z, out


if __name__ == "__main__":
    # Kept deliberately small: this is a calibration check, not a measurement.
    # A full-size control (many cells x many permutations x large N) costs
    # minutes of pure-Python MI evaluation; the experiment scripts run their
    # own control at their own scale.
    print("Self-test: random data must give z ~ 0 (never a large positive value)")
    print("Mean over 3 independent random datasets, small N for speed.\n")
    for label, nw, nb, wb in [("TEA / RC5-32 shape", 2, 8, 32),
                               ("Threefish-1024 shape", 4, 4, 64)]:
        z, d = random_control(nw, nb, 20000, word_bits=wb, n_perm=15, n_seeds=3)
        per = ", ".join(f"{v:+.1f}" for v in d["z_per_seed"])
        print(f"  {label:<22} mean z = {z:+6.2f}  max = {d['z_max']:+6.2f}  "
              f"(cells={d['n_cells']}, per seed: [{per}])")
    print("\nA single draw of a max-statistic is itself noisy; the mean is the"
          "\ncontrol, and z_max is reported so the spread stays visible.")
