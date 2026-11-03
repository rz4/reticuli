"""Reviewer finding #2, against the SHIPPED function.

Two producers whose outcomes are independent GIVEN the case -- no shared
convention, no common prior, nothing the claim failed to name. The only
structure is that some cases are harder than others, which is true of every
test suite ever written.

heldout.agreement()'s docstring says a positive excess means "they share
structure the claim never named." If it reports a large positive excess here,
the statistic cannot distinguish shared convention from shared difficulty.
"""
import random, statistics, sys
sys.path.insert(0, "src")
from reticuli import heldout

def trial(n_cases, p_easy, p_hard, seed):
    rng = random.Random(seed)
    a, b = {}, {}
    for i in range(n_cases):
        p = p_easy if i % 2 == 0 else p_hard      # difficulty, known to nobody
        a[f"c{i}"] = rng.random() < p             # independent draws,
        b[f"c{i}"] = rng.random() < p             # conditional on difficulty
    return heldout.agreement(a, b)

print("Producers independent conditional on case difficulty.")
print("Half the cases p=0.90, half p=0.10. No shared hidden structure.\n")
runs = [trial(2000, 0.9, 0.1, s) for s in range(40)]
print(f"  observed agreement : {statistics.mean(r['agreement'] for r in runs):.3f}")
print(f"  'expected' baseline: {statistics.mean(r['expected'] for r in runs):.3f}")
print(f"  EXCESS             : {statistics.mean(r['excess'] for r in runs):+.3f}"
      f"  (sd {statistics.stdev(r['excess'] for r in runs):.3f})")
print()
print("  reviewer's prediction: +0.32, from E[excess] = 2*Cov(p_Ai, p_Bi)")
print("    Cov = 0.5*(0.81+0.01) - 0.25 = 0.16  ->  2*0.16 = 0.32")
print()

# the control: uniform difficulty, so there is no covariance to pick up
flat = [trial(2000, 0.5, 0.5, s) for s in range(40)]
print(f"Control, uniform difficulty (p=0.5 everywhere), same independence:")
print(f"  EXCESS             : {statistics.mean(r['excess'] for r in flat):+.3f}"
      f"  (sd {statistics.stdev(r['excess'] for r in flat):.3f})")
print()
mean_excess = statistics.mean(r['excess'] for r in runs)
print("CONFIRMED: the statistic reports large positive excess for producers "
      f"with\nno shared structure whatsoever ({mean_excess:+.2f}), purely because cases "
      "differ in\ndifficulty. The control shows the excess vanishes when "
      "difficulty is uniform,\nwhich isolates difficulty as the cause."
      if mean_excess > 0.25 else "not reproduced")
