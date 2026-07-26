#!/usr/bin/env python3
"""
Fast verification pass -- the controls and the prediction rule, nothing slow.

reproduce.py runs the full set in about 16 minutes, dominated by rc5_64.py
sweeping to N=800,000. This runs the parts a reviewer wants first: does the
statistic behave on random data, is the signal carry-driven where claimed, and
does the rule predict.

    python quick.py
"""
import subprocess
import sys
import time
import os

HERE = os.path.dirname(os.path.abspath(__file__))
STEPS = [
    ("statistic self-test on random data", "experiments/maxstat.py"),
    ("carry control: ADD vs XOR", "experiments/carry_control.py"),
    ("retention rule: 41 predictions", "experiments/retention_rule.py"),
]

t0 = time.time()
print("=" * 72)
print("  F8 quick verification")
print("=" * 72)
failed = []
for label, script in STEPS:
    print(f"\n>>> {label}")
    r = subprocess.run([sys.executable, os.path.join(HERE, script)],
                       capture_output=True, text=True)
    print(r.stdout.rstrip())
    if r.returncode != 0:
        print(r.stderr.rstrip())
        failed.append(label)

print("\n" + "=" * 72)
if failed:
    print(f"  FAILED: {', '.join(failed)}")
else:
    print(f"  all checks passed in {time.time()-t0:.0f}s")
print("  full run: python reproduce.py")
print("=" * 72)
sys.exit(1 if failed else 0)
