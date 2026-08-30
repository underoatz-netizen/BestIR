# BestIR DSP Extension Implementation Plan (Superseded)

> This document has been superseded by
> `docs/IR_COMPARISON_AND_MATCHING_PLAN_V2.md`, which incorporates the clarified
> CSD, impulse-envelope, spectrogram, phase/group-delay, pair-blending, and
> response-matching requirements. Keep this file only as historical context.

**Status:** Proposed — architecture approval required before implementation  
**Date:** 2026-08-30  
**Decider:** Project owner  
**Audience:** AI coding agents implementing BestIR extensions  

## 1. Outcome

Add all four requested capabilities without changing legacy behavior:

1. IR phase analysis and pair alignment.
2. T60/decay analysis with validity reporting.
3. Non-destructive IR filtering, alignment, and export.
4. Advanced multi-objective DSP/tone matching.

The existing application remains a supported baseline. New functionality is
implemented as an opt-in extension layer and connected through adapters. The
legacy scanner, cache, `AnalysisResult`, ranking, UI, launcher, and packaged
executable must keep their current behavior until the final rollout is
explicitly approved.

## 2. Authoritative Baseline

Current code boundaries:

- `app/core/analysis.py`: 96-point, log-frequency magnitude analysis and legacy
  tone metrics.
- `app/core/matching.py`: mean-aligned magnitude RMS scoring.
- `app/core/tonematch.py`: DI + IR magnitude-domain prediction.
- `app/core/cache.py`: legacy JSON cache, version 4.
- `app/ui/main_window.py`: current application composition root.
- `app/ui/workers.py`: legacy scan and record threads.
- `bestir.py`, `run.bat`, `BestIR.spec`: current launch/package path.

Verified baseline on 2026-08-30:

```text
python -m pytest tests -q --basetemp=E:\Projects\BestIR\.codex-pytest-basetemp -p no:cacheprovider
20 passed

python -m app.main --selftest
BestIR selftest OK
```

The workspace was not a Git repository when inspected. Before implementation,
the owner should create a recoverable snapshot or initialize version control.
No agent should assume rollback is available until that is done.

## 3. Non-Negotiable Compatibility Rules

1. Do not modify files under `app/core/` or `app/ui/` during work packages
   WP-01 through WP-06.
2. Do not change `AnalysisResult`, `CACHE_VERSION`, existing cache payloads,
   `score_curve`, `rank_records`, or any legacy global state.
3. Do not overwrite source IR files. Processed files always go to a separate
   destination and use collision-safe names.
4. Treat all legacy objects and NumPy arrays received from adapters as
   read-only. Copy before any DSP operation that can mutate data.
5. Extension features are disabled by default. When disabled, no extra raw
   audio loading, scanning, cache writes, or ranking overhead is allowed.
6. Unsupported or statistically invalid measurements return an explicit
   validity status; they must not return plausible-looking fabricated values.
7. Existing tests must pass before and after every work package.
8. Changes to the default launcher or the existing PyInstaller spec require a
   separate final approval after the opt-in extension has passed acceptance.

## 4. Architecture Decision

### Decision

Use an additive extension package with immutable contracts, a legacy adapter,
a separate sidecar cache, pure DSP services, and an optional subclassed UI.

```text
Legacy AnalysisResult / selected path
                 |
                 v
        LegacyIRAdapter (read-only)
                 |
                 v
       AudioBuffer + SourceKey contracts
          |          |          |
          v          v          v
       Phase      Decay      Processor
          \          |          /
           \         v         /
            Advanced Matching
                    |
                    v
          Extension Sidecar Cache
                    |
                    v
      ExtendedMainWindow(MainWindow)
            optional launcher only
```

New package layout:

```text
app/extensions/
    __init__.py
    contracts.py
    adapters.py
    cache.py
    service.py
    phase.py
    decay.py
    processing.py
    processing_export.py
    advanced_matching.py
    profiles.py
    ui/
        __init__.py
        main_window_adapter.py
        analysis_dock.py
        processing_panel.py
        matching_panel.py
        workers.py
app/extended_main.py
bestir_extended.py
BestIRExtended.spec
tests/extensions/
```

### Options Considered

| Option | Compatibility | Complexity | Decision |
|---|---:|---:|---|
| Add fields and logic directly to `AnalysisResult` and legacy scanner | Low | Medium | Rejected |
| Add plugin hooks to the current `MainWindow` first | Medium | High | Deferred; it changes core architecture |
| Sidecar extension with adapters and optional subclassed UI | High | Medium | Selected |
| Build a separate unrelated application | High | High | Rejected; duplicates too much BestIR behavior |

### Consequences

- Legacy behavior stays independently testable and packageable.
- Phase/decay data can evolve without invalidating legacy cache version 4.
- The optional UI can reuse selection, library, and audition behavior through
  public widget signals and attributes.
- Some duplicated launcher/composition code is accepted temporarily. It can be
  consolidated only after the extension path is proven.

## 5. Shared Contracts and Data Policy

Implement these contracts first in `app/extensions/contracts.py` as frozen
dataclasses. Names may change only before WP-02 starts.

```python
SourceKey(path, mtime_ns, size)
AudioBuffer(source, sample_rate, samples, channels)
AnalysisStatus(valid, reason, warnings)
PhaseAnalysisConfig(...)
PhaseResult(...)
PairAlignmentResult(...)
DecayAnalysisConfig(...)
DecayBandResult(...)
DecayResult(...)
EQBand(kind, frequency_hz, gain_db, q)
IRProcessingConfig(...)
ProcessingReport(...)
MatchingTarget(...)
MatchingWeights(...)
ScoreBreakdown(...)
RankedCandidate(record, breakdown)
```

Contract requirements:

- `AudioBuffer.samples` always has shape `(frames, channels)`, dtype float64,
  finite values only, and is marked non-writeable by the adapter.
- Time is stored in seconds and samples; frequency is Hz; level is dB.
- Result arrays use native NumPy arrays in memory but serialize as float32
  blobs or bounded lists in the sidecar cache.
- All configs are hashable and serializable so the cache key includes the full
  algorithm configuration.
- Every result includes an `algorithm_version` and `AnalysisStatus`.
- No extension result is attached to or stored inside `AnalysisResult`.

`LegacyIRAdapter` in `app/extensions/adapters.py` is the only component allowed
to translate a legacy record/path into `AudioBuffer`. It must:

1. Resolve and stat the exact path.
2. Load with the existing public `load_ir` function.
3. Validate shape, sample rate, length, and finite values.
4. Copy and mark samples read-only.
5. Produce `SourceKey(path, mtime_ns, size)` for invalidation.

## 6. Sidecar Cache

Create `app/extensions/cache.py` using Python `sqlite3`; do not touch the legacy
JSON cache. Recommended database:

```text
%LOCALAPPDATA%\BestIR\extensions-v1.sqlite3
```

Primary key:

```text
(canonical_path, mtime_ns, size, feature_name, algorithm_version, config_hash)
```

Store only derived bounded data. Never cache the raw waveform. Use transactions,
parameterized statements, WAL mode where supported, and atomic commits. A cache
failure must degrade to recomputation and must not prevent legacy scanning.

## 7. Work Packages and Dependencies

```text
WP-00 Baseline/snapshot
        |
WP-01 Contracts + adapter + sidecar cache + facade
        |---------------------------|
        v             v             v
WP-02 Phase       WP-03 Decay    WP-04 Processing/export
        |             |             |
        +-------------+-------------+
                      v
             WP-05 Advanced matching
                      |
                      v
             WP-06 Optional UI adapter
                      |
                      v
             WP-07 Packaging/QA/rollout
```

WP-02, WP-03, and most of WP-04 may run in parallel after WP-01 contracts are
frozen. WP-05 depends on phase and decay result contracts. WP-06 starts only
after all pure DSP APIs are stable.

### WP-00 — Establish Safety Baseline

Ownership: repository setup and verification only.

Tasks:

1. Create a Git repository or a dated recoverable copy with owner approval.
2. Record Python, NumPy, SciPy, SoundFile, and PySide6 versions.
3. Run the 20 legacy tests and the headless self-test.
4. Record a checksum or untouched-file list for `app/core/` and `app/ui/`.
5. Create unique writable test temp directories per work package.

Gate: baseline evidence is saved; no source behavior is changed.

### WP-01 — Extension Foundation

Ownership:

- `app/extensions/contracts.py`
- `app/extensions/adapters.py`
- `app/extensions/cache.py`
- `app/extensions/service.py`
- `tests/extensions/test_contracts.py`
- `tests/extensions/test_adapter.py`
- `tests/extensions/test_extension_cache.py`

`ExtensionAnalysisService` is a facade that accepts legacy records but delegates
all work to pure services. It must support dependency injection of loader and
cache for deterministic tests.

Acceptance:

- Adapter does not mutate legacy records or input arrays.
- Cache invalidates on path metadata, config, feature, and algorithm version.
- Corrupt/unwritable cache falls back safely.
- Concurrent reads and serialized writes do not corrupt the database.
- Legacy test suite remains unchanged and green.

### WP-02 — Phase Analysis and Pair Alignment

Ownership:

- `app/extensions/phase.py`
- `tests/extensions/test_phase.py`

Required outputs:

- Detected onset per channel in samples and milliseconds.
- Peak polarity and confidence.
- Onset-compensated unwrapped phase on a documented frequency grid.
- Group delay with a magnitude-based reliability mask.
- Minimum-phase reference and excess-phase curve where mathematically valid.
- A/B alignment: integer delay, fractional delay, polarity recommendation,
  normalized correlation, and phase-difference curve.

Algorithm requirements:

1. Remove DC on a private copy.
2. Detect onset using a relative threshold plus local energy confirmation.
3. Window the useful IR region explicitly; do not silently use file padding.
4. Estimate phase by FFT and unwrap only reliable bins.
5. Compute group delay from phase derivative with controlled smoothing.
6. Use normalized cross-correlation or GCC-PHAT for coarse pair alignment, then
   parabolic interpolation for fractional-sample refinement.
7. For differing sample rates, resample a comparison copy to an explicit common
   rate; preserve native-rate single-file results.

Validation fixtures:

- Dirac impulses with known integer delays.
- Broadband IR with known fractional delay.
- Polarity-inverted copies.
- Low-pass and band-limited signals with unreliable-bin masking.
- Mono/stereo and 44.1/48/88.2/96 kHz inputs.

Acceptance:

- Integer delay and polarity are exact on synthetic fixtures.
- Fractional delay error is no greater than 0.25 sample on the agreed broadband
  fixture.
- Group delay for a pure delay matches the injected delay within the documented
  FFT/window tolerance.
- Silence and insufficient-energy input return invalid status, not NaN-heavy
  successful results.

### WP-03 — T60 and Decay Analysis

Ownership:

- `app/extensions/decay.py`
- `tests/extensions/test_decay.py`

Do not reinterpret the existing `effective_length_ms` as T60. Implement proper
Schroeder energy decay analysis on raw IR data.

Required outputs:

- Broadband and fractional-octave decay results.
- EDT, T20, T30, extrapolated T60, fitted slope, R-squared, usable dynamic
  range, noise-floor estimate, and validity reason.
- Optional clarity metrics C50/C80 and center time when the input supports them.
- Truncation/noise warnings.

Algorithm requirements:

1. Detect onset and remove pre-onset noise from the integration region.
2. Estimate the noise floor and compensate or truncate the Schroeder integral.
3. Fit EDT over 0 to -10 dB, T20 over -5 to -25 dB, and T30 over -5 to -35 dB.
4. Extrapolate T60 only from a valid regression and expose the source fit.
5. Use stable SOS fractional-octave filters whose bands are below Nyquist.
6. Reject poor fits using explicit dynamic-range and R-squared thresholds.

Important domain rule: short guitar cabinet IRs often do not contain a diffuse
reverberant decay. The UI/result must say `insufficient decay`, `truncated`, or
`not a valid reverberation measurement` when appropriate.

Acceptance:

- Synthetic exponential decays recover known T60 within 5% under clean
  conditions.
- Added stationary noise does not produce a falsely long valid T60.
- Short/truncated/silent IRs return deterministic invalid statuses.
- All band filters remain stable at supported sample rates.

### WP-04 — Non-Destructive IR Processing and Export

Ownership:

- `app/extensions/processing.py`
- `app/extensions/processing_export.py`
- `tests/extensions/test_processing.py`
- `tests/extensions/test_processing_export.py`

Immutable `IRProcessingConfig` should cover:

- Optional target sample rate.
- Mono/stereo channel policy.
- DC removal.
- Polarity flip.
- Integer/fractional delay alignment.
- High-pass and low-pass filters.
- Parametric peak, low-shelf, and high-shelf EQ bands.
- Minimum-phase or linear-phase processing mode with documented latency and
  pre-ringing consequences.
- Onset trim, target length, tail window/fade.
- Normalization mode (`none`, `peak`, or explicit gain).
- Output subtype/bit depth and optional dither where applicable.

Processing order must be explicit and tested:

```text
load/validate -> private copy -> channel policy -> resample -> DC/polarity
-> delay/phase operation -> filters/EQ -> trim/length/window
-> gain/normalization -> finite/peak guard -> atomic export
```

Export rules:

- Never overwrite source or existing output by default.
- Write a temporary file in the destination, validate by reopening it, then
  atomically commit to a collision-safe final filename.
- Return a `ProcessingReport` containing input/output metadata, gain, peak,
  RMS, clipping status, applied operations, warnings, and final path.
- Cancelled/failed jobs remove only their own temporary file.

Acceptance:

- A no-op float export is numerically equivalent within the selected format's
  tolerance.
- Cutoff/EQ fixtures meet documented magnitude-response tolerances.
- Delay, polarity, sample rate, channel count, length, and normalization are
  verified from the reopened output file.
- Existing files are preserved and name collisions are deterministic.
- No output contains NaN, infinity, or unintended clipping.

### WP-05 — Advanced Multi-Objective Matching

Ownership:

- `app/extensions/advanced_matching.py`
- `app/extensions/profiles.py`
- `tests/extensions/test_advanced_matching.py`

Keep legacy ranking intact. Implement `LegacyMagnitudeScorerAdapter` that calls
the existing `score_curve` for exact compatibility, then add a new scorer that
returns immutable `RankedCandidate` wrappers instead of mutating
`AnalysisResult.score`.

Matching dimensions:

- Magnitude-shape distance with configurable frequency weighting.
- DI-to-target output magnitude prediction.
- Phase/group-delay similarity where a phase target exists.
- Decay/EDT/T20/T30 similarity where valid targets exist.
- Low-frequency resonance/tightness and transient/onset penalties.
- Optional instrument profiles for standard guitar, baritone, 7/8 string,
  bass, and custom frequency ranges.

Scoring rules:

1. Each component returns raw units plus a normalized loss.
2. Weights are explicit and normalized; no hidden weighting.
3. Missing optional metrics follow a declared policy (`exclude-and-renormalize`
   or `reject`). Never silently treat missing as zero error.
4. Tie-breaking is deterministic by canonical path.
5. Return a complete `ScoreBreakdown` for explainability.
6. Default `legacy` mode must reproduce current magnitude scores exactly.

Acceptance:

- Legacy parity differs by no more than `1e-12` on the existing matching
  fixtures.
- Changing one weight changes only the intended component contribution.
- Invalid decay/phase data follows the configured missing-data policy.
- Ranking never mutates the source records.
- Results are deterministic across repeated runs.

### WP-06 — Optional UI and Worker Integration

Ownership:

- `app/extensions/ui/*`
- `app/extended_main.py`
- `bestir_extended.py`
- `tests/extensions/test_extended_ui.py`

Implement `ExtendedMainWindow(MainWindow)` without editing `MainWindow`.
Connect to existing `library_panel.selection_changed`, use selected records as
read-only inputs, and add an extension dock or tab set containing:

1. Phase/Alignment view.
2. Decay/T60 view with validity badges.
3. Processing controls, preview summary, and export confirmation.
4. Advanced matching controls and score-breakdown table.

Use a separate extension worker with:

- Request IDs so stale results cannot update a newer selection.
- Cooperative cancellation between files/stages.
- Progress and structured error signals.
- No GUI object access from the worker thread.
- Bounded concurrency and no retained full-library raw audio.

Add `app/extended_main.py` and `bestir_extended.py` as opt-in launch paths. The
legacy `app.main` and `bestir.py` remain untouched.

Acceptance:

- Legacy application still launches and passes its GUI smoke workflow.
- Extended application launches with no input/output audio device.
- Selection changes cannot display stale analysis.
- Cancelling processing produces no committed output.
- All four features can be exercised from the optional UI.

### WP-07 — Packaging, Performance, Documentation, and Rollout

Ownership:

- `BestIRExtended.spec`
- extension user documentation
- benchmark scripts and release checklist

Tasks:

1. Build a separate `BestIRExtended.exe`; do not replace `BestIR.exe`.
2. Verify packaged operation with no Python installation.
3. Benchmark cold and cached extension analysis on representative mono/stereo
   IRs and a large library.
4. Confirm extension-disabled startup/scan overhead is effectively zero.
5. Test 44.1, 48, 88.2, and 96 kHz; mono and stereo; short, long, silent,
   malformed, clipped, and noisy inputs.
6. Document phase conventions, T60 validity, filter phase modes, score units,
   and export safety.
7. Run a listening-oriented A/B check after numerical verification.

Only after all gates pass should the owner decide whether the extension
launcher becomes the default. That decision is a separate small change and
must retain a rollback path to `app.main`.

## 8. Test Gates for Every Work Package

Each AI coder must provide command output for all applicable gates:

```powershell
python -m pytest tests -q --basetemp=E:\Projects\BestIR\.test-tmp\<work-package> -p no:cacheprovider
python -m app.main --selftest
```

Also run focused tests first:

```powershell
python -m pytest tests\extensions\test_<feature>.py -q --basetemp=E:\Projects\BestIR\.test-tmp\<work-package>-focused -p no:cacheprovider
```

For the GUI packages, run both legacy and extension offscreen smoke tests. The
current `tests/gui_smoke.py` uses the system temp directory, so run it in an
environment with a writable system temp or adapt only the new extension smoke
test to accept an explicit writable temp directory.

Verification order:

1. Contract and numerical unit tests.
2. Error/edge-case tests.
3. Full legacy regression suite.
4. Headless self-test.
5. Offscreen GUI smoke test.
6. Real-file integration test on a small copied fixture set.
7. Benchmark and packaged executable test when applicable.

## 9. AI Coding Handoff Protocol

Give an AI coder only one work package at a time. Use this prompt:

```text
Read docs/DSP_EXTENSION_IMPLEMENTATION_PLAN.md completely. Implement only
<WP-ID>. Treat the current worktree as authoritative. Do not modify app/core,
app/ui, legacy tests, bestir.py, run.bat, or BestIR.spec. Preserve other agents'
changes. Start by verifying the prerequisite work-package APIs and baseline.
Use immutable contracts and pure DSP functions. Add focused tests for every
acceptance criterion, run the full legacy suite and self-test, and report exact
files changed, mathematical conventions, test commands/results, unresolved
risks, and the next unlocked work package. Stop if the prerequisite contracts
are missing or incompatible; do not invent a second interface.
```

Agent coordination rules:

- WP-01 owns all contracts; later agents request contract changes through the
  coordinator instead of editing them independently.
- WP-02, WP-03, and WP-04 have disjoint file ownership and can run in parallel.
- WP-05 starts after the coordinator validates WP-02 and WP-03 result schemas.
- WP-06 starts after all pure DSP APIs are frozen.
- One agent/coordinator runs the final combined suite and resolves integration;
  individual agents must not rewrite another package to make their tests pass.

## 10. Completion Definition

The project is complete only when:

- All four capabilities work through the opt-in application.
- Every stated numerical and safety acceptance criterion has direct test
  evidence.
- All legacy tests and legacy GUI workflows still pass unchanged.
- The legacy cache and data model remain compatible.
- Source IR files and unrelated user data are never modified.
- The extended executable builds and runs independently.
- Documentation explains limitations, especially phase reference conventions
  and invalid T60 cases.
- The owner has reviewed the opt-in build before any default-launcher switch.
