# Reproducibility

## Environment this repository was measured on

| | |
|---|---|
| Hardware | Apple Mac mini M4, 16 GB |
| OS | macOS (Darwin 25.5.0) |
| Python | 3.12.7 |
| numpy | 1.26.4 |
| scipy | 1.17.1 |

Every script is deterministic: seeds are fixed in code, and repeated runs produce
byte-identical numeric output. This was checked — GIFT and PRESENT reproduce
their Z-scores and MI values exactly across runs, with only the recorded
wall-clock timings differing.

## Running it

```bash
pip install -e .
python reproduce.py           # everything, ~16 min on the machine above
```

Individual experiments:

```bash
python experiments/reproduce_core.py     # Speck 32/64, properties C1-C6
python experiments/speck_variants.py     # all four Speck variants
python experiments/threefish256.py       # Threefish-256, 72 rounds
python experiments/threefish1024.py      # Threefish-1024, 80 rounds
python experiments/gift.py               # GIFT-64 / GIFT-128
python experiments/present.py            # PRESENT-80
python experiments/tea.py                # TEA (UNCLEAR, see README)
python experiments/rc5.py                # RC5-32/12/16 (UNCLEAR)
python experiments/rc5_64.py             # RC5-64/24/24 (UNCLEAR)
```

Controls and rules:

```bash
python experiments/maxstat.py            # statistic self-test on random data
python experiments/carry_control.py      # ADD -> XOR: is it really carries?
python experiments/retention_rule.py     # the prediction rule, 41/41
python experiments/prediction.py         # held-out bit-prediction accuracy
```

`experiments/rc5_64.py` dominates the runtime: it sweeps six sample sizes up to
N=800,000. Skip it for a fast pass.

## Verification order

Nothing in this repository measures a cipher before checking the
implementation:

| Cipher | Checked against |
|---|---|
| Speck (all variants) | official NSA specification vectors, 7/7 |
| Threefish-256 / -1024 | Skein v1.3 reference KAT |
| GIFT-64 / GIFT-128 | `giftcipher/gift` published vectors |
| PRESENT-80 | CHES 2007 vectors |
| RC5-32 | RFC 2040 test vector |
| RC5-64 | draft-krovetz-rc6-rc5-vectors-00 |
| TEA | encrypt/decrypt round-trip + avalanche 31.9/64 |
| SHA-256 / SHA-512 | FIPS 180-4 vectors (immune set) |
| BLAKE2s | RFC 7693 vector (immune set) |

A script that fails its vector check raises and stops rather than reporting a
measurement.

## Statistical protocol

Established the hard way — see the artifact list in the README:

1. **Random-data control first.** Every statistic is run on pure noise before it
   is run on a cipher. A statistic that reports a signal on random data is void,
   and its results are discarded rather than interpreted.
2. **Familywise correction.** A maximum over K cells is scored against the
   distribution of the maximum over the same K cells under permutation, never
   against a single-cell null.
3. **At least 25 permutation draws.** A null built from 3 draws gave z=+8.4 on
   data where 30 draws gave z=+2.1. Small-sample standard deviations inflate z.
4. **Bit 0 excluded.** `(u+v)[0] = u[0] XOR v[0]` holds identically, so bit 0 is
   arithmetic, not cryptanalysis.
5. **Identity screen.** Before any cell is reported, check whether the target is
   an exact shifted copy of the source, or contains it by construction.
6. **Disjoint confirmation.** A candidate found on one seed must hold on fresh
   seeds. One candidate at 50.9 % fell to 50.0 % under this test and was dropped.
7. **N-scaling is not proof.** Selection bias also grows with N. It is reported
   but never used as the argument.
