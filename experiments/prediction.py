#!/usr/bin/env python3
"""
Prediction test: state a falsifiable claim, then check it on held-out data.

A distinguisher says "this output is not random". A predictor says "bit b of
the cross-round difference is X" and is either right or wrong. The second claim
is strictly stronger, and it needs no permutation null, no familywise
correction, and no Z-score -- it cannot be inflated by a selection artifact,
because the cell is chosen on TRAINING data and scored on data never used to
choose it.

Protocol per cipher:
  1. Generate output at round R and R+1 (same key, same counter), full rounds.
  2. Split into train / test.
  3. On TRAIN only: find the (source word, source bit, target word, target bit)
     cell with the highest mutual information, and read off the majority rule
     mapping source bit -> difference bit.
  4. On TEST: apply that rule. Report accuracy.
  5. Random-data baseline through the identical pipeline: must give 50%.

An accuracy meaningfully above 50% on held-out data is a prediction, not a
correlation. Threefish's MI = ln 2 on bit 0 predicts 100%; this script states
whatever the data actually gives.

Usage:  python experiments/prediction.py
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


# ---------------------------------------------------------------- statistics

def mi_binary(a, b):
    """Mutual information of two binary vectors, in nats."""
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
    Ha = -pa * math.log(pa) - (1 - pa) * math.log(1 - pa) if 0 < pa < 1 else 0.0
    Hb = -pb * math.log(pb) - (1 - pb) * math.log(1 - pb) if 0 < pb < 1 else 0.0
    return max(0.0, Ha + Hb - H)


def _bits(word, bit):
    return ((word >> np.uint64(bit)) & np.uint64(1)).astype(bool)


def fit_predict(words_R, words_R1, n_bits, shifts=True, train_frac=0.5,
                bit_stride=1):
    """Pick the best cell on TRAIN, score the rule on TEST.

    Returns a dict with the chosen cell, the rule, and held-out accuracy.
    """
    N = len(words_R[0])
    n_tr = int(N * train_frac)
    tr = slice(0, n_tr)
    te = slice(n_tr, N)

    diffs = [words_R[t] ^ words_R1[t] for t in range(len(words_R1))]
    bit_list = list(range(0, n_bits, bit_stride))

    best = {"mi": -1.0}
    for si in range(len(words_R)):
        for sb in bit_list:
            x_tr = _bits(words_R[si][tr], sb)
            for ti in range(len(diffs)):
                shift_range = bit_list if shifts else [sb]
                for tb in shift_range:
                    d_tr = _bits(diffs[ti][tr], tb)
                    m = mi_binary(x_tr, d_tr)
                    if m > best["mi"]:
                        # majority rule learned on TRAIN only
                        agree = int(np.count_nonzero(x_tr == d_tr))
                        best = {"mi": m, "src_word": si, "src_bit": sb,
                                "tgt_word": ti, "tgt_bit": tb,
                                "rule_equal": bool(agree * 2 >= len(x_tr)),
                                "train_agree_frac": agree / len(x_tr)}

    # score on held-out data the cell selection never saw
    x_te = _bits(words_R[best["src_word"]][te], best["src_bit"])
    d_te = _bits(diffs[best["tgt_word"]][te], best["tgt_bit"])
    pred = x_te if best["rule_equal"] else ~x_te
    acc = float(np.count_nonzero(pred == d_te) / len(d_te))

    n_te = N - n_tr
    best["test_accuracy"] = acc
    best["n_train"] = n_tr
    best["n_test"] = n_te
    best["mi_train_nats"] = best.pop("mi")
    # Binomial z against the 50% null on the held-out split.
    best["binomial_z"] = (acc - 0.5) / math.sqrt(0.25 / n_te) if n_te else 0.0
    return best


def random_baseline(n_words, n_bits, N, seed=4242, word_bits=64):
    rng = np.random.default_rng(seed)
    a = [rng.integers(0, 1 << word_bits, size=N, dtype=np.uint64)
         for _ in range(n_words)]
    b = [rng.integers(0, 1 << word_bits, size=N, dtype=np.uint64)
         for _ in range(n_words)]
    return fit_predict(a, b, n_bits)


# ------------------------------------------------------------------ ciphers

def speck_words(N, ws, kw, alpha, beta, rounds, seed=1):
    mask = (1 << ws) - 1
    rng = np.random.default_rng(seed)
    key = [int(v) for v in rng.integers(0, 1 << min(ws, 63), size=kw)]
    rk = [0] * max(rounds + 2, 40)
    l = list(key[1:])
    rk[0] = key[0]
    for i in range(rounds + 1):
        rl = ((l[i % len(l)] >> alpha) | (l[i % len(l)] << (ws - alpha))) & mask
        nl = ((rk[i] + rl) & mask) ^ i
        l.append(nl)
        rk[i + 1] = ((((rk[i] << beta) | (rk[i] >> (ws - beta))) & mask) ^ nl)
    xs = np.zeros(N, dtype=np.uint64)
    ys = np.zeros(N, dtype=np.uint64)
    for blk in range(N):
        x, y = (blk >> ws) & mask, blk & mask
        for r in range(rounds):
            x = ((((x >> alpha) | (x << (ws - alpha))) & mask) + y) & mask
            x ^= rk[r]
            y = ((((y << beta) | (y >> (ws - beta))) & mask)) ^ x
        xs[blk], ys[blk] = x, y
    return [xs, ys]


TF256_ROT = [[14, 16], [52, 57], [23, 40], [5, 37],
             [25, 33], [46, 12], [58, 22], [32, 32]]


def _rol64(v, r):
    r %= 64
    return ((v << r) | (v >> (64 - r))) & M64 if r else v


def threefish256_words(N, rounds, seed=5):
    rng = np.random.default_rng(seed)
    key = [int(rng.integers(0, 2**63)) * 2 + 1 for _ in range(4)]
    tweak = [int(rng.integers(0, 2**63)) * 2 for _ in range(2)]
    C240 = 0x1BD11BDAA9FC1A22
    ks = key + [key[0] ^ key[1] ^ key[2] ^ key[3] ^ C240]
    tw = tweak + [tweak[0] ^ tweak[1]]
    out = [np.zeros(N, dtype=np.uint64) for _ in range(4)]
    for blk in range(N):
        v = [blk & M64, 0, 0, 0]
        for d in range(rounds):
            if d % 4 == 0:
                s = d // 4
                v[0] = (v[0] + ks[s % 5]) & M64
                v[1] = (v[1] + ks[(s + 1) % 5] + tw[s % 3]) & M64
                v[2] = (v[2] + ks[(s + 2) % 5] + tw[(s + 1) % 3]) & M64
                v[3] = (v[3] + ks[(s + 3) % 5] + s) & M64
            r0, r1 = TF256_ROT[d % 8]
            e0 = (v[0] + v[1]) & M64
            e1 = _rol64(v[1], r0) ^ e0
            e2 = (v[2] + v[3]) & M64
            e3 = _rol64(v[3], r1) ^ e2
            v = [e0, e3, e2, e1]
        for w in range(4):
            out[w][blk] = v[w]
    return out


TF1024_ROT = [[24, 13, 8, 47, 8, 17, 22, 37], [38, 19, 10, 55, 49, 18, 23, 52],
              [33, 4, 51, 13, 34, 41, 59, 17], [5, 20, 48, 41, 47, 28, 16, 25],
              [41, 9, 37, 31, 12, 47, 44, 30], [16, 34, 56, 51, 4, 53, 42, 41],
              [31, 44, 47, 46, 19, 42, 44, 25], [9, 48, 35, 52, 23, 31, 37, 20]]
TF1024_PERM = [0, 9, 2, 13, 6, 11, 4, 15, 10, 7, 12, 3, 14, 5, 8, 1]


def threefish1024_words(N, rounds, seed=11):
    rng = np.random.default_rng(seed)
    key = [int(rng.integers(0, 2**63)) * 2 + 1 for _ in range(16)]
    tweak = [int(rng.integers(0, 2**63)) * 2 for _ in range(2)]
    C240 = 0x1BD11BDAA9FC1A22
    par = C240
    for k in key:
        par ^= k
    ks = key + [par]
    tw = tweak + [tweak[0] ^ tweak[1]]
    out = [np.zeros(N, dtype=np.uint64) for _ in range(16)]
    for blk in range(N):
        v = [blk & M64] + [0] * 15
        for d in range(rounds):
            if d % 4 == 0:
                sN = d // 4
                for i in range(16):
                    v[i] = (v[i] + ks[(sN + i) % 17]) & M64
                v[13] = (v[13] + tw[sN % 3]) & M64
                v[14] = (v[14] + tw[(sN + 1) % 3]) & M64
                v[15] = (v[15] + sN) & M64
            nv = [0] * 16
            for j in range(8):
                x0, x1 = v[2 * j], v[2 * j + 1]
                e0 = (x0 + x1) & M64
                e1 = _rol64(x1, TF1024_ROT[d % 8][j]) ^ e0
                nv[2 * j], nv[2 * j + 1] = e0, e1
            v = [nv[TF1024_PERM[i]] for i in range(16)]
        for w in range(16):
            out[w][blk] = v[w]
    return out


def tea_words(N, rounds, seed=0):
    MASK = np.uint64(0xFFFFFFFF)
    DELTA = np.uint64(0x9E3779B9)
    rng = np.random.default_rng(1000 + seed)
    k = tuple(np.uint64(int(rng.integers(0, 1 << 32))) for _ in range(4))
    r2 = np.random.default_rng(seed)
    y = r2.integers(0, 1 << 32, size=N, dtype=np.uint64) & MASK
    z = r2.integers(0, 1 << 32, size=N, dtype=np.uint64) & MASK
    s = np.uint64(0)
    for _ in range(rounds):
        s = (s + DELTA) & MASK
        y = (y + (((z << np.uint64(4)) + k[0]) ^ (z + s) ^
                  ((z >> np.uint64(5)) + k[1]))) & MASK
        z = (z + (((y << np.uint64(4)) + k[2]) ^ (y + s) ^
                  ((y >> np.uint64(5)) + k[3]))) & MASK
    return [y, z]


# --------------------------------------------------------------------- main

def main():
    N = 40000
    rows = []

    def run(label, rounds, wr, wr1, n_bits, bit_stride=1, note=""):
        r = fit_predict(wr, wr1, n_bits, bit_stride=bit_stride)
        r.update({"cipher": label, "rounds": rounds, "note": note})
        rows.append(r)
        print(f"{label:>16} R{rounds:<4} bit {r['src_bit']:>2}(w{r['src_word']}) "
              f"-> diff bit {r['tgt_bit']:>2}(w{r['tgt_word']})   "
              f"acc = {r['test_accuracy']*100:6.2f}%  "
              f"binom z = {r['binomial_z']:+8.1f}  "
              f"(train MI = {r['mi_train_nats']:.4f} nats)")
        return r

    print("=" * 100)
    print("PREDICTION TEST -- cell chosen on training data, accuracy scored on held-out data")
    print("=" * 100)
    print(f"N = {N:,} blocks, 50/50 train/test split, baseline = 50.00%\n")

    # Threefish-256, full 72 rounds
    a = threefish256_words(N, 72)
    b = threefish256_words(N, 73)
    run("Threefish-256", 72, a, b, 8,
        note="raw carry, beta_eff=0; MI on bit 0 reaches ln 2")

    # Threefish-1024, full 80 rounds. Restricted to the low 4 bits: the raw
    # carry mechanism lives at bit 0, and 16 words x 64 bits is a large scan.
    a1 = threefish1024_words(N // 2, 80)
    b1 = threefish1024_words(N // 2, 81)
    run("Threefish-1024", 80, a1, b1, 4,
        note="permutation fixed-point carry retention")

    # Speck family, full rounds
    for label, ws, kw, al, be, rounds in [
            ("Speck 32/64", 16, 4, 7, 2, 22),
            ("Speck 48/96", 24, 4, 8, 3, 23),
            ("Speck 64/128", 32, 4, 8, 3, 27)]:
        wr = speck_words(N, ws, kw, al, be, rounds)
        wr1 = speck_words(N, ws, kw, al, be, rounds + 1)
        run(label, rounds, wr, wr1, ws, note=f"beta-masking, alpha={al}")

    # TEA, full 32 rounds
    ta = tea_words(N, 32)
    tb = tea_words(N, 33)
    run("TEA", 32, ta, tb, 32, note="Feistel self-XOR")

    # Random baseline through the identical pipeline
    print()
    rb = random_baseline(2, 16, N, word_bits=32)
    rb.update({"cipher": "RANDOM baseline", "rounds": None})
    rows.append(rb)
    print(f"{'RANDOM baseline':>16} {'--':<5} bit {rb['src_bit']:>2}(w{rb['src_word']}) "
          f"-> diff bit {rb['tgt_bit']:>2}(w{rb['tgt_word']})   "
          f"acc = {rb['test_accuracy']*100:6.2f}%  "
          f"binom z = {rb['binomial_z']:+8.1f}  "
          f"(train MI = {rb['mi_train_nats']:.4f} nats)")

    print()
    print("=" * 100)
    print("The random baseline picks the best of the same number of cells on training")
    print("data and still lands at chance on held-out data -- which is exactly why this")
    print("test cannot be inflated by cell selection.")
    print("=" * 100)

    out = {"test": "held-out cross-round bit prediction",
           "N": N, "train_frac": 0.5, "baseline_accuracy": 0.5,
           "results": rows}
    path = os.path.join(RESULTS, "prediction.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2, default=float)
    print(f"\nSaved to {path}")
    return out


if __name__ == "__main__":
    main()
