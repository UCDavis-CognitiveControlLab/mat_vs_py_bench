"""T0 -- DAQ write latency and jitter. No display involved.

Question: how long does a TTL pulse call take, and how variable is it?
This isolates the DAQ driver path from everything else, so that when T2 gives a
number we know how much of it is the card and how much is the display.

Compare against matlab/t0_daq.m -- same rig, same session, same pulse width.

    uv run python t0_daq.py --dummy -n 1000
    uv run python t0_daq.py --config <path to cfg/rig-right.txt>
"""

from __future__ import annotations

import argparse
import gc
import time

import numpy as np

from dio import open_dio
from report import summarise, write_result

DEFAULT_CONFIG = "../psychopy_template/cclab_movie_project/Code/cclab-matlab-tools/cfg/rig-right.txt"


def run(config: str, dummy: bool, n: int, line: str, width_ms: float) -> np.ndarray:
    dio = open_dio(config, dummy=dummy)

    # P5: quiesce the collector before a timing-critical loop.
    gc.collect()
    gc.freeze()
    gc.disable()
    try:
        # Warm up: the first calls pay driver / page-fault costs that are not
        # representative. MATLAB pays the same tax, so both arms discard it.
        for _ in range(20):
            dio.pulse(line, width_ms)

        elapsed = np.empty(n)
        for i in range(n):
            t0 = time.perf_counter()
            dio.pulse(line, width_ms)
            elapsed[i] = time.perf_counter() - t0
    finally:
        gc.enable()
        dio.close()

    # The measured interval includes our own deliberate busy-wait; subtract it
    # so what remains is driver overhead only.
    return (elapsed - width_ms / 1000.0) * 1000.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--dummy", action="store_true", help="run without NI hardware")
    ap.add_argument("-n", type=int, default=10000)
    ap.add_argument("--line", default="A")
    ap.add_argument("--width-ms", type=float, default=1.0)
    ap.add_argument("--out", default="results")
    args = ap.parse_args()

    overhead = run(args.config, args.dummy, args.n, args.line, args.width_ms)
    stats = summarise(overhead)

    print(f"T0  DAQ write overhead (ms), n={args.n}, line={args.line}, "
          f"{'DUMMY' if args.dummy else 'NI PCIe-6351'}")
    for k, v in stats.items():
        print(f"  {k:>6}: {v:9.4f}")

    write_result(args.out, "t0_daq_python", stats, overhead,
                 meta={"n": args.n, "line": args.line, "width_ms": args.width_ms,
                       "dummy": args.dummy, "config": args.config})


if __name__ == "__main__":
    main()
