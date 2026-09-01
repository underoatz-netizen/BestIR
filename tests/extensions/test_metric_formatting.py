"""B12 gates: display-only unit formatting (metric_format + MetricCard/SummaryPanel).

Cached raw values (fraction coverage, linear crest ratio) must never be
mutated; conversions happen only at render time.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

from app.extensions.contracts import (FeatureValue, ResponseFingerprint,  # noqa: E402
                                      SourceKey)
from app.extensions.ui import metric_format as mf  # noqa: E402

pytest.importorskip('PySide6')


# --------------------------------------------------------------------------
# pure formatting helpers
# --------------------------------------------------------------------------

def test_coverage_fraction_displays_as_percent():
    assert mf.to_display_value('gd_valid_coverage', 0.250978, '%') == \
        pytest.approx(25.0978)
    assert mf.format_metric('gd_valid_coverage', 0.250978, '%') == '25.10%'


def test_coverage_zero_and_one_boundaries():
    assert mf.format_metric('gd_valid_coverage', 0.0, '%') == '0.00%'
    assert mf.format_metric('gd_valid_coverage', 1.0, '%') == '100.00%'


def test_crest_ratio_to_db():
    assert mf.crest_ratio_to_db(2.0) == pytest.approx(6.0206, abs=1e-3)
    assert mf.to_display_value('crest_factor', 2.0, 'dB') == \
        pytest.approx(6.0206, abs=1e-3)
    # display text stays within the established significant-digit style
    assert mf.format_metric('crest_factor', 2.0, 'dB').startswith('6.02')
    assert mf.format_metric('crest_factor', 2.0, 'dB').endswith('dB')


@pytest.mark.parametrize('bad', [0.0, -1.0, float('nan'), float('inf'), None])
def test_crest_guards_return_none(bad):
    assert mf.crest_ratio_to_db(bad) is None
    assert mf.to_display_value('crest_factor', bad, 'dB') is None
    assert mf.format_metric('crest_factor', bad, 'dB') == 'n/a'


def test_none_and_nonfinite_generic_values():
    assert mf.format_metric('time_to_peak_ms', None, 'ms') == 'n/a'
    assert mf.format_metric('time_to_peak_ms', float('nan'), 'ms') == 'n/a'


def test_raw_units_pass_through_unchanged():
    assert mf.to_display_value('time_to_peak_ms', 12.5, 'ms') == 12.5
    assert mf.to_display_value('early_energy_5ms', 0.37, '') == 0.37
    assert mf.format_metric('gd_median_ms', 1.234, 'ms') == '1.234 ms'
    assert mf.format_cell(12.5, 'ms') == '12.5'
    assert mf.format_cell(25.0978, '%') == '25.10%'
    assert mf.format_cell(None, '%') == 'n/a'
    assert mf.unit_suffix('%') == '%'
    assert mf.unit_suffix('ms') == ' ms'
    assert mf.unit_suffix('') == ''


# --------------------------------------------------------------------------
# non-mutation of cached / contract values
# --------------------------------------------------------------------------

def _fingerprint(path='ir.wav'):
    key = SourceKey(path=path, mtime_ns=1, size=2, sample_rate=48000,
                    channels=1)
    return ResponseFingerprint(
        key=key,
        transient={
            'time_to_peak_ms': FeatureValue(1.5, True),
            'early_energy_5ms': FeatureValue(0.37, True),
            'centroid_ms': FeatureValue(4.25, True),
            'crest_factor': FeatureValue(2.0, True),
        },
        decay={
            'd20_low_ms': FeatureValue(210.5, True),
            'boxiness_persistence_excess_db': FeatureValue(3.25, True),
            'boxiness_ridge_hz': FeatureValue(315.0, True),
        },
        phase={
            'gd_median_ms': FeatureValue(0.85, True),
            'gd_spread_ms': FeatureValue(0.4, True),
            'gd_valid_coverage': FeatureValue(0.250978, True),
        },
    )


def test_to_display_value_does_not_mutate_input():
    fp = _fingerprint()
    snapshot = fp.to_json()
    feats = fp.all_features()
    for name, fv in feats.items():
        mf.to_display_value(name, fv.value, 'ms')
        mf.format_metric(name, fv.value, '%')
        mf.format_metric(name, fv.value, 'dB')
    assert fp.to_json() == snapshot


@pytest.fixture(scope='module')
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_panel_and_card_do_not_mutate_fingerprint(qapp):
    from app.extensions.ui.summary_panel import SummaryPanel
    fp_a = _fingerprint('a.wav')
    fp_b = _fingerprint('b.wav')
    snap_a, snap_b = fp_a.to_json(), fp_b.to_json()
    panel = SummaryPanel()
    try:
        panel.show_fingerprints(fp_a, fp_b, 'A.wav', 'B.wav')
    finally:
        panel.close()
    assert fp_a.to_json() == snap_a
    assert fp_b.to_json() == snap_b


# --------------------------------------------------------------------------
# widget-level display
# --------------------------------------------------------------------------

def test_metric_card_percent_and_db(qapp):
    from app.extensions.ui.widgets.metric_card import MetricCard
    cov = MetricCard('Phase Coverage', unit='%', feature='gd_valid_coverage')
    cov.set_values(0.250978, 0.5)
    assert cov.val_a_lbl.text() == '25.10%'
    assert cov.val_b_lbl.text() == '50.00%'
    assert cov.delta_lbl.text() == '-24.90%'

    crest = MetricCard('Crest factor', unit='dB', feature='crest_factor')
    crest.set_values(2.0, 1.0)
    assert crest.val_a_lbl.text().startswith('6.02')
    assert crest.val_b_lbl.text() == '0 dB' or \
        float(crest.val_b_lbl.text().replace(' dB', '')) == pytest.approx(0.0)

    bad = MetricCard('Crest factor', unit='dB', feature='crest_factor')
    bad.set_values(0.0, 2.0)
    assert bad.val_a_lbl.text() == 'n/a'
    assert bad.delta_lbl.text() == '—'


def test_metric_card_legacy_raw_unit(qapp):
    from app.extensions.ui.widgets.metric_card import MetricCard
    card = MetricCard('Time to Peak', unit='ms', feature='time_to_peak_ms')
    card.set_values(1.5, 2.0)
    assert card.val_a_lbl.text() == '1.5 ms'
    assert card.val_b_lbl.text() == '2 ms'
    assert card.delta_lbl.text() == '-0.5 ms'


def test_summary_panel_table_and_cards_display(qapp):
    from app.extensions.ui.summary_panel import SummaryPanel
    fp_a = _fingerprint('a.wav')
    fp_b = _fingerprint('b.wav')
    panel = SummaryPanel()
    try:
        panel.show_fingerprints(fp_a, fp_b, 'A.wav', 'B.wav')
        rows = {panel.table.item(i, 0).text():
                (panel.table.item(i, 1).text(), panel.table.item(i, 2).text(),
                 panel.table.item(i, 3).text())
                for i in range(panel.table.rowCount())}
        assert rows['Valid phase coverage'] == ('25.10%', '25.10%', '+0.00%')
        assert rows['Crest factor'][0].startswith('6.02')
        assert rows['Time to peak (ms)'] == ('1.5', '1.5', '+0')

        card_txt = panel._cards['gd_valid_coverage'].val_a_lbl.text()
        assert card_txt == '25.10%'

        # differences prose uses display-unit numbers (percent rows)
        assert 'Valid phase coverage' in panel.why.toPlainText()
    finally:
        panel.close()


def test_summary_panel_invalid_crest_shows_na(qapp):
    from app.extensions.ui.summary_panel import SummaryPanel
    fp_a = _fingerprint('a.wav')
    fp_b = _fingerprint('b.wav')
    # zero crest is valid raw data but not representable in dB
    fp_b.transient['crest_factor'] = FeatureValue(0.0, True)
    panel = SummaryPanel()
    try:
        panel.show_fingerprints(fp_a, fp_b, 'A.wav', 'B.wav')
        rows = {panel.table.item(i, 0).text():
                (panel.table.item(i, 1).text(), panel.table.item(i, 2).text(),
                 panel.table.item(i, 3).text())
                for i in range(panel.table.rowCount())}
        assert rows['Crest factor'] == ('6.021', 'n/a', 'n/a')
    finally:
        panel.close()
