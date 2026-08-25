# mat_vs_py_bench — MATLAB vs Python stimulus timing

Answers one question: **is a PsychoPy stack as good as the lab's MATLAB /
Psychtoolbox stack for stimulus–neural synchronisation?**

Nothing in `cclab-rig` should be built until this answers yes. Standalone on
purpose — depends only on `numpy`, `psychopy`, and (on the rig) `nidaqmx`,
never on `cclab-rig`. That library gets extracted from whatever this turned out
to need.

## Layout assumption

This repo expects to sit **beside** `psychopy_template`:

```
research_infra/
  mat_vs_py_bench/     <- here
  psychopy_template/   <- cclab-rig, spec/, and the cclab-matlab-tools submodule
```

Two paths depend on that: the default rig config
(`../psychopy_template/cclab_movie_project/Code/cclab-matlab-tools/cfg/rig-right.txt`)
and the references to `spec/` below. Both are overridable — pass `--config`
explicitly if your checkout differs.

## Run

```bash
uv sync                              # off-rig
uv sync --extra rig                  # on the rig (needs NI-DAQmx driver installed)

uv run python preflight.py --off-rig # check the machine first, always
uv run python t1_flip.py --frames 3000
uv run python t4_micro.py
uv run python t2_photodiode.py --flips 300      # rig only
uv run python t0_daq.py -n 10000                # rig only
```

MATLAB arm, from `matlab/` with Psychtoolbox and `cclab-matlab-tools` on the path:

```matlab
t1_flip(3000); t4_micro(1000000, 20);
t0_daq('rig-right', 10000); t2_photodiode('rig-right', 300);
```

Self-checks (no hardware, no display):

```bash
uv run python dio.py && uv run python report.py \
  && uv run python t2_photodiode.py --selftest && uv run python t4_micro.py --selftest
```

Results land in `results/` as JSON summaries plus raw `.npy`/`.csv`. Rig time is
expensive: raw samples are always kept so a question can be re-answered without
re-booking.

## The criterion — agree this with Xiaomo BEFORE measuring

Stated in `../psychopy_template/spec/TIMELINE.md`, repeated here because it is the point.

**A constant offset is not an error.** If stimulus onset is reliably 8ms after
the TTL on every trial, that is a number you subtract in analysis and it costs
nothing. What destroys a PSTH is *jitter* — trial-to-trial variability, which
cannot be corrected because you do not know its value on any given trial.

So the bar is:

- jitter (SD) of TTL→photon **< 1ms**
- p01..p99 spread **within 5ms**
- median offset: any stable value, reported and subtracted
- PsychoPy jitter within **2×** Psychtoolbox, same rig, same session

`t2_photodiode.py` prints PASS/FAIL against these rather than leaving it to the eye.

Agreed after the fact, any result is arguable. Agreed in advance, the
measurement decides. This is the single highest-leverage thing in the file.

---

# Test log — one entry per concern

Each section below is written to be pasted into a GitHub issue once the lab org
exists. Status is `open` until measured on the rig.

---

## T0 — DAQ write latency `open`

**Concern.** How long does a TTL pulse call take, and how variable? If the
`nidaqmx` path is meaningfully worse than MATLAB's DAQ Toolbox path, that is a
real blocker and it is better to know before anything is built on top.

**Method.** `t0_daq.py` / `matlab/t0_daq.m`. N=10000 pulses on line A, no
display involved. Measure wall time around the call, subtract the deliberate
1ms busy-wait, leaving driver overhead. 20 warm-up pulses discarded. The MATLAB
arm calls `cclabPulse` **unmodified** — comparing against a reimplementation
would be comparing against a strawman.

**Prediction.** ~20–100µs median, occasional tail to ~1ms from OS scheduling.
Python and MATLAB within a factor of 2, because both are thin wrappers over the
same NI-DAQmx C driver.

**Pass.** Median < 200µs, p99 < 1ms, within 2× of MATLAB.

**If it fails.** This is the one result that would justify the Rust DAQ daemon
in `../psychopy_template/spec/TIMELINE.md`. Not before.

---

## T1 — flip timing `open`

**Concern.** Does `win.flip()` land on the refresh clock, and how often does it
miss? Dropped frames are the failure mode that actually bites: one drop is a
whole refresh period, 16.7ms at 60Hz — three times the entire error budget.

**Method.** `t1_flip.py` / `matlab/t1_flip.m`. Fullscreen, alternate a white
patch, capture 3000 flip timestamps, take intervals. `core.rush` and
`gc.freeze/disable` on. PTB arm uses `Priority(MaxPriority(w))` and
**`SkipSyncTests = 0`** — the sync tests are the thing under test.

**Prediction.** Median = refresh period, SD well under 0.5ms because flips are
quantised to the refresh clock. Drops rare when idle. The number that matters is
the drop rate under load (see T3).

**Pass.** Implied refresh matches the monitor. Drops < 0.1% idle.

**Note.** Runs on a laptop. Run it early and often; it is the cheapest signal
available and needs no booking.

---

## T2 — photodiode ground truth `open` **decisive**

**Concern.** Everything above measures software talking to itself. This measures
photons. It is the only test that can actually settle the migration question,
and the only one whose result belongs on a slide.

**Wiring.**

```
photodiode aimed at stimulus monitor corner  ->  ai0
TTL line 'A' BNC on the breakout box         ->  ai1
```

Both signals are digitised by the **same PCIe-6351 clock**, so the TTL→photon
interval is measured by the card and owes nothing to either computer's software
clock. No cross-clock assumption survives into the number. That is the whole
trick.

**Method.** `t2_photodiode.py` / `matlab/t2_photodiode.m`. Finite hardware-timed
AI capture at 50kHz (finite, not continuous, so no reader thread competes with
the flip loop — see P4). Alternate a white patch in the diode's corner, fire
line A immediately after each flip returns, 300 flips. Post-hoc: debounced
rising-edge detection on both channels, auto-thresholded from each signal's own
floor and peak, then pair each TTL to the next photodiode edge within 2 refresh
periods.

**Prediction.** Median offset one refresh plus panel response, so roughly
5–20ms depending on the monitor — **and that is fine, it is constant**. SD under
0.5ms. PsychoPy and PTB within one frame of each other.

**Pass.** The criterion above.

**Blocked on.** A photodiode. Most NHP labs have one; otherwise a phototransistor
plus a BNC is a few dollars. **Confirm this exists before booking the rig** —
without it T2 cannot run and the day is largely wasted.

**Trap, already guarded.** If the edge-pairing window exceeds one frame period, a
dropped frame does not appear as a missing pair — it silently pairs with the
*next* frame's photodiode edge and reports a lag one refresh too long. That turns
the most important failure mode into a plausible-looking number. `pair_edges`
takes `max_lag_s = 2 × refresh` and there is a self-check pinning the behaviour.

---

## T3 — timing under realistic load `open`

**Concern.** T1 and T2 measure an idle loop. Real tasks draw images, poll gaze,
and append rows. If timing only holds when nothing else happens, it does not hold.

**Method.** T1/T2 protocol with the loop doing per-frame work: draw a
full-screen image, poll gaze (mouse off-rig, EyeLink on-rig), append an event
row to an in-memory list. Explicitly **no disk IO in the loop** (P1) — that is
the discipline being validated, and the comparison against a version that does
write per-frame is worth running once to show why the rule exists.

**Prediction.** This is where drops appear, if anywhere. Expect "excellent, plus
N drops per 10k", and the work is driving N to zero.

**Pass.** Drops < 0.1%, jitter unchanged from T2.

**Not yet written.** Depends on what T1/T2 reveal about where the margin is.

---

## T4 — language microbenchmark `open` *ruling-out only*

**Concern.** Someone will ask "isn't Python slow?" That deserves a number rather
than a shrug.

**Method.** `t4_micro.py` / `matlab/t4_micro.m`. 1e6 iterations of scalar
branch-plus-arithmetic — the shape of a trial-loop state check. Pure Python and
pure MATLAB loops, no vectorisation on either side, since vectorising would
measure C and not the interpreter.

**Prediction.** ~60ns/iteration in CPython. MATLAB comparable or slower; both
are interpreted. A 60Hz frame fits ~270,000 such iterations; a trial loop runs a
few hundred per frame.

**Framing — important.** This is **not** the argument for the migration. Interpreter
overhead sits last among jitter sources, four to five orders of magnitude below
the display path. Present it as one slide that rules the question out, and lead
with T2. Leading with T4 would be measuring the wrong thing convincingly.

---

## T5 — mitigation ablation `open`

**Concern.** `../psychopy_template/spec/PRINCIPLES.md` mandates `gc.freeze/disable` and `core.rush`. Are
they earning their place, or cargo cult?

**Method.** T3 with each toggled: `--no-rush`, `--no-gc-off`. Flags already exist
on `t1_flip.py`.

**Prediction.** GC off removes rare multi-ms outliers rather than shifting the
median. `rush` reduces the tail. Both show up in p99 and max, not in the median —
which is itself the argument for reporting percentiles instead of mean±SD.

**Pass.** Not pass/fail. If a mitigation does nothing measurable, delete it from
the principles rather than keeping it on faith.

---

## Open questions blocking a clean run

- Rig PC specs: Windows version, GPU, monitor model and refresh rate. Numbers
  are not interpretable without these recorded alongside.
- Photodiode availability. Blocks T2. **Confirm before booking.**
- Which neural system receives the TTL, and how it timestamps input.
- Can both MATLAB and Python arms run in one session without re-cabling? If the
  BNC has to move between arms, the comparison weakens and the wiring change
  must be noted in the results.
