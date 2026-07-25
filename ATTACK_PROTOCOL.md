# Attack protocol

A distinguisher is not built in one or two attempts. A negative result after a
shallow pass is a statement about the attack, not about the cipher.

This file is a gate: **no cipher may be recorded as showing no signal until
every angle below has been tried and logged.**

## Why this exists

Threefish-256 measured `Z ≈ 2` on the first pass in this project — indistinguishable
from noise, and it would have been logged as immune. The observable was wrong.
Measured on the correct bit-pair, the same cipher at the same 72 rounds reaches

    MI = 0.693147 = ln 2

the information-theoretic maximum for a single bit. The strongest result in the
repository was one shallow pass away from being filed as a negative.

That is the failure mode this protocol exists to prevent.

## The eight angles

Every one of these must be run and recorded before a negative is logged.

**1. All cells.** Scan every (source word, target word, bit) triple. Not just
bit *i* against bit *i*.

**2. All diagonal shifts.** Test bit *i* against bit *(i − s)* for every shift
*s*. This is not optional: Speck 32/64 at shift 0 gives MI = 0.000188, pure
noise. At shift 7 — its rotation parameter α — the same data gives MI = 0.63.
Searching only the unshifted diagonal misses the entire Speck family.

**3. Low bits separately.** Raw carry exposure lives at bits 0–5 (effective
β = 0). A sum over all 64 bit positions dilutes a strong signal on bit 0 into
nothing. Threefish's ln 2 sits on bit 0 alone.

**4. Round distance 2 and 3.** Not only R → R+1. Some structures only couple
across a longer span, particularly ciphers whose round is really a half-round.

**5. Both directions.** Encrypt and decrypt. F8's signal in Speck is strictly
encrypt-only — the ratio exceeds 3,000:1 — so a decrypt-only test finds nothing
and proves nothing.

**6. Sample size to at least N = 200,000.** A weak-but-real signal is
indistinguishable from noise at N = 20,000. Push N before concluding, and pair
it with a random-data control at the same N (growth alone proves nothing —
see the statistics note in the README).

**7. Intermediate state.** Not only the final output, wherever the cipher's
structure suggests an internal observable. The output may be diffused while the
state one step earlier is not.

**8. The isolated primitive.** Run the round function or ARX-box on its own, in
addition to the full cipher. SPARX is the case in point: the ARX-box in
isolation gives Z ≈ +5,500, while the full cipher gives Z ≈ 0. The linear
inter-round layer is the entire protection — which is a finding, and it is
invisible if only the full cipher is tested.

## Logging a negative

Only after all eight angles produce nothing may a cipher be logged as showing no
signal — and the entry must state **the mechanism**, not just the number.

The standard is set by the existing closed negatives:

- **CHAM** — the word carousel `(A,B,C,D) → (B,C,D,Y)` structurally prevents
  the self-XOR compensation F8 requires. Algebraically proven, not merely
  unobserved.
- **XTEA** — the inner addition `((v1<<4) ^ (v1>>5)) + v1` destroys the
  correlation at 27 of 32 bit positions by itself; the outer addition damps the
  remaining 5 by a further 3,000–556,000×. Note that this explanation *corrected*
  an earlier, structurally-right-but-algebraically-incomplete one. Revising a
  negative's mechanism is part of the work.
- **SIMON** — bitwise AND in place of modular addition, so no carry chain
  exists to leak. The control that defines the null.

"No hit with the tools tried so far" is the honest phrasing. It is not the same
as "immune", and it is not the same as "given up".

## Before attacking a cipher

Check whether it already appears in the prior experiment set. Many of these
ciphers have been attacked before, some with results that predate the
familywise correction in `experiments/maxstat.py` — a borderline old result may
be either killed or confirmed by the corrected statistic, and both outcomes are
worth having.
