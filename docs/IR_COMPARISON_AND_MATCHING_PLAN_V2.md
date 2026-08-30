# BestIR IR Comparison and Response Matching Plan — V2

**Status:** Proposed — architecture approval required before implementation  
**Date:** 2026-08-30  
**Decider:** Project owner  
**Audience:** AI coding agents and integration coordinator  
**Supersedes:** `docs/DSP_EXTENSION_IMPLEMENTATION_PLAN.md`  

## 1. Product Intent

BestIR's existing magnitude/EQ screening is complete and accepted. It remains
the first-stage tone selector and must not be rewritten.

The new problem is narrower and more useful: two IRs can have nearly identical
smoothed magnitude responses but behave differently in time, resonance decay,
phase, and a blend. BestIR needs a visual comparison workbench and a second-stage
response matcher that exposes and scores those differences.

The target workflow is:

```text
Existing EQ/tone target
        |
        v
Legacy magnitude shortlist (fast, unchanged)
        |
        v
Response fingerprint ranking (time/decay/phase scalars)
        |
        v
Select IR A + IR B
        |
        v
Compare Workbench
  - Impulse/envelope
  - CSD waterfall
  - Spectrogram/difference map
  - Phase/group delay
  - Predicted aligned blend
        |
        v
Choose one IR, choose a blend partner, or export a processed copy
```

## 2. Functional Requirements

### 2.1 CSD Waterfall

Provide a three-dimensional Cumulative Spectral Decay view for examining
frequency-dependent tail energy. The primary use is distinguishing low-end
resonance and decay between tone-similar IRs.

The view must support:

- IR A, IR B, and A-minus-B comparison.
- Log-frequency axis, time axis in milliseconds, and relative level in dB.
- Adjustable displayed frequency range and dynamic range.
- Low-end focused profile with enough window length to resolve 20–500 Hz.
- Frequency cursor linked to the spectrogram and phase plots.
- Quantitative band-decay readouts; the 3D surface is not the only evidence.

### 2.2 Time-Domain Waveform and Impulse Envelope

Show the raw onset-aligned impulse and one or more envelopes. Use it to compare
transient attack, pre-arrival energy, peak timing, early energy, and tail shape.

Required measurements:

- Onset sample/time and detection confidence.
- Peak sample/time and polarity.
- 10–90% envelope rise time where meaningful.
- Time from onset to peak.
- Early-energy ratios such as 0–1 ms, 0–5 ms, and early/late energy.
- Energy centroid/center time.
- Crest factor and tail end relative to the detected noise floor.

### 2.3 Spectrogram Heatmap

Provide A, B, and difference heatmaps to reveal when resonant energy persists.
The primary use is distinguishing a static magnitude bump from temporally
persistent boxiness, low-frequency bloom, or high-frequency fizz.

The view must support:

- Log-frequency display and a shared dB color scale.
- Linked time/frequency cursor.
- Switchable low-end, balanced, and transient-resolution profiles.
- Configurable analysis bands instead of a hard-coded definition of boxiness.
- Quantitative persistence scores alongside the heatmap.

### 2.4 Phase Response, Group Delay, and Blend Prediction

Provide onset-compensated phase and group delay only in reliable frequency bins.
For a selected pair, report alignment and polarity suggestions, then predict the
frequency response of the blend before the user changes a signal chain.

Required outputs:

- Unwrapped onset-compensated phase.
- Group delay in milliseconds or samples.
- Minimum-phase reference and excess phase where valid.
- Magnitude-derived reliability mask.
- Pair delay, fractional delay, polarity relation, and correlation confidence.
- Magnitude-weighted phase difference.
- Predicted blend magnitude for adjustable A/B ratio.
- Comb-cancellation/risk summary and frequency locations.

### 2.5 Response-Aware Search

Keep the existing EQ scorer as stage one. Add response constraints and weighted
ranking as stage two. Users must be able to request, for example:

- Similar tone, tighter/shorter low-end decay.
- Similar tone, faster transient.
- Similar tone, less persistent 180–500 Hz energy.
- Similar tone, smoother group delay.
- Best phase-compatible partner for the currently selected IR.
- Best candidate to reach a selected reference's complete response fingerprint.

Every advanced result must explain why it ranked where it did.

## 3. Non-Functional Requirements

1. Legacy scan, cache, ranking, tone match, audition, export, UI, launcher, and
   executable retain their current behavior.
2. Extension-disabled operation performs no extra raw loading or DSP work.
3. Full CSD and spectrogram matrices are computed only for selected IRs or an
   explicit small shortlist. Whole-library scans cache scalar fingerprints only.
4. All heavy processing runs outside the Qt GUI thread and supports stale-result
   rejection and cooperative cancellation.
5. Raw waveforms are not retained for the whole library or stored in the cache.
6. Mono, stereo, 44.1, 48, 88.2, and 96 kHz inputs are first-class cases.
7. Phase conventions, time origin, channel policy, normalization, windowing, and
   invalid-data rules are visible to the user and serialized with cached results.
8. A missing or invalid response metric is never silently treated as a perfect
   match.
9. Source files are immutable; optional processed exports are collision-safe and
   atomic.

## 4. Architecture Decision Record

### Context

The legacy `AnalysisResult` contains a 96-point smoothed magnitude curve and a
400-point display envelope. It does not retain complex FFT data, raw phase, or
enough time-frequency detail to reconstruct CSD, spectrogram, accurate attack,
or group delay. These analyses must load raw IR audio.

Computing large time-frequency matrices for every file would slow scanning and
inflate the cache. Mutating the legacy result/cache would violate compatibility.

### Decision

Build an additive extension with three cost tiers:

```text
Tier 0: existing magnitude metrics       all IRs, unchanged, legacy cache
Tier 1: scalar ResponseFingerprint       shortlist/on demand, sidecar cache
Tier 2: display matrices + pair analysis selected A/B only, memory cache
```

Use a single canonical preprocessing service so all views agree about onset,
time zero, channel handling, normalization, and useful tail bounds.

### Options Considered

| Option | Scan cost | Compatibility | Diagnostic value | Decision |
|---|---:|---:|---:|---|
| Add all arrays to legacy `AnalysisResult` | High | Low | High | Rejected |
| Precompute CSD/spectrogram for every IR | Very high | Medium | High | Rejected |
| Compute every new view only after selection | Low | High | High | Incomplete alone; no response ranking |
| Cache scalar fingerprints, render matrices for A/B only | Low/controlled | High | High | Selected |

### UI Rendering Decision

Separate DSP matrices from rendering. Prefer `pyqtgraph.opengl` for a true 3D
CSD surface when OpenGL is available. Provide a deterministic stacked-ridge or
2D heatmap fallback when OpenGL/PyOpenGL is missing or unsupported. The absence
of 3D acceleration must not stop the application.

### Consequences

- Tone ranking remains fast and familiar.
- First advanced ranking of a shortlist may take additional time; subsequent
  runs use the sidecar fingerprint cache.
- A/B views can retain high detail without bloating persistent storage.
- All plots share identical preprocessing, making visual differences meaningful.
- An optional OpenGL dependency is isolated behind a renderer interface.

## 5. Additive Package Layout

Do not modify `app/core/`, `app/ui/`, `bestir.py`, `run.bat`, or `BestIR.spec`
during the extension work packages.

```text
app/extensions/
    __init__.py
    contracts.py
    adapters.py
    cache.py
    preprocessing.py
    envelope.py
    time_frequency.py
    csd.py
    spectrogram.py
    phase.py
    decay.py
    fingerprint.py
    pair_compare.py
    advanced_matching.py
    profiles.py
    processing.py
    processing_export.py
    service.py
    ui/
        __init__.py
        main_window_adapter.py
        compare_workbench.py
        summary_panel.py
        waveform_view.py
        csd_view.py
        spectrogram_view.py
        phase_blend_view.py
        response_search_panel.py
        workers.py
        renderers/
            csd_base.py
            csd_opengl.py
            csd_fallback.py
app/extended_main.py
bestir_extended.py
BestIRExtended.spec
tests/extensions/
```

The optional `ExtendedMainWindow(MainWindow)` connects to the existing public
`library_panel.selection_changed` signal. It adds the Compare Workbench without
editing the legacy window.

## 6. Canonical Contracts

`app/extensions/contracts.py` owns all frozen dataclasses. Freeze these APIs
before feature agents work in parallel.

```text
SourceKey
AudioBuffer
AnalysisStatus
PreprocessingConfig
PreparedIR
EnvelopeConfig / EnvelopeResult
TimeFrequencyConfig
CSDResult
SpectrogramResult
PhaseConfig / PhaseResult
DecayConfig / DecayResult
ResponseFingerprint
PairComparisonConfig / PairComparisonResult
BlendConfig / BlendPrediction
ResponseTarget / MatchingWeights
ScoreComponent / ScoreBreakdown / RankedCandidate
IRProcessingConfig / ProcessingReport
```

Key invariants:

- Samples use float64 shape `(frames, channels)` and finite values only.
- Adapter output arrays are non-writeable; DSP functions copy before mutation.
- Native channel phase is retained. Power-averaged channels may be used for
  magnitude-only displays but never for pair phase decisions.
- Configs include algorithm versions and serialize deterministically for cache
  keys.
- Result arrays explicitly state axes, units, normalization reference, and valid
  masks.
- No result is attached to or stored inside legacy `AnalysisResult`.

## 7. Canonical Signal Preparation

Every analysis begins in `preprocessing.py`:

1. Load through `LegacyIRAdapter` using the record path.
2. Validate sample rate, shape, length, finite values, and file signature.
3. Copy, remove DC if configured, and preserve the original peak/RMS metadata.
4. Detect onset using a relative peak threshold plus local-energy confirmation.
5. Estimate pre-onset noise and useful tail bound.
6. Establish raw time and onset-relative time axes.
7. Apply only display normalization; never confuse it with source level.
8. Preserve per-channel data and expose an explicit magnitude-only channel
   aggregate when requested.

Pair alignment is a derived comparison view. It must not replace raw timing.
The UI exposes `Raw`, `Onset aligned`, and `Suggested blend alignment` modes.

## 8. DSP Specifications

### 8.1 Impulse Envelope and Transient Metrics

Return the raw waveform plus:

- Analytic/Hilbert envelope for fine structure.
- Short-window RMS envelope for stable energy comparisons.
- Optional peak-hold envelope for display only.

Metrics are measured on onset-relative time. Gain-independent metrics use a
documented normalized envelope; absolute peak/RMS remain separate metadata.

Do not present a 10–90% rise time as valid when the impulse is a one-sample peak
or when smoothing dominates the measurement. Return a status/reason instead.

### 8.2 CSD Waterfall

CSD and spectrogram are different products and must not share an ambiguous
label. CSD uses progressively later tail-gated transforms:

```text
H_k(f) = FFT{ h(t) * tail_window(t; start=t_k, end=t_tail) }
CSD(f, t_k) = 20 log10(|H_k(f)| / |H_0(f)|)
```

Implementation requirements:

- Taper gate boundaries to limit leakage.
- Use a fixed documented frequency grid and mask bins below the reliability
  floor.
- Support low-end, balanced, and high-resolution profiles.
- Use multi-resolution analysis or explicit long low-end windows; at 20 Hz one
  cycle is 50 ms, so a short FFT cannot justify detailed low-frequency claims.
- Record effective resolution in every result.
- Compute band-decay curves from energy, not from the visual surface alone.

Primary scalar metrics:

- Low-end decay-to-10/20/30 dB where supported.
- Decay slope and fit confidence in configurable bands.
- Resonance persistence and ridge frequency/Q.
- Low-frequency late/early energy ratio.

### 8.3 Spectrogram

Use fixed local windows rather than cumulative tails. Provide named profiles:

- `Low-end`: long windows, high frequency resolution, lower time resolution.
- `Balanced`: general comparison.
- `Transient`: short windows, high time resolution.

A future multi-resolution merge may combine profiles onto one log-frequency
grid, but each contributing window/resolution must remain inspectable.

Boxiness is not simply a 300 Hz magnitude boost. Define a configurable
`PersistenceBand` with target and neighbor bands. A default guitar-oriented
profile may compare persistent energy around 180–500 Hz against adjacent bands,
but the user can edit all boundaries. Return:

- Persistent-band excess in dB.
- Duration above threshold.
- Dominant resonance frequency and estimated Q.
- Difference from adjacent-band decay.
- Validity/confidence.

Use the same mechanism for low-end bloom and high-frequency fizz persistence.

### 8.4 Phase and Group Delay

Absolute phase is inseparable from time origin. Show both raw and
onset-compensated phase and label them clearly.

Required computation:

1. FFT each channel separately using the canonical useful window.
2. Unwrap only bins that pass the magnitude reliability threshold.
3. Compute group delay:

```text
group_delay_seconds(f) = -(1 / 2*pi) * d(phi) / df
```

4. Smooth phase derivative only with a documented bandwidth.
5. Optionally derive minimum-phase response from log magnitude and report excess
   phase; reject cases that violate numerical prerequisites.
6. Never join unreliable phase gaps as if they were valid measurements.

Pair alignment uses normalized cross-correlation or GCC-PHAT for coarse delay,
parabolic refinement for fractional delay, and an explicit polarity test.

### 8.5 Blend Prediction

For gains `gA`, `gB`, delay `tau`, and polarity `s`:

```text
Hmix(f) = gA * HA(f) + gB * s * HB(f) * exp(-j*2*pi*f*tau)
```

Calculate this from complex responses, not by averaging magnitude curves.
Provide raw, onset-aligned, and suggested-alignment predictions. Sweep optional
blend ratios and report:

- Worst cancellation in the selected band.
- RMS deviation from the power-normalized expectation.
- Frequencies of major notches.
- A magnitude-weighted phase-compatibility score.
- Sensitivity to +/- one sample of alignment.

Validate the prediction against an actual time-domain aligned sum.

### 8.6 Decay and T60

Low-end decay from CSD/band energy is the primary cabinet-IR metric. Keep formal
Schroeder EDT/T20/T30/T60 as an additional result with strict validity checks.
Short cabinet IRs frequently lack a diffuse reverberant field or sufficient
dynamic range; report `not a valid reverberation measurement`, `truncated`, or
`noise dominated` rather than a fabricated T60.

### 8.7 Response Fingerprint

`ResponseFingerprint` contains bounded scalar features only:

```text
Tone:
  legacy magnitude curve reference + legacy score

Transient:
  onset confidence, time-to-peak, valid rise time, early-energy ratios,
  energy centroid, crest factor

Decay/resonance:
  low-end D10/D20/D30, band slopes, late/early energy,
  boxiness persistence, dominant ridge/Q, fizz persistence

Phase:
  per-band group-delay median/spread, excess-phase summaries,
  valid-frequency coverage
```

Every field carries validity. Store the fingerprint in the separate SQLite
sidecar cache keyed by file metadata, algorithm version, and config hash. Do not
persist full CSD/spectrogram matrices by default.

## 9. Matching Strategy: Tone First, Response Second

### Stage 1 — Legacy Tone Shortlist

Call the existing ranking unchanged. Select either top-K or all candidates
within a user-defined legacy dB-score threshold. This guarantees familiar EQ
behavior and prevents response metrics from hiding a poor tonal match.

### Stage 2 — Response Fingerprints

Compute/cache scalar fingerprints for the shortlist only. Rank with explicit
constraints and normalized weighted losses.

Example constraints:

- Legacy magnitude error <= 1.5 dB RMS.
- Low-end D20 <= selected threshold.
- Boxiness persistence <= selected threshold.
- Valid group-delay coverage >= selected percentage.

### Stage 3 — Explainable Ranking

Return immutable `RankedCandidate` wrappers with a score breakdown. Missing
metrics use an explicit policy: `exclude-and-renormalize` or `reject`. Never
mutate `AnalysisResult.score` in advanced mode.

Recommended transparent presets:

- `Tight`: short low-end decay and low late/early low-band energy.
- `Fast attack`: low time-to-peak and high early-energy ratio.
- `Low boxiness persistence`: low target-band excess and short persistence.
- `Smooth time response`: low group-delay spread in user-selected bands.
- `Blend safe`: lowest predicted cancellation after allowed alignment.
- `Reference response`: closest complete valid fingerprint to a selected IR.

Presets are editable starting weights/constraints, not undocumented tone labels.

### Stage 4 — Pair Search

Given IR A, find candidates with an acceptable tone score, then rank candidates
by predicted aligned blend compatibility. Return both the best partner and the
recommended delay/polarity/blend ratio with its risk report.

## 10. Compare Workbench UX

The extended application adds a `Compare A/B` workbench. Two selected library
rows populate A and B. Do not overload the existing single-selection inspector.

Tabs:

1. `Summary`: tone delta, transient/decay/phase metric table, validity, and the
   main reasons the IRs differ.
2. `Waveform`: raw waveform, envelopes, onset/peak markers, raw/aligned modes.
3. `CSD`: A, B, and difference surface with numeric band-decay panel.
4. `Spectrogram`: A, B, and difference heatmaps with persistence readouts.
5. `Phase & Blend`: magnitude, phase, group delay, suggested alignment,
   polarity, blend ratio, and comb-risk preview.

Interaction requirements:

- Shared frequency/time cursor across relevant views.
- A/B axes and color scales are locked by default.
- Raw and normalized modes are explicit.
- Difference plots use a symmetric scale and show which IR is positive.
- Expensive recomputation is debounced and cancellable.
- Result request IDs prevent an old computation from updating a newer pair.
- All failure/invalid states remain visible instead of leaving stale graphs.

## 11. UX/UI Reference Handoff — Boro UI for Apple Watch Apps

Reference supplied by the owner:

<https://www.figma.com/design/Zxfefb7M5L9xKTvihi85pz/Boro-UI-for-Apple-Watch-apps--Community-?node-id=0-1&t=5EKqt79eq0FYN36q-1>

The reference is a visual and interaction direction, not a pixel-copy target.
Publicly indexed descriptions characterize the kit as a clean, modern, dark,
futuristic Apple Watch UI with neumorphic/skeuomorphic depth and yellow accents.
The exact Figma file was not programmatically readable in this environment, so
exact dimensions, token names, and component IDs must be confirmed by the UI
agent if Figma access becomes available.

### What to Carry into BestIR

| Reference language | BestIR adaptation | Do not do |
|---|---|---|
| Dark layered surfaces | Keep the current `BG`, `SURFACE`, `SURFACE2`, and `BORDER` tokens; add a shallow raised-card hierarchy for the extension | Do not recolor the accepted legacy UI globally |
| Strong accent color | Use a gold/yellow accent for target/attention and distinct blue/green A/B plot colors | Do not use one neon color for every data series |
| Compact cards and status chips | Use metric cards, validity chips, and compact control rows in the Compare Workbench | Do not hide units or warnings behind icon-only controls |
| Tactile depth/shadows | Use subtle shadows and 1–2 px contrast edges on navigation/control cards | Do not add heavy shadows to heatmaps, axes, or scientific plots |
| Watch-like focused flows | Keep one primary action per state: `Compare`, `Align`, `Blend`, or `Export` | Do not force desktop users through a watch-style multi-screen wizard |
| High glanceability | Put A/B identity, tone score, validity, and key response deltas above plots | Do not replace detailed plots with decorative gauges |

### Desktop Shell Mapping

The current BestIR layout already has a useful three-region structure:

```text
Left: Library/table and filters
Center: Plot/workbench and analysis tabs
Right: Inspector, pair summary, and actions
```

The extension should preserve that structure. `ExtendedMainWindow(MainWindow)`
adds a compact context header above the workbench:

```text
[BestIR] [A: filename / tone score] [B: filename / tone score]
[Compare] [Align] [Raw | Onset aligned | Blend aligned] [Export report]
```

### Design Tokens for the Extension

Use existing `app/ui/styles.py` values as the compatibility baseline. Define
extension-only aliases rather than editing legacy tokens:

| Token | Initial direction | Usage |
|---|---|---|
| `compare-bg` | existing `BG` | Workbench background |
| `compare-surface` | existing `SURFACE` | Cards, controls, plot containers |
| `compare-surface-raised` | existing `SURFACE2` | Selected/raised card |
| `compare-text` | existing `TEXT` | Primary labels and values |
| `compare-text-dim` | existing `TEXT_DIM` | Units, secondary labels |
| `compare-target` | warm gold/yellow | Target, attention, blend ratio |
| `compare-a` | high-contrast blue | IR A and its markers |
| `compare-b` | high-contrast green | IR B and its markers |
| `compare-difference` | orange/red with symmetric scale | A-minus-B and risk warnings |
| `compare-valid` | existing `GREEN` | Valid/verified metric |
| `compare-invalid` | existing `RED` | Invalid/insufficient-data metric |

The final colors must be checked for contrast against the dark surfaces and
tested with color-vision simulation. Series identity must also be communicated
by labels, line styles, or markers—not color alone.

### Component and State Handoff

| Component | Required states | Behavior |
|---|---|---|
| `PairHeader` | empty, A-only, A+B, stale, loading | Shows source names, sample rates, channel policy, and request status |
| `MetricCard` | valid, warning, invalid, unavailable | Shows value, unit, confidence, and a short reason; never displays a bare `0` for missing data |
| `AnalysisTabBar` | default, active, disabled/loading | Tabs are Waveform, CSD, Spectrogram, Phase & Blend; disabled tabs explain why |
| `ViewToolbar` | raw, onset-aligned, blend-aligned | Controls shared display normalization, frequency range, dynamic range, and resolution profile |
| `PlotLegend` | A, B, difference, target | Labels remain visible while zooming and exporting |
| `ValidityChip` | valid, low-confidence, truncated, noise-dominated, invalid | Tooltip explains the acoustic limitation |
| `BlendControls` | no pair, pair available, alignment suggested, risky | Ratio/delay/polarity changes update prediction with debounce and cancellation |
| `ResponseSearchPanel` | legacy-only, fingerprint loading, ready, no valid candidates | Keeps tone constraints visible while showing response weights |
| `ExportReportDialog` | preview, writing, success, collision, error | Requires destination confirmation and reports exact source/config/signature |

### Interaction and Accessibility

- Keyboard order: library selection → pair assignment → toolbar → tab bar →
  plot controls → metric cards → export.
- All icon buttons have text/tooltips and accessible names.
- A/B assignment supports keyboard shortcuts and a visible swap action.
- Hover crosshair is supplemented by keyboard-selectable frequency/time values.
- Loading uses a non-blocking progress state; invalid data uses explanatory text.
- Long filenames are elided visually but available in a tooltip and report.
- Color, line pattern, labels, and marker shape jointly identify A/B/difference.
- Plot zoom/pan must not remove the legend, units, or validity indicator.
- Motion is restrained: 120–180 ms ease-out for card/tab state changes; no
  animated plot interpolation that implies unmeasured data.

### Responsive Behavior

Although the reference is watch-sized, BestIR is a desktop tool. Use these
desktop breakpoints for the extension:

| Width | Behavior |
|---|---|
| `>= 1280 px` | Three-region shell; summary cards and plot side by side where space permits |
| `900–1279 px` | Keep library and workbench; collapse right inspector into a tab/drawer |
| `< 900 px` | Single active region with A/B summary pinned above; never shrink plots below readable axis labels |

### Loading, Empty, and Error UX

- No pair: explain “Select two IRs to compare” and show the legacy tone workflow.
- A-only: allow assigning B from the library without clearing A.
- Different sample rates: show both native rates and the explicit comparison rate.
- Noisy/short IR: render the waveform but mark unsupported metrics as invalid.
- OpenGL unavailable: show the CSD fallback and a non-blocking capability note.
- Worker cancelled: restore the previous complete result, never a half-rendered mix.
- Cache failure: show a recoverable warning and recompute in memory.
- Export collision: offer a new collision-safe filename; never overwrite silently.

### UX Acceptance Gate

The UI agent must provide a static screenshot or offscreen render for:

1. Empty pair.
2. Two valid IRs with all tabs ready.
3. Valid A + invalid/truncated B.
4. Loading/cancelled response analysis.
5. Blend with a visible comb-risk warning.

Review criteria are glanceability, readable scientific units, clear A/B identity,
visible validity, keyboard navigation, dark-theme contrast, and no decorative
element obscuring data. Exact Figma measurements remain pending direct access.

## 12. Additional High-Value Features

These additions directly improve selection accuracy and should be included
after the four required views are numerically stable:

1. **Difference views:** waveform residual, spectrogram A-minus-B, CSD
   difference, phase difference, and group-delay difference.
2. **Audition parity:** convolve the same DI through A, B, and the predicted
   blend with identical level matching and alignment for visual/audible checks.
3. **Constraint filters:** allow users to set hard limits on attack, low-end
   decay, boxiness persistence, valid phase coverage, and comb risk.
4. **Sensitivity view:** show how blend response changes at delay offsets of
   -1, 0, and +1 sample; this catches fragile blends.
5. **Response similarity map:** later, use PCA/SVD on normalized fingerprints to
   show library clusters. Label axes as statistical components, not physical
   acoustic quantities.
6. **Measurement provenance:** export a JSON/CSV report containing configs,
   units, warnings, source signatures, and score breakdowns.

## 13. Work Packages and Efficient Dependency Order

```text
WP-00 Baseline + recoverable snapshot
        |
WP-01 Contracts + adapter + sidecar cache + service facade
        |
WP-02 Canonical preprocessing + envelope/transient
        |----------------------|
        v                      v
WP-03 CSD + spectrogram    WP-04 Phase + pair blend
        |                      |
        +----------+-----------+
                   v
WP-05 Decay + response fingerprint
                   |
WP-06 Advanced matching + pair search
                   |
WP-07 Compare Workbench UI + workers/renderers
        |----------------------|
        v                      v
WP-08 Optional processing/export     WP-09 QA/package/rollout
```

WP-03 and WP-04 can run in parallel after WP-02. WP-08 can begin after WP-04
contracts stabilize, but it is lower product priority than the comparison and
matching path.

### WP-00 — Baseline and Recovery

- Confirm or initialize version control with owner approval; the inspected
  workspace was not a Git repository.
- Record dependency versions and legacy test output.
- Preserve checksums of `app/core/` and `app/ui/`.
- Baseline gate: 20 legacy tests and `app.main --selftest` pass.

### WP-01 — Contracts, Adapter, Cache, Facade

Ownership:

```text
app/extensions/contracts.py
app/extensions/adapters.py
app/extensions/cache.py
app/extensions/service.py
tests/extensions/test_contracts.py
tests/extensions/test_adapter.py
tests/extensions/test_cache.py
```

Gate: immutable/read-only behavior, cache invalidation, corrupt-cache fallback,
no legacy changes.

### WP-02 — Canonical Preparation and Envelope

Ownership:

```text
app/extensions/preprocessing.py
app/extensions/envelope.py
tests/extensions/test_preprocessing.py
tests/extensions/test_envelope.py
```

Acceptance:

- Known onset recovered within one sample on clean fixtures.
- Gain changes do not alter normalized timing/energy-ratio metrics.
- Stereo channels remain distinct.
- Silent, clipped, non-finite, and too-short inputs return deterministic status.

### WP-03 — Time-Frequency Engine, CSD, Spectrogram

Ownership:

```text
app/extensions/time_frequency.py
app/extensions/csd.py
app/extensions/spectrogram.py
tests/extensions/test_csd.py
tests/extensions/test_spectrogram.py
```

Acceptance:

- A long-decay 80 Hz resonator ranks as longer than a short-decay fixture.
- A damped resonance inside the configured boxiness band is detected at the
  correct band/time while neighbor-band fixtures are not falsely labeled.
- Identical signals/configs produce zero difference matrices within tolerance.
- Result axes, resolution, normalization, and valid masks are exact and tested.
- Low-end claims are suppressed when the signal/window cannot resolve them.

### WP-04 — Phase, Group Delay, Pair Alignment, Blend Prediction

Ownership:

```text
app/extensions/phase.py
app/extensions/pair_compare.py
tests/extensions/test_phase.py
tests/extensions/test_pair_compare.py
```

Acceptance:

- Integer delay and polarity are exact on synthetic fixtures.
- Fractional-delay estimate error <= 0.25 sample on the agreed broadband
  fixture.
- Pure-delay group delay matches injected delay within documented tolerance.
- Predicted complex blend magnitude matches an actual aligned time-domain sum
  within 0.25 dB RMS over reliable bins.
- Unreliable low-magnitude bins are masked and excluded from scores.

### WP-05 — Decay and Response Fingerprint

Ownership:

```text
app/extensions/decay.py
app/extensions/fingerprint.py
app/extensions/profiles.py
tests/extensions/test_decay.py
tests/extensions/test_fingerprint.py
```

Acceptance:

- Synthetic exponential decay recovers valid T60 within 5% when formal T60 is
  applicable.
- Truncated/noisy cabinet-style fixtures do not receive a fabricated valid T60.
- Fingerprints are deterministic, bounded, serializable, and gain invariant
  where documented.
- Invalid component provenance survives cache round trips.

### WP-06 — Response Matching and Pair Search

Ownership:

```text
app/extensions/advanced_matching.py
tests/extensions/test_advanced_matching.py
```

Acceptance:

- Stage-one legacy scores reproduce `score_curve` within `1e-12`.
- Stage two never promotes candidates outside explicit tone constraints.
- Synthetic tight/slow, boxy/clean, and phase-safe/risky fixtures rank in the
  expected order.
- Missing-data policies and score breakdown arithmetic are directly tested.
- Source `AnalysisResult` objects are never mutated.

### WP-07 — Compare Workbench and Rendering

Ownership:

```text
app/extensions/ui/*
app/extended_main.py
bestir_extended.py
tests/extensions/test_extended_ui.py
tests/extensions/extended_gui_smoke.py
```

Acceptance:

- Exactly two selected legacy rows populate A/B without modifying legacy UI.
- All five workbench tabs display the same source/config identity.
- Stale and cancelled computations cannot update plots.
- OpenGL absence activates the fallback renderer without application failure.
- Legacy and extended headless GUI workflows both pass without audio devices.

### WP-08 — Optional Processing and Export

Retain the non-destructive processing/export requirements from the superseded
plan, but implement them after comparison and matching. Phase/delay suggestions
may populate a processing config only after explicit user action; analysis never
modifies audio automatically.

### WP-09 — Packaging and Release Gates

- Build `BestIRExtended.exe` separately from `BestIR.exe`.
- Benchmark cold/cached shortlist analysis and A/B matrix rendering.
- Confirm extension-disabled overhead is effectively zero.
- Validate all supported rates/channels and malformed edge cases.
- Run numerical tests, full legacy regression, GUI smoke, real-IR comparison,
  packaged launch, and listening A/B checks.
- Switch the default launcher only in a separately approved final change.

## 14. Test Fixtures

Create deterministic synthetic fixtures rather than relying only on commercial
IR files:

- Dirac, delayed Dirac, inverted Dirac, and fractional-delay broadband IR.
- Minimum-phase low/high-pass fixtures.
- Damped sinusoids at 80, 120, 300, 450, 3k, and 8k Hz with known decay rates.
- Fast and slow onset envelopes with matched smoothed magnitude where possible.
- Stereo files with known inter-channel delay/polarity.
- Noise-floor, truncated-tail, clipped, silent, NaN/Inf, and too-short inputs.
- Pair fixtures with analytically predictable constructive/destructive blends.

Use real IRs only for integration, visual review, and performance evidence. Unit
tests must not depend on the licensed `IR/` library being present.

## 15. Test Gates

For every work package:

```powershell
python -m pytest tests\extensions\test_<feature>.py -q --basetemp=E:\Projects\BestIR\.test-tmp\<wp>-focused -p no:cacheprovider
python -m pytest tests -q --basetemp=E:\Projects\BestIR\.test-tmp\<wp>-full -p no:cacheprovider
python -m app.main --selftest
```

WP-07 and WP-09 also run legacy and extended offscreen GUI smoke tests. Each
agent reports exact commands, results, numerical tolerances, unresolved risks,
and files changed.

## 16. AI Coder Handoff Prompt

Give one agent one work package. WP-03 and WP-04 are the first safe parallel
pair. Use this prompt:

```text
Read docs/IR_COMPARISON_AND_MATCHING_PLAN_V2.md completely. Implement only
<WP-ID>. Treat the current worktree and frozen contracts as authoritative. Do
not modify app/core, app/ui, legacy tests, bestir.py, run.bat, or BestIR.spec.
Preserve other agents' changes and stay within the listed file ownership. Start
by verifying prerequisite work packages and baseline. Implement pure DSP before
UI, document mathematical conventions, and test every acceptance criterion with
deterministic synthetic fixtures. Run focused tests, the full legacy suite, and
the self-test. Report files changed, exact test output, numerical error against
ground truth, limitations, and the next unlocked work package. Stop and report a
contract conflict instead of inventing or editing a competing interface.
```

Coordinator rules:

- WP-01 alone owns shared contracts.
- WP-02 alone owns preprocessing/time origin.
- WP-03 and WP-04 consume those APIs without changing them.
- WP-05 resolves scalar feature semantics before WP-06 scoring begins.
- WP-07 consumes frozen result models; it does not embed DSP in widgets.
- One coordinator runs the combined suite and handles cross-package changes.

## 17. Completion Definition

The clarified project is complete only when:

- Legacy EQ/tone screening behaves exactly as before.
- Users can compare two tone-similar IRs in waveform/envelope, CSD,
  spectrogram, phase, group delay, and predicted blend views.
- Visual claims have quantitative metrics, units, configs, confidence, and
  validity status.
- Response-aware ranking can preserve tone constraints while selecting attack,
  decay, boxiness, phase, or blend behavior.
- Complex blend predictions match time-domain verification within tolerance.
- Heavy matrices remain selected-pair/on-demand work and the UI stays
  responsive.
- Legacy tests, extended tests, both GUI smoke paths, packaging, real-IR review,
  and listening A/B checks pass.
- Source files, legacy cache/data models, and legacy executable remain intact.
