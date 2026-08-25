"""Preflight -- check the machine before you burn rig time.

Run this the moment you sit down at the rig. Every check here corresponds to a
way a session has been wasted: no NI driver, wrong screen, sync tests disabled,
no photodiode swing. Finding out at minute 1 costs nothing; finding out at
minute 50 costs the booking.

Exits nonzero if anything is a hard blocker.

    uv run python preflight.py
    uv run python preflight.py --config <path to cfg/rig-right.txt>
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

DEFAULT_CONFIG = "../psychopy_template/cclab_movie_project/Code/cclab-matlab-tools/cfg/rig-right.txt"

OK, WARN, FAIL = "  ok ", " warn", " FAIL"
_status: list[str] = []


def check(name: str, fn, hard: bool = True) -> None:
    try:
        detail = fn()
        print(f"[{OK}] {name}" + (f" -- {detail}" if detail else ""))
    except Exception as e:  # noqa: BLE001 -- preflight reports, never crashes
        print(f"[{FAIL if hard else WARN}] {name} -- {e}")
        _status.append(name if hard else "")


def c_python() -> str:
    v = sys.version_info
    if v < (3, 11):
        raise RuntimeError(f"need >=3.11, have {v.major}.{v.minor}")
    return f"{v.major}.{v.minor}.{v.micro}"


def c_uv() -> str:
    p = shutil.which("uv")
    if not p:
        raise RuntimeError("not on PATH -- https://docs.astral.sh/uv/")
    return p


def c_numpy() -> str:
    import numpy
    return numpy.__version__


def c_psychopy() -> str:
    import psychopy
    return psychopy.__version__


def c_nidaqmx() -> str:
    import nidaqmx.system
    devs = list(nidaqmx.system.System.local().devices)
    if not devs:
        raise RuntimeError("driver present but no devices -- card seated? NI-MAX sees it?")
    names = ", ".join(f"{d.name}({d.product_type})" for d in devs)
    if not any("PCIe-6351" in d.product_type for d in devs):
        raise RuntimeError(f"no PCIe-6351 among: {names}")
    return names


def c_config(path: str):
    def _inner() -> str:
        from dio import parse_config
        p = Path(path)
        if not p.exists():
            raise RuntimeError(f"{p} not found -- is the cclab-matlab-tools submodule checked out?")
        ch = parse_config(p)
        digout = [c.label for c in ch if c.kind == "digout"]
        return f"{p.name}: digout lines {digout}"
    return _inner


def c_screens() -> str:
    from psychopy import monitors  # noqa: F401
    import pyglet
    disp = pyglet.canvas.get_display()
    screens = disp.get_screens()
    if len(screens) < 2:
        raise RuntimeError(
            f"only {len(screens)} screen(s). The stimulus monitor should be a "
            "separate display, and --screen must point at it.")
    return " | ".join(f"{s.width}x{s.height}" for s in screens)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--off-rig", action="store_true",
                    help="skip hardware checks; expect to develop, not measure")
    args = ap.parse_args()

    print("cclab bench preflight\n")
    check("python >= 3.11", c_python)
    check("uv on PATH", c_uv)
    check("numpy", c_numpy)
    check("psychopy", c_psychopy)
    check("rig config readable", c_config(args.config))
    check("multiple displays", c_screens, hard=False)

    if args.off_rig:
        print(f"[{WARN}] nidaqmx -- skipped (--off-rig)")
        print(f"[{WARN}] NI PCIe-6351 -- skipped (--off-rig)")
    else:
        check("nidaqmx + NI PCIe-6351", c_nidaqmx)

    print()
    if any(_status):
        print("BLOCKED. Fix the FAIL lines above before spending rig time.")
        sys.exit(1)

    print("Preflight clear.\n")
    print("Reminders that no script can check for you:")
    print("  - Is the photodiode taped over the flashing corner and powered?")
    print("  - Is TTL line 'A' patched into ai1?")
    print("  - Is SkipSyncTests OFF in the MATLAB arm? (sync tests ARE the test)")
    print("  - Has the criterion in spec/TIMELINE.md been agreed BEFORE measuring?")
    print("  - Both arms in the same session, no re-cabling between them.")


if __name__ == "__main__":
    main()
