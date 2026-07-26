# Immune ciphers — mechanism-backed negative results

A repository that only shows hits looks like cherry-picking. These are the
ciphers this project attacked and could not break, each with the structural
reason, measured rather than asserted.

An entry here means "no signal found with the tools tried, and here is the
structural reason to expect none". It does not mean "proven secure".

## The condition

All entries below fail the same test:

> A leak exists iff a value returns to an observable position without being
> combined with foreign material on the way.

| Cipher | Rounds | Interposed between value and reuse | Ratio to null |
|---|:--:|---|:--:|
| ChaCha20 | 20 | foreign XOR (`d ^= a`, d unrelated to the sum) | ~1.0× |
| Salsa20 | 20 | XOR into a different word | ~1.0× |
| SHA-256 | 64 | `S0`/`S1` three-term XOR-rotations + `Ch`/`Maj` | 0.6× at R=64 |
| SHA-512 | 80 | same as SHA-256, 64-bit words | ~1.0× |
| BLAKE2s | 10 | foreign XOR — **and immune in isolation** | 0.5–0.9× |
| SKINNY-64 | 32 | MixColumns destroys the cell in the same round | 0.51–0.79× |
| Threefish-512 | 72 | permutation retains no addition output in its own pair | 0.0005 MI |
| SPARKLE384 | 11 | linear layer, from step 1 | 0.0004 MI |
| SIMON 32/64 | 32 | bitwise AND — no carry chain exists | ~1.0× |

## Notable cases

**BLAKE2s is the strongest negative here.** Ratio 0.5–0.9× at *every* round
count including R=1, and its G function measures 0.60–0.87× in isolation. SPARX
and SPARKLE leak at the primitive level and are rescued by their linear layer;
BLAKE2s needs no rescuing.

**Threefish-512 was an open puzzle.** Threefish-256 and Threefish-1024 both leak,
yet the middle size does not. The retention rule answers it from the
specification: permutation `[2,1,4,7,6,5,0,3]` returns no addition output to its
own MIX pair, for any of the four pairs. Predicted before measuring.

**SKINNY-64 is a rule failure, kept as one.** The cycle structure predicted a
candidate — 4 fixed points, all cycles ≤ 4, the same profile as PRESENT-80 and
GIFT-64 which both leak. It measured nothing. Diagnosing that produced the
transport requirement that unified the ARX and SPN forms of the rule. A rule that
never mispredicts has not been tested.

**SHA-2's protection is not what was expected.** The state rotation was the
obvious candidate and is not the answer: frozen it gives z=1.7, and with the
round constants and message schedule also removed, z=−1.2. The interposed
diffusion is the protection.

**An inversion in the SHA-256 message schedule.** There, modular addition
*protects*: with `+` the measurement is null (z=−1.0), with `^` it rises to
z=+35.1. The carry chain leaks only when its output is reused unfiltered.

## Not attacked far enough to claim anything

CHAM and XTEA are algebraically argued immune in the wider project but their
proofs are not reproduced in this repository yet. AES, Camellia, SM4, Serpent,
Twofish, Midori and Ascon have not been measured here at all.
