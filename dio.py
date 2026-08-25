"""Minimal NI PCIe-6351 digital/analog IO, parsing the lab's existing cfg format.

Deliberately standalone: bench must not depend on cclab-rig, because cclab-rig
is supposed to be extracted from whatever bench turns out to need.

Mirrors cclab-matlab-tools/cclabInitDIO.m + cclabPulse.m closely enough that the
Python and MATLAB arms of the benchmark are doing the same thing.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path

# Rig config lives in the lab's cclab-matlab-tools checkout, whose location varies
# per machine. Point CCLAB_RIG_CONFIG at it, or copy/symlink cfg/ into this repo.
DEFAULT_CONFIG = os.environ.get("CCLAB_RIG_CONFIG", "cfg/rig-right.txt")


@dataclass
class Channel:
    label: str  # 'A', 'B', 'j', 'H' ... matches the BNC label on the breakout box
    kind: str  # 'digout' | 'reward' | 'joystick'
    device: str  # 'ni' | 'mcc' | 'none'
    channel: str = ""  # e.g. 'port0/line4', 'ai0'
    cal: tuple[float, ...] = ()  # joystick calibration voltages, measured


def parse_config(path: str | Path) -> list[Channel]:
    """Parse cclab-matlab-tools/cfg/*.txt.

    Tab-separated: label, kind, device, [channel], [cal...]
    Same file MATLAB reads, so both stacks agree about which BNC is which.
    """
    out = []
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        f = [p for p in line.split("\t") if p != ""]
        if len(f) < 3:
            raise ValueError(f"{path}: malformed config line: {raw!r}")
        out.append(
            Channel(
                label=f[0],
                kind=f[1],
                device=f[2],
                channel=f[3] if len(f) > 3 else "",
                cal=tuple(float(x) for x in f[4:]),
            )
        )
    return out


class DummyDIO:
    """No hardware. Same interface, so dummy mode is a flag and never a code edit."""

    def __init__(self, channels: list[Channel]):
        self.channels = channels
        self.calls: list[tuple[str, float]] = []

    def pulse(self, which: str, width_ms: float = 1.0) -> float:
        t0 = time.perf_counter()
        _busy_wait(width_ms / 1000.0)
        self.calls.append((which, t0))
        return t0

    def close(self) -> None:
        pass


class NIDIO:
    """NI PCIe-6351 via nidaqmx. Digital out only -- reward/joystick not needed for bench."""

    def __init__(self, channels: list[Channel], device: str | None = None):
        import nidaqmx  # imported lazily: not installed off-rig
        from nidaqmx.constants import LineGrouping

        self.digout = [c for c in channels if c.kind == "digout" and c.device == "ni"]
        if not self.digout:
            raise RuntimeError("no 'ni' digout channels in config")

        self.device = device or _find_device()
        self.order = [c.label for c in self.digout]

        self.task = nidaqmx.Task()
        for c in self.digout:
            self.task.do_channels.add_do_chan(
                f"{self.device}/{c.channel}",
                line_grouping=LineGrouping.CHAN_PER_LINE,
            )
        self.task.start()
        self._low = [False] * len(self.digout)

    def pulse(self, which: str, width_ms: float = 1.0) -> float:
        """Drive line(s) high for width_ms, then low. Returns perf_counter at the rising write.

        Blocking, single pulse -- matches cclabPulse.m semantics exactly.
        """
        sample = [c.label in which for c in self.digout]
        unknown = set(which) - set(self.order)
        if unknown:
            raise ValueError(f"channel(s) not configured: {sorted(unknown)}")

        t0 = time.perf_counter()
        self.task.write(sample)
        _busy_wait(width_ms / 1000.0)
        self.task.write(self._low)
        return t0

    def close(self) -> None:
        try:
            self.task.write(self._low)
        finally:
            self.task.stop()
            self.task.close()


def _find_device(model: str = "PCIe-6351") -> str:
    import nidaqmx.system

    for dev in nidaqmx.system.System.local().devices:
        if model in dev.product_type:
            return dev.name
    raise RuntimeError(f"no {model} found; use --dummy for off-rig runs")


def _busy_wait(seconds: float) -> None:
    """Spin rather than sleep.

    time.sleep() on Windows has ~1ms granularity and can overshoot by more --
    unacceptable for a 1ms TTL. MATLAB's WaitSecs spins for the same reason.
    """
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        pass


def open_dio(config: str | Path, dummy: bool = False):
    # --dummy has to work on a laptop with no rig config present.
    if dummy and not Path(config).exists():
        config = Path(__file__).parent / "cfg" / "dummy.txt"
    channels = parse_config(config)
    if dummy or all(c.device == "none" for c in channels):
        return DummyDIO(channels)
    return NIDIO(channels)


def _selftest() -> None:
    import tempfile

    cfg = Path(tempfile.mkdtemp()) / "t.txt"
    cfg.write_text("j\treward\tni\t\nA\tdigout\tni\tport0/line4\nH\tjoystick\tni\tai0\t2.901\t2.092\n")
    ch = parse_config(cfg)
    assert [c.label for c in ch] == ["j", "A", "H"], ch
    assert ch[0].channel == "", "trailing-tab reward line must yield empty channel"
    assert ch[1].channel == "port0/line4"
    assert ch[2].cal == (2.901, 2.092), "joystick calibration voltages must survive parsing"

    d = open_dio(cfg, dummy=True)
    t = d.pulse("A", 1.0)
    assert d.calls == [("A", t)]

    t0 = time.perf_counter()
    _busy_wait(0.002)
    assert 0.002 <= time.perf_counter() - t0 < 0.010, "busy wait must not undershoot"
    print("dio selftest ok")


if __name__ == "__main__":
    _selftest()
