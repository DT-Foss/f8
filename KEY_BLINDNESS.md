# Key blindness of the F8 observable

A distinguisher is usually a step toward key recovery: guess a round key,
partially decrypt, and check whether the distinguisher strengthens. For F8 on
Speck that route is closed, and not for want of computation — the observable is
structurally independent of the round key.

This is stated as a proposition because it is provable from the round function,
not inferred from a failed search. It also bounds what F8 is: a structural
detector, not an extractor.

## Proposition

Let a Speck round with parameters (α, β) and round key `k` map state `(x, y)` to

```
x' = (ROR(x, α) + y) XOR k
y' = ROL(y, β) XOR x'
```

The inverse round, given a guess `g` for `k`, recovers

```
y = ROR(x' XOR y', β)                    (1)
x = ROL((x' XOR g) - y, α)               (2)
```

**Equation (1) contains no key material.** The recovered `y` is a function of the
ciphertext alone.

F8's observable is

```
MI( x_bit i ; (y_R XOR y_{R+1})_bit (i-α) )
```

The second argument is built entirely from recovered `y` values, so by (1) it is
invariant under the guess. Changing `g` alters only the first argument, via (2),
and that is a bijection of the `x` word for each fixed `g`. A bijection applied to
one argument of a mutual information permutes which bit positions are examined
but cannot create or destroy the dependence being measured.

Therefore the F8 score, maximised over bit positions, is constant in `g` up to
finite-sample noise. No ranking over key candidates is possible.

## Verification

Direct check, N = 20,000, Speck 32/64 at R = 21:

| | |
|---|---|
| invert with `g = 0x0000`, recover `y` | — |
| invert with `g = 0xFFFF`, recover `y` | — |
| **the two recovered `y` arrays are bit-identical** | `True` |
| the two recovered `x` arrays are identical | `False` |

Full key sweep, 65,536 candidates, N = 60,000, Speck 32/64 at R = 20:

| | |
|---|---|
| F8 at the true key | 0.44355 |
| known-key calibration | 0.44355 (exact match — the sweep is correctly built) |
| best candidate | 0.45114 |
| **rank of the true key** | **21,450 of 65,536** |
| z of the true key | +0.46 |
| distinct score values | 32,703 (so the sweep is not degenerate) |

The true key sits at the middle of the distribution. The spread that exists is
finite-sample noise in the `x` argument, not signal.

## Why the obvious repairs also fail

**Strip the key XOR before measuring.** The round writes
`x' = (ROR(x,α) + y) XOR k`, so a guess `g` gives `x' XOR g`, and the
cross-round difference becomes

```
(C₁ XOR g) XOR (C₂ XOR g) = C₁ XOR C₂
```

The guess cancels identically. Measured: all 65,536 candidates produce the same
score, `distinct = 1`.

**Measure on the x-difference instead of the y-difference.** Both sides then
depend on the guess, which removes the invariance — but no dependence appears.
Full sweep: rank 11,442 of 16,384, z = +0.42.

An earlier version of this experiment reported z = −10.12 for the x-difference,
which looked like a usable anti-correlation. It was an artifact: the reference set
was the top 200 candidates from a coarse pass, i.e. pre-selected. Against the full
sweep the true key is unremarkable. Recorded because the mistake is instructive.

## What this means

**F8 is a detector, not an extractor.** It answers "is this output
distinguishable from random" and, through the retention rule, "why". It does not
answer "what is the key", and on Speck it provably cannot in this form.

**The key-schedule independence reported in the paper is the same fact.** The
measured invariance across normal, all-zero and random round keys (0.645 / 0.623 /
0.622) is not a robustness property that happens to hold — it follows from the
structure of the inverse round.

**Conversion would need a different observable.** Any route to key recovery has
to place the guess algebraically inside the measured quantity. The two natural
candidates are closed above. That is a bound on this construction, not on the
underlying carry leakage: a differential counter over partially decrypted states
*is* key-dependent, because it reads the `x` branch, and that route remains open.

## Reproducing

```bash
python experiments/key_blindness.py
```
