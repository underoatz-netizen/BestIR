# -*- coding: utf-8 -*-
"""Wave5 panel tests: ResponseSearchPanel payload/signal + summary style.

Exercises the actual public APIs:
- ResponseSearchPanel: get_preset_state() payload (B08) is mode-independent,
  mode switches through the mode_combo, and the Set A candidate action button
  (U07) fires candidate_set_a.
- SummaryPanel: show_fingerprints renders n/a reasons inline, ranks by the
  dimensionless normalized effect, and never claims a winner (U08).
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.extensions.contracts import (FeatureValue, ResponseFingerprint,  # noqa: E402
                                      ScoreBreakdown, SourceKey)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class TestResponseSearchPanel:
    def test_simple_advanced_payload_keys_and_set_a_signal(self, qapp):
        from app.extensions.contracts import RankedCandidate
        from app.extensions.ui.response_search_panel import ResponseSearchPanel

        panel = ResponseSearchPanel()
        payload_keys = {'name', 'weights', 'constraints', 'targets', 'policy'}
        # Simple mode payload (B08 public snapshot API)
        simple_payload = panel.get_preset_state()
        assert isinstance(simple_payload, dict)
        assert set(simple_payload) == payload_keys
        # Advanced mode: same public payload shape, no 'mode' split
        panel.mode_combo.setCurrentText('Advanced')
        assert panel.current_mode() == 'Advanced'
        adv_payload = panel.get_preset_state()
        assert isinstance(adv_payload, dict)
        assert set(adv_payload) == payload_keys
        assert adv_payload['weights'] == simple_payload['weights']

        # candidate "Set A" accessible button fires candidate_set_a (U07)
        panel.mode_combo.setCurrentText('Simple')
        cand = RankedCandidate(
            record=SimpleNamespace(path='C:/ir/a.wav'),
            fingerprint=None, breakdown=ScoreBreakdown(total=0.5), rank=1)
        panel.show_results([cand])
        fired = {}
        panel.candidate_set_a.connect(
            lambda c: fired.update(count=fired.get('count', 0) + 1, cand=c))
        from PySide6.QtWidgets import QPushButton
        set_a_btns = [b for b in panel.findChildren(QPushButton)
                      if (b.accessibleName() or '').startswith('Set A')]
        assert set_a_btns, 'no Set A button found in the candidate row'
        set_a_btns[0].click()
        assert fired.get('count', 0) >= 1
        assert fired['cand'] is cand
        panel.close()


class TestSummaryStyle:
    def test_normalized_ordering_na_visible_and_neutral_wording(self, qapp):
        from app.extensions.ui.summary_panel import SummaryPanel

        def fingerprint(path):
            return ResponseFingerprint(
                key=SourceKey(path=path, mtime_ns=1, size=2, sample_rate=48000,
                              channels=1),
                transient={
                    'time_to_peak_ms': FeatureValue(1.0, True),
                    'early_energy_5ms': FeatureValue(0.37, True),
                    'crest_factor': FeatureValue(2.0, True),
                },
                decay={
                    'd20_low_ms': FeatureValue(210.5, True),
                    'boxiness_persistence_excess_db': FeatureValue(3.25, True),
                },
                phase={
                    'gd_median_ms': FeatureValue(0.85, True),
                    'gd_spread_ms': FeatureValue(0.4, True),
                    # B's coverage is invalid -> n/a must stay visible
                    'gd_valid_coverage': FeatureValue(
                        None, False, note='no reliable bins'),
                },
            )

        panel = SummaryPanel()
        fp_a = fingerprint('a.wav')
        fp_b = fingerprint('b.wav')
        # different values so normalized-effect ranking is observable
        fp_b.transient['time_to_peak_ms'] = FeatureValue(3.0, True)
        fp_b.transient['early_energy_5ms'] = FeatureValue(0.10, True)
        fp_b.decay['d20_low_ms'] = FeatureValue(190.0, True)
        fp_b.phase['gd_median_ms'] = FeatureValue(0.5, True)
        panel.show_fingerprints(fp_a, fp_b, name_a='IR A', name_b='IR B')

        from PySide6.QtWidgets import QLabel, QTableWidget, QTextEdit
        texts = []
        for t in panel.findChildren(QTableWidget):
            for r in range(t.rowCount()):
                for c in range(t.columnCount()):
                    item = t.item(r, c)
                    if item:
                        texts.append(item.text())
        for e in panel.findChildren(QTextEdit):
            texts.append(e.toPlainText())
        for l in panel.findChildren(QLabel):
            texts.append(l.text())
        joined = " ".join(texts).lower()
        # n/a must be visible (not hidden)
        assert any("n/a" in t.lower() for t in texts), \
            f"n/a not visible: {texts}"
        # neutral wording: no winner-style words
        for bad in ("winner", "ผู้ชนะ", "better", "ดีที่สุด"):
            assert bad not in joined, f"non-neutral wording found: {bad}"
        # normalized-effect ordering: early-energy delta (0.27/0.2) ranks first
        # (lines[0] = intro, lines[1] = blank, lines[2:] = ranked bullets)
        lines = panel.why.toPlainText().splitlines()
        assert 'Early energy 0-5 ms' in lines[2], lines
        assert 'Time to peak (ms)' in lines[3], lines
        # styles rules applied
        for l in panel.findChildren(QLabel):
            assert l.style() is not None
        panel.close()