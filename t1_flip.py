"""T1 -- flip timing. Runs on a laptop, no hardware.

Question: does win.flip() land on the refresh clock, and how often does it miss?

This does not need the rig, so run it early and often. It cannot prove the
migration (only T2 does that) but it catches the failure mode that actually
bites: dropped frames. A dropped frame is a whole refresh period of error --
16.7ms at 60Hz, three times the entire budget -- and it is caused by code
discipline, not by language choice.

    uv run python t1_flip.py --frames 3000
"""

from __future__ import annotations

import argparse
import gc

import numpy as np

from report import summarise, write_result


def run(frames: int, screen: int, use_rush: bool, use_gc_off: bool) -> np.ndarray:
    from psychopy import core, visual

    win = visual.Window(fullscr=True, screen=screen, color=(-1, -1, -1),
                        units="pix", allowGUI=False, waitBlanking=True)
    patch = visual.Rect(win, width=200, height=200, fillColor=(1, 1, 1),
                        lineColor=None)

    if use_rush:
        core.rush(True)
    if use_gc_off:
        gc.collect(); gc.freeze(); gc.disable()
    try:
        for _ in range(10):  # discard warm-up frames
            win.flip()
        t = np.empty(frames)
        for i in range(frames):
            if i % 2 == 0:
                patch.draw()
            t[i] = win.flip()
    finally:
        gc.enable()
        if use_rush:
            core.rush(False)
        win.close()

    return np.diff(t) * 1000.0  # inter-flip intervals, ms


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frames", type=int, default=3000)
    ap.add_argument("--screen", type=int, default=0)
    ap.add_argument("--no-rush", action="store_true", help="ablation: skip core.rush")
    ap.add_argument("--no-gc-off", action="store_true", help="ablation: leave gc enabled")
    ap.add_argument("--out", default="results")
    args = ap.parse_args()

    iv = run(args.frames, args.screen, not args.no_rush, not args.no_gc_off)
    stats = summarise(iv)

    # A "drop" is an interval closer to 2 refreshes than to 1.
    refresh = float(np.median(iv))
    dropped = int(np.count_nonzero(iv > refresh * 1.5))

    print(f"T1  inter-flip interval (ms), frames={args.frames}, "
          f"rush={not args.no_rush}, gc_off={not args.no_gc_off}")
    for k, v in stats.items():
        print(f"  {k:>6}: {v:9.4f}")
    print(f"  implied refresh: {1000.0 / refresh:.2f} Hz")
    print(f"  dropped frames : {dropped} / {iv.size}  ({100.0 * dropped / iv.size:.3f}%)")

    write_result(args.out, "t1_flip_python", stats, iv,
                 meta={"frames": args.frames, "dropped": dropped,
                       "refresh_hz": 1000.0 / refresh,
                       "rush": not args.no_rush, "gc_off": not args.no_gc_off})


if __name__ == "__main__":
    main()
