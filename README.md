# mat_vs_py_bench — MATLAB vs Python stimulus timing

A test suite to determine whether a PsychoPy migration from MATLAB /
Psychtoolbox is immediately viable for the CCLab and its technology stack.
Scope is stimulus–neural synchronisation: TTL-to-photon offset and jitter,
frame timing, and DAQ write latency, measured on both stacks on the same rig in
the same session.

Standalone by design — depends only on `numpy`, `psychopy`, and (on the rig)
`nidaqmx`. No lab library is imported, so the bench can be run against the
current stack without changing it.

## Install

```bash
uv sync                # off-rig (laptop): T1, T4, all self-checks
uv sync --extra rig    # on the rig; the NI-DAQmx driver must already be installed
uv sync --extra plot   # matplotlib, for plotting saved results
```

Python ≥ 3.11. The MATLAB arm needs Psychtoolbox and `cclab-matlab-tools` on the
MATLAB path.

## Configure

The rig config is the lab's existing `cclab-matlab-tools/cfg/*.txt` file — the
same file MATLAB reads, so both arms agree on which BNC is which. Its location
varies per machine, so point at it explicitly:

```bash
export CCLAB_RIG_CONFIG=/path/to/cclab-matlab-tools/cfg/rig-right.txt
```

Or pass `--config <path>` per run, or copy/symlink the `cfg/` directory into this
repo — the default is `cfg/rig-right.txt`, relative to the repo root. `cfg/dummy.txt`
is checked in (all channels `none`), so `--dummy` runs need no rig config at all.

## Usage

Run `preflight.py` first, every time. It fails fast on the things that waste a
booking — missing driver, wrong screen, sync tests disabled, no photodiode swing
— and exits nonzero if any hard blocker is present.

```bash
uv run python preflight.py --off-rig     # laptop: skips the NI checks
uv run python preflight.py               # rig: full check, exit 1 blocks the session
```

Off-rig, no hardware needed:

```bash
uv run python t1_flip.py --frames 3000            # flip timing; --no-rush / --no-gc-off ablate
uv run python t4_micro.py -n 1000000 --reps 20    # interpreter microbenchmark
uv run python t0_daq.py --dummy -n 1000           # exercises the DAQ path without a card
uv run python t2_photodiode.py --dummy --flips 60 # exercises the T2 analysis end to end
```

On the rig:

```bash
uv run python t0_daq.py -n 10000 --line A --width-ms 1.0
uv run python t2_photodiode.py --flips 300 --rate 50000 --pd-chan ai0 --ttl-chan ai1
```

Common flags: `--config` (rig config path), `--screen` (which display; the
stimulus monitor, not the console), `--out` (result directory, default
`results/`), `--dummy` (no hardware).

MATLAB arm, from `matlab/`, same rig and same session as the Python arm:

```matlab
t1_flip(3000);
t4_micro(1000000, 20);
t0_daq('rig-right', 10000);
t2_photodiode('rig-right', 300);
```

Self-checks — no hardware, no display, safe in CI:

```bash
uv run python dio.py && uv run python report.py \
  && uv run python t2_photodiode.py --selftest && uv run python t4_micro.py --selftest
```

## Results

Each run writes to `results/` as `<test>_<YYYYMMDDTHHMMSSZ>`: a `.json` summary
(n, median, mean, sd, iqr, p01, p99, min, max, plus a `meta` block) and the raw
samples (`.npy` from Python, `.csv` from MATLAB). Raw samples are always kept, so
a question can be re-answered without re-booking the rig.

Bench output is rig-characterisation data, not recording data, so the
[CC Lab Data Organization Standard](~/dev/research/CogCtrlLab/CCLabDataOrg)
(`CC Lab Data Organization Standard.md`) does not apply directly — there is no
session, animal, area, or task block here, and the session hierarchy and
`task.mat` metafile have nothing to describe. What does carry over, and is
already followed:

- `YYYYMMDD` timestamps, so results sort chronologically
- raw / processed separation — raw samples immutable, summaries derived
- open formats (`.json`, `.npy`, `.csv`; never `.mat`) so any language can read them

If bench results are ever archived alongside session data, treat a rig+date as
the key (`rigright_20260825`) and file it under `derivatives/`, not under an
animal.

## Acceptance criterion — agree with Xiaomo before measuring

A constant offset is not an error. If stimulus onset is reliably 8ms after the
TTL on every trial, that value can be subtracted in analysis at no cost. What
degrades a PSTH is jitter — trial-to-trial variability, which cannot be
corrected because its value on any given trial is unknown.

The bar is therefore:

- jitter (SD) of TTL→photon **< 1ms**
- p01..p99 spread **within 5ms**
- median offset: any stable value, reported and subtracted
- PsychoPy jitter within **2×** Psychtoolbox, same rig, same session

`t2_photodiode.py` prints PASS/FAIL against these rather than leaving the
judgement to inspection. Agreeing the criterion in advance is what makes the
measurement decisive; agreed afterwards, any result is arguable.

## TODO

Before the rig session:

- [ ] Get the criterion above agreed with Xiaomo, in writing
- [ ] Confirm a photodiode exists in the lab — **blocks T2, the decisive test**
- [ ] Confirm both arms can run in one session without re-cabling the BNC
- [ ] Record rig PC specs: Windows version, GPU, monitor model, refresh rate
- [ ] Confirm which neural system receives the TTL and how it timestamps input
- [ ] Run T1 and T4 on a laptop; they need no booking and catch setup problems early
- [ ] Book the rig

On the rig, in order:

- [ ] `preflight.py` — must exit 0
- [ ] T0 both arms, T2 both arms (T2 first if time is short)
- [ ] T1 on the rig monitor, both arms

Code still to write:

- [ ] T3 — timing under realistic load; not started, shape depends on T1/T2
- [ ] T5 — mitigation ablation; needs the T3 loop plus the existing `--no-rush`
      and `--no-gc-off` flags
- [ ] `analyze.py` — plot saved results across arms; the `plot` extra exists for it

After:

- [ ] Write up T2 as the headline result; T4 as one ruling-out slide
- [ ] Decide the migration, then extract `cclab-rig` from whatever this needed

---

# Test log — one entry per concern

Each section below is written to be pasted into a GitHub issue once the lab org
exists. Status is `open` until measured on the rig.

---

## T0 — DAQ write latency `open`

**Concern.** How long does a TTL pulse call take, and how variable is it? If the
`nidaqmx` path is meaningfully worse than MATLAB's DAQ Toolbox path, that is a
blocker, and it is better established before anything is built on top.

**Method.** `t0_daq.py` / `matlab/t0_daq.m`. N=10000 pulses on line A, no
display involved. Measure wall time around the call, subtract the deliberate
1ms busy-wait, leaving driver overhead. 20 warm-up pulses discarded. The MATLAB
arm calls `cclabPulse` **unmodified**, so the comparison is against the stack as
it exists rather than against a reimplementation.

**Prediction.** ~20–100µs median, occasional tail to ~1ms from OS scheduling.
Python and MATLAB within a factor of 2, since both are thin wrappers over the
same NI-DAQmx C driver.

**Pass.** Median < 200µs, p99 < 1ms, within 2× of MATLAB.

**If it fails.** This is the result that would justify moving the DAQ path out of
Python into a dedicated daemon. Not before.

---

## T1 — flip timing `open`

**Concern.** Does `win.flip()` land on the refresh clock, and how often does it
miss? Dropped frames are the practical failure mode: one drop is a whole refresh
period, 16.7ms at 60Hz — three times the entire error budget.

**Method.** `t1_flip.py` / `matlab/t1_flip.m`. Fullscreen, alternate a white
patch, capture 3000 flip timestamps, take intervals. `core.rush` and
`gc.freeze/disable` on. PTB arm uses `Priority(MaxPriority(w))` and
**`SkipSyncTests = 0`** — the sync tests are part of what is under test.

**Prediction.** Median = refresh period, SD well under 0.5ms because flips are
quantised to the refresh clock. Drops rare when idle. The number that matters is
the drop rate under load (see T3).

**Pass.** Implied refresh matches the monitor. Drops < 0.1% idle.

**Note.** Runs on a laptop. Run it early and often; it is the cheapest signal
available and needs no booking.

---

## T2 — photodiode ground truth `open` **decisive**

**Concern.** The other tests measure software talking to itself. This one
measures photons. It is the test that settles the migration question, and the
one whose result belongs on a slide.

**Wiring.**

```
photodiode aimed at stimulus monitor corner  ->  ai0
TTL line 'A' BNC on the breakout box         ->  ai1
```

Both signals are digitised by the **same PCIe-6351 clock**, so the TTL→photon
interval is measured by the card and does not depend on either computer's
software clock. No cross-clock assumption enters the number.

**Method.** `t2_photodiode.py` / `matlab/t2_photodiode.m`. Finite hardware-timed
AI capture at 50kHz (finite, not continuous, so no reader thread competes with
the flip loop). Alternate a white patch in the diode's corner, fire line A
immediately after each flip returns, 300 flips. Post-hoc: debounced rising-edge
detection on both channels, auto-thresholded from each signal's own floor and
peak, then pair each TTL to the next photodiode edge within 2 refresh periods.

**Prediction.** Median offset of one refresh plus panel response, so roughly
5–20ms depending on the monitor — acceptable, since it is constant. SD under
0.5ms. PsychoPy and PTB within one frame of each other.

**Pass.** The criterion above.

**Blocked on.** A photodiode. Most NHP labs have one; otherwise a phototransistor
plus a BNC is a few dollars. **Confirm this exists before booking the rig** —
without it T2 cannot run and most of the session is wasted.

**Trap, already guarded.** If the edge-pairing window exceeds one frame period, a
dropped frame does not appear as a missing pair — it pairs with the *next*
frame's photodiode edge and reports a lag one refresh too long, turning the most
important failure mode into a plausible-looking number. `pair_edges` takes
`max_lag_s = 2 × refresh` and there is a self-check pinning the behaviour.

---

## T3 — timing under realistic load `open`

**Concern.** T1 and T2 measure an idle loop. Real tasks draw images, poll gaze,
and append rows. Timing that only holds when nothing else happens does not hold.

**Method.** T1/T2 protocol with the loop doing per-frame work: draw a
full-screen image, poll gaze (mouse off-rig, EyeLink on-rig), append an event
row to an in-memory list. Explicitly **no disk IO in the loop** — that is the
discipline being validated, and the comparison against a version that does write
per-frame is worth running once to document the reason for the rule.

**Prediction.** This is where drops appear, if anywhere. Expect good timing plus
N drops per 10k, with the work being to drive N to zero.

**Pass.** Drops < 0.1%, jitter unchanged from T2.

**Not yet written.** Depends on what T1/T2 reveal about where the margin is.

---

## T4 — language microbenchmark `open` *ruling-out only*

**Concern.** "Isn't Python slow?" is a question the migration will attract, and
it deserves a number.

**Method.** `t4_micro.py` / `matlab/t4_micro.m`. 1e6 iterations of scalar
branch-plus-arithmetic — the shape of a trial-loop state check. Pure Python and
pure MATLAB loops, no vectorisation on either side, since vectorising would
measure C rather than the interpreter.

**Prediction.** ~60ns/iteration in CPython. MATLAB comparable or slower; both
are interpreted. A 60Hz frame fits ~270,000 such iterations; a trial loop runs a
few hundred per frame.

**Framing.** This is not the argument for the migration. Interpreter overhead
sits last among jitter sources, four to five orders of magnitude below the
display path. Present it as one slide that rules the question out, and lead with
T2.

---

## T5 — mitigation ablation `open`

**Concern.** The PsychoPy arm runs with `gc.freeze/disable` and `core.rush`. Do
they measurably help on this rig, or are they inherited habit?

**Method.** T3 with each toggled: `--no-rush`, `--no-gc-off`. Flags already exist
on `t1_flip.py`.

**Prediction.** GC off removes rare multi-ms outliers rather than shifting the
median. `rush` reduces the tail. Both show up in p99 and max, not in the median —
which is itself the argument for reporting percentiles rather than mean±SD.

**Pass.** Not pass/fail. If a mitigation does nothing measurable, drop it rather
than keeping it by default.
