"""T2 -- photodiode ground truth. The decisive test.

The other tests provide context; this is the measurement that decides whether
the PsychoPy migration is viable.

WIRING
    photodiode aimed at a corner of the stimulus monitor  ->  ai0
    TTL line 'A' BNC on the breakout box                  ->  ai1

Both signals are then digitised by the SAME NI PCIe-6351 clock, so the interval
between them is measured by the card and does not depend on either computer's
software clock, so no cross-clock assumption enters the number.

WHAT IT PRODUCES
    flip -> photon   : how long after the flip call returns light actually changes
    TTL  -> photon   : the offset the neural recorder will see  <-- the criterion
    jitter of both   : SD and p99, which is what the criterion is stated against

Run the same protocol under matlab/t2_photodiode.m for the Psychtoolbox arm.

    uv run python t2_photodiode.py --dummy --flips 60
    uv run python t2_photodiode.py --flips 300
"""

from __future__ import annotations

import argparse
import gc
import time

import numpy as np

from dio import DEFAULT_CONFIG, open_dio, parse_config
from report import summarise, write_result


# ---------------------------------------------------------------- acquisition

class AnalogCapture:
    """Finite hardware-timed AI capture on two channels.

    Finite (not continuous) on purpose: the run is a few seconds, the whole
    record fits in host RAM, and a finite task needs no reader thread competing
    with the flip loop -- no background threads during timing-critical work.
    """

    def __init__(self, device: str, pd_chan: str, ttl_chan: str,
                 rate: float, n_samples: int):
        import nidaqmx
        from nidaqmx.constants import AcquisitionType, TerminalConfiguration

        self.rate = rate
        self.n_samples = n_samples
        self.task = nidaqmx.Task()
        for ch in (pd_chan, ttl_chan):
            self.task.ai_channels.add_ai_voltage_chan(
                f"{device}/{ch}", min_val=-10.0, max_val=10.0,
                terminal_config=TerminalConfiguration.RSE,
            )
        self.task.timing.cfg_samp_clk_timing(
            rate, sample_mode=AcquisitionType.FINITE, samps_per_chan=n_samples)

    def start(self) -> None:
        self.task.start()

    def read(self, timeout: float = 30.0) -> np.ndarray:
        data = self.task.read(number_of_samples_per_channel=self.n_samples,
                              timeout=timeout)
        return np.asarray(data, dtype=float)  # shape (2, n)

    def close(self) -> None:
        self.task.stop()
        self.task.close()


class DummyCapture:
    """Synthesises a plausible trace so the analysis path is exercised off-rig.

    Models a real display: light changes one refresh after the flip returns,
    plus panel response, plus a little jitter. The numbers are invented -- only
    the shape is real. Never present dummy output as a result.
    """

    def __init__(self, rate: float, n_samples: int, flip_times: list[float],
                 t0: float, refresh: float):
        self.rate, self.n_samples = rate, n_samples
        self._flips, self._t0, self._refresh = flip_times, t0, refresh
        self._rng = np.random.default_rng(0)

    def start(self) -> None:
        pass

    def read(self, timeout: float = 30.0) -> np.ndarray:
        n = self.n_samples
        pd = np.zeros(n)
        ttl = np.zeros(n)
        panel_lag = 0.004  # invented: LCD response
        for i, tf in enumerate(self._flips):
            rel = tf - self._t0
            j = self._rng.normal(0, 0.0002)
            s_ttl = int(rel * self.rate)
            s_pd = int((rel + panel_lag + j) * self.rate)
            if 0 <= s_ttl < n:
                ttl[s_ttl:s_ttl + int(0.001 * self.rate)] = 5.0
            if 0 <= s_pd < n and i % 2 == 0:  # light rises on alternate flips
                pd[s_pd:s_pd + int(self._refresh * 2 * self.rate)] = 3.0
        return np.vstack([pd, ttl])

    def close(self) -> None:
        pass


# ------------------------------------------------------------ edge extraction

def rising_edges(sig: np.ndarray, rate: float, threshold: float,
                 min_gap_s: float = 0.002) -> np.ndarray:
    """Times (seconds from capture start) of low->high threshold crossings.

    Debounced by min_gap_s: an LCD ramp or a noisy photodiode can wobble across
    the threshold several times on one true transition, and each wobble would
    otherwise become a spurious event and corrupt the pairing below.
    """
    high = sig > threshold
    idx = np.flatnonzero(~high[:-1] & high[1:]) + 1
    if idx.size == 0:
        return np.empty(0)
    keep = [idx[0]]
    min_gap = int(min_gap_s * rate)
    for i in idx[1:]:
        if i - keep[-1] >= min_gap:
            keep.append(i)
    return np.asarray(keep, dtype=float) / rate


def auto_threshold(sig: np.ndarray) -> float:
    """Midpoint between the signal's floor and ceiling.

    Photodiode output level depends on the diode, the gain, the monitor, and how
    the thing is taped to the screen. Hardcoding a volts threshold would mean
    re-tuning a constant every session; taking it from the data does not.
    """
    # Floor from a low percentile (robust to noise), ceiling from the max.
    # NOT a high percentile: a 1ms TTL inside a 16.7ms frame is ~1% duty cycle,
    # so even the 99th percentile still sits in the low state.
    lo = float(np.percentile(sig, 1))
    hi = float(np.max(sig))
    if hi - lo < 0.1:
        raise ValueError(
            f"signal has no usable swing (floor={lo:.3f}V, peak={hi:.3f}V). "
            "Check the photodiode is aimed at the flashing corner and powered.")
    return (lo + hi) / 2.0


def pair_edges(ttl_t: np.ndarray, pd_t: np.ndarray,
               max_lag_s: float = 0.030) -> np.ndarray:
    """For each TTL edge, the delay to the next photodiode edge within max_lag_s.

    Returns NaN where no photodiode edge followed -- which is exactly what a
    dropped frame looks like, so those NaNs are a finding, not an error.

    max_lag_s must stay BELOW the inter-flip interval. If it exceeds one frame
    period, a dropped frame does not show up as NaN: the TTL silently pairs with
    the NEXT frame's photodiode edge and reports a lag one refresh too long.
    That turns the test's most important failure mode into a plausible-looking
    number. Callers pass 2x the measured refresh period.
    """
    out = np.full(ttl_t.shape, np.nan)
    j = 0
    for i, t in enumerate(ttl_t):
        while j < pd_t.size and pd_t[j] < t:
            j += 1
        if j < pd_t.size and pd_t[j] - t <= max_lag_s:
            out[i] = pd_t[j] - t
    return out


# ------------------------------------------------------------------- protocol

def run(config: str, dummy: bool, flips: int, rate: float,
        pd_chan: str, ttl_chan: str, line: str, screen: int):
    from psychopy import core, visual

    dio = open_dio(config, dummy=dummy)
    win = visual.Window(fullscr=True, screen=screen, color=(-1, -1, -1),
                        units="pix", allowGUI=False, waitBlanking=True)
    refresh = win.monitorFramePeriod or (1 / 60.0)

    patch = visual.Rect(win, width=200, height=200, fillColor=(1, 1, 1),
                        lineColor=None,
                        pos=(-win.size[0] / 2 + 110, win.size[1] / 2 - 110))

    n_samples = int((flips * refresh + 1.0) * rate)
    flip_times: list[float] = []

    if dummy:
        cap = DummyCapture(rate, n_samples, flip_times, 0.0, refresh)
    else:
        chans = parse_config(config)
        dev = getattr(dio, "device", None) or _device_from(chans)
        cap = AnalogCapture(dev, pd_chan, ttl_chan, rate, n_samples)

    # P5 / core.rush: quiesce the collector and raise priority for the loop only.
    core.rush(True)
    gc.collect(); gc.freeze(); gc.disable()
    try:
        # Discard the first frames: the first flip after window creation is
        # never representative (texture upload, driver warm-up).
        for _ in range(10):
            win.flip()

        cap.start()
        t0 = time.perf_counter()
        for i in range(flips):
            if i % 2 == 0:
                patch.draw()
            t = win.flip()          # the flip's own timestamp, not the clock
            dio.pulse(line, 1.0)    # fire immediately after, measure below
            flip_times.append(t)
        data = cap.read()
    finally:
        gc.enable()
        core.rush(False)
        cap.close()
        dio.close()
        win.close()

    if dummy:  # DummyCapture needs the times it was supposed to synthesise
        cap._flips, cap._t0 = flip_times, flip_times[0] if flip_times else 0.0
        data = cap.read()

    pd_sig, ttl_sig = data[0], data[1]
    pd_t = rising_edges(pd_sig, rate, auto_threshold(pd_sig))
    ttl_t = rising_edges(ttl_sig, rate, auto_threshold(ttl_sig))
    lag = pair_edges(ttl_t, pd_t, max_lag_s=2 * refresh) * 1000.0  # ms

    return {
        "ttl_to_photon_ms": lag,
        "flip_intervals_ms": np.diff(flip_times) * 1000.0,
        "n_ttl_edges": ttl_t.size,
        "n_pd_edges": pd_t.size,
        "refresh_s": refresh,
    }


def _device_from(chans) -> str:
    from dio import _find_device
    return _find_device()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--dummy", action="store_true",
                    help="synthesise a trace; exercises analysis, proves nothing")
    ap.add_argument("--flips", type=int, default=300)
    ap.add_argument("--rate", type=float, default=50000.0, help="AI sample rate Hz")
    ap.add_argument("--pd-chan", default="ai0", help="photodiode analog in")
    ap.add_argument("--ttl-chan", default="ai1", help="TTL loopback analog in")
    ap.add_argument("--line", default="A", help="digital out line to pulse")
    ap.add_argument("--screen", type=int, default=0)
    ap.add_argument("--out", default="results")
    args = ap.parse_args()

    r = run(args.config, args.dummy, args.flips, args.rate,
            args.pd_chan, args.ttl_chan, args.line, args.screen)

    lag = r["ttl_to_photon_ms"]
    dropped = int(np.count_nonzero(~np.isfinite(lag)))
    stats = summarise(lag)
    flip_stats = summarise(r["flip_intervals_ms"])

    if args.dummy:
        print("*** DUMMY -- synthetic trace. Not a result. ***")
    print(f"T2  TTL -> photon (ms), n={args.flips}")
    for k, v in stats.items():
        print(f"  {k:>6}: {v:9.4f}")
    print(f"  edges : {r['n_ttl_edges']} TTL / {r['n_pd_edges']} photodiode")
    print(f"  unpaired (dropped?): {dropped}")
    print(f"\n  inter-flip interval (ms): median {flip_stats['median']:.3f} "
          f"sd {flip_stats['sd']:.3f} max {flip_stats['max']:.3f}")

    # The pre-registered criterion, evaluated here rather than by eye.
    ok_sd = stats["sd"] < 1.0
    spread = max(abs(stats["p99"] - stats["median"]),
                 abs(stats["median"] - stats["p01"]))
    ok_p99 = spread < 5.0
    print(f"\n  CRITERION (spec/TIMELINE.md)")
    print(f"    jitter SD < 1ms         : {'PASS' if ok_sd else 'FAIL'} ({stats['sd']:.3f})")
    print(f"    p01..p99 within 5ms     : {'PASS' if ok_p99 else 'FAIL'} ({spread:.3f})")
    print(f"    median offset (subtract in analysis): {stats['median']:.3f} ms")

    write_result(args.out, "t2_photodiode_python", stats, lag,
                 meta={"flips": args.flips, "rate": args.rate, "dummy": args.dummy,
                       "dropped": dropped, "flip_intervals": flip_stats,
                       "criterion_sd_pass": ok_sd, "criterion_p99_pass": ok_p99})


def _selftest() -> None:
    rate = 50000.0
    n = int(1.0 * rate)
    ttl = np.zeros(n); pd = np.zeros(n)
    true_lag = 0.004
    for k in range(10):
        s = int((0.05 + k * 0.05) * rate)
        ttl[s:s + int(0.001 * rate)] = 5.0
        p = s + int(true_lag * rate)
        pd[p:p + int(0.01 * rate)] = 3.0

    te = rising_edges(ttl, rate, auto_threshold(ttl))
    pe = rising_edges(pd, rate, auto_threshold(pd))
    assert te.size == 10 and pe.size == 10, (te.size, pe.size)
    lag = pair_edges(te, pe, max_lag_s=0.030)
    assert np.allclose(lag, true_lag, atol=1e-4), lag

    # a dropped frame -> unpaired TTL -> NaN, not a wrong pairing
    lag2 = pair_edges(te, pe[1:], max_lag_s=0.030)
    assert np.isnan(lag2[0]), "missing photodiode edge must yield NaN"
    assert np.allclose(lag2[1:], true_lag, atol=1e-4), "later pairs must not shift"

    # too-loose max_lag silently mispairs instead of reporting the drop
    bad = pair_edges(te, pe[1:], max_lag_s=0.100)
    assert not np.isnan(bad[0]) and bad[0] > 0.04, "guard: this is the bug max_lag prevents"

    # debounce: a wobbly LCD ramp must not become several events
    wob = np.zeros(n)
    s = int(0.05 * rate)
    wob[s:s + 5] = 3.0; wob[s + 8:s + 12] = 0.0; wob[s + 12:s + 5000] = 3.0
    assert rising_edges(wob, rate, 1.5).size == 1, "debounce failed"

    try:
        auto_threshold(np.zeros(100))
    except ValueError:
        pass
    else:
        raise AssertionError("flat signal must raise, not silently return garbage")
    print("t2 selftest ok")


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        _selftest()
    else:
        main()
