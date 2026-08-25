"""T4 -- language microbenchmark. Ruling-out evidence only.

This answers "isn't Python slow?" with a number.

It is deliberately not the argument for the migration. Interpreter overhead sits
last on the list of jitter sources, four to five orders of magnitude below the
display path. Presenting it as the main evidence would be misleading; omitting
it leaves the question open. One slide, framed as ruling out.

Compare against matlab/t4_micro.m -- same loop, same operation counts.

    uv run python t4_micro.py
"""

from __future__ import annotations

import argparse
import gc
import time

import numpy as np

from report import summarise, write_result


def branch_loop(n: int) -> int:
    """Scalar arithmetic + branching -- the shape of a trial-loop state check.

    Kept in pure Python on purpose: vectorising it would measure numpy's C
    speed, not the interpreter's, and the interpreter is what is on trial here.
    """
    acc = 0
    for i in range(n):
        if i % 3 == 0:
            acc += i
        elif i % 5 == 0:
            acc -= i
        else:
            acc += 1
    return acc


def run(n: int, reps: int) -> np.ndarray:
    gc.collect(); gc.freeze(); gc.disable()
    try:
        branch_loop(n // 10)  # warm up
        out = np.empty(reps)
        for r in range(reps):
            t0 = time.perf_counter()
            branch_loop(n)
            out[r] = (time.perf_counter() - t0) * 1000.0
    finally:
        gc.enable()
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-n", type=int, default=1_000_000, help="iterations per rep")
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--out", default="results")
    args = ap.parse_args()

    ms = run(args.n, args.reps)
    stats = summarise(ms)
    per_iter_ns = stats["median"] * 1e6 / args.n

    print(f"T4  {args.n:,} branch+arith iterations, {args.reps} reps")
    for k, v in stats.items():
        print(f"  {k:>6}: {v:9.4f} ms")
    print(f"\n  per iteration: {per_iter_ns:.1f} ns")
    print(f"  a 60Hz frame ({1000/60:.1f} ms) fits ~{int(16.67e6 / per_iter_ns):,} of these.")
    print("  Context: a trial loop runs a few hundred branches per frame.")

    write_result(args.out, "t4_micro_python", stats, ms,
                 meta={"n": args.n, "reps": args.reps, "per_iter_ns": per_iter_ns})


def _selftest() -> None:
    # i in 0..9: multiples of 3 add (0+3+6+9)=18; i=5 subtracts 5;
    # the other five (1,2,4,7,8) add 1 each.
    assert branch_loop(10) == 18 - 5 + 5, branch_loop(10)
    assert branch_loop(0) == 0
    print("t4 selftest ok")


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        _selftest()
    else:
        main()
