"""Shared stats + result persistence for the bench suite.

Every test writes the same shape: a JSON summary (for the slide) and a raw npy
(for re-analysis without re-running on the rig). Rig time is expensive; never
throw away raw samples.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def summarise(x: np.ndarray) -> dict[str, float]:
    """Median and spread, not mean and SD.

    A dropped frame is a huge outlier that drags a mean around while telling you
    nothing about typical behaviour. The percentiles are what the pre-registered
    criterion in spec/TIMELINE.md is actually stated against.
    """
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        raise ValueError("no finite samples")
    return {
        "n": float(x.size),
        "median": float(np.median(x)),
        "mean": float(np.mean(x)),
        "sd": float(np.std(x, ddof=1)) if x.size > 1 else 0.0,
        "iqr": float(np.subtract(*np.percentile(x, [75, 25]))),
        "p01": float(np.percentile(x, 1)),
        "p99": float(np.percentile(x, 99)),
        "min": float(np.min(x)),
        "max": float(np.max(x)),
    }


def write_result(outdir: str | Path, name: str, stats: dict,
                 raw: np.ndarray | None = None, meta: dict | None = None) -> Path:
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = out / f"{name}_{stamp}"

    base.with_suffix(".json").write_text(json.dumps(
        {"test": name, "utc": stamp, "stats": stats, "meta": meta or {}}, indent=2))
    if raw is not None:
        np.save(base.with_suffix(".npy"), np.asarray(raw))

    print(f"  -> {base}.json")
    return base.with_suffix(".json")


def _selftest() -> None:
    x = np.concatenate([np.zeros(99), [1000.0]])  # 99 good samples, one dropped frame
    s = summarise(x)
    assert s["median"] == 0.0, "median must ignore the outlier"
    assert s["mean"] > 9.0, "mean must be dragged by it -- this is why we report both"
    assert s["max"] == 1000.0
    assert s["p99"] < s["max"], "p99 must sit below a single extreme outlier"
    try:
        summarise(np.array([np.nan, np.inf]))
    except ValueError:
        pass
    else:
        raise AssertionError("all-nonfinite input must raise")
    print("report selftest ok")


if __name__ == "__main__":
    _selftest()
