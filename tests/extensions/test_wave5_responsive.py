"""Wave 5 foundation gates: responsive layout adapter, instance-local Boro
styling (B18) and AB-header path/accessibility wiring.

Only public adapter/window/widget behavior is exercised — no private helper
calls, no reliance on layout internals beyond parentage and Qt accessors.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

pytest.importorskip('PySide6')
from PySide6.QtCore import QCoreApplication, QEvent, Qt  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QToolButton)  # noqa: E402

# Snapshot the legacy module-level styling BEFORE any window exists.
# These must survive window creation untouched (B18).
import app.ui.model as _model_mod  # noqa: E402
import app.ui.plot_panel as _plot_mod  # noqa: E402

_LEGACY_TOP5_BG = QColor(_model_mod._TOP5_BG)
_LEGACY_PEN_COLORS = {
    name: QColor(getattr(_plot_mod, name).color())
    for name in ('_CURVE_PEN', '_HOVER_PEN', '_SEL_PEN', '_TOP_PEN',
                 '_TARGET_PEN', '_DI_PEN', '_OUTPUT_PEN')}


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def extended(qapp, tmp_path):
    import app.ui.workers as legacy_workers
    from app.extensions.ui.main_window_adapter import ExtendedMainWindow

    legacy_workers.ScanWorker.start = lambda self: None   # no real-scan race
    win = ExtendedMainWindow()
    from app.core.cache import LibraryCache
    from app.core.scanner import scan_library
    from tests.extensions import fixtures as fx
    from tests.synth import write_wav
    lib = tmp_path / 'lib'
    lib.mkdir()
    write_wav(lib / 'a.wav', fx.boxy_fixture(300.0, 0.06, n=24000))
    write_wav(lib / 'b.wav', fx.clean_fixture(n=24000))
    write_wav(lib / 'c.wav', fx.decay_fixture(100.0, 0.02, n=24000))
    cache = LibraryCache(str(tmp_path / 'fp_wave5.json'))
    win.library = scan_library([str(lib)], cache)
    win._on_scan_done(win.library)
    # The offscreen window cannot shrink below the sum of the legacy panels'
    # minimum widths; lower them so a 1280-class resize can reach compact mode.
    for region in (win.library_panel, win.screen_panel, win.inspector, win.plot):
        region.setMinimumWidth(150)
    win.show()
    yield win
    win.close()


def _adapter(win):
    from app.extensions.ui.responsive_layout import ResponsiveLayoutAdapter

    adapters = [a for a in win.findChildren(ResponsiveLayoutAdapter)]
    assert len(adapters) == 1, 'the extended window must own exactly one adapter'
    return adapters[0]


def _settle(win, qapp, width):
    win.resize(width, 720)
    qapp.processEvents()


def _hbox_rows(panel):
    """Top-level horizontal sub-layouts of the library panel (public Qt)."""
    lay = panel.layout()
    return [lay.itemAt(i) for i in range(lay.count())
            if isinstance(lay.itemAt(i), QHBoxLayout)]


def _row_with(panel, widget):
    for row in _hbox_rows(panel):
        if row.indexOf(widget) >= 0:
            return row
    return None


def _row_widget_texts(row):
    return [item.widget().text() for item in
            (row.itemAt(i) for i in range(row.count()))
            if item.widget() is not None and hasattr(item.widget(), 'text')]


# ---- U01: responsive drawer + filter wrap ----------------------------------
def test_compact_width_collapses_inspector_and_wraps_filters(extended, qapp):
    adapter = _adapter(extended)
    panel = extended.library_panel
    _settle(extended, qapp, 1400)
    assert not adapter.is_compact()
    assert adapter.inspector_open()
    assert not extended.inspector.isHidden()
    assert adapter.filter_overflow() is None

    _settle(extended, qapp, 1100)
    assert adapter.is_compact()
    assert not adapter.inspector_open()
    assert extended.inspector.isHidden()
    # secondary filters moved into the overflow popup, Search stays in the row
    assert adapter.filter_overflow() is not None
    for name in adapter.FILTER_WIDGETS:
        widget = getattr(panel, name)
        assert widget.parent() is not panel, name
    assert panel.search.parent() is panel

    _settle(extended, qapp, 1400)
    assert not adapter.is_compact()
    assert adapter.filter_overflow() is None
    for name in adapter.FILTER_WIDGETS:
        widget = getattr(panel, name)
        assert widget.parent() is panel, name
    assert not extended.inspector.isHidden()


def test_inspector_drawer_toggle_restores_splitter_sizes(extended, qapp):
    adapter = _adapter(extended)
    _settle(extended, qapp, 1400)
    splitter = extended.centralWidget()
    sizes_before = list(splitter.sizes())
    assert any(s > 0 for s in sizes_before)

    adapter.toggle_inspector()
    assert not adapter.inspector_open()
    assert extended.inspector.isHidden()

    adapter.toggle_inspector()
    assert adapter.inspector_open()
    assert not extended.inspector.isHidden()
    assert list(splitter.sizes()) == sizes_before


# ---- U02 (Wave 7): wide search row + separate collapsible secondary row -----
def test_u02_wide_search_row_and_separate_filter_row(extended, qapp):
    adapter = _adapter(extended)
    panel = extended.library_panel
    _settle(extended, qapp, 1400)
    assert not adapter.is_compact()
    assert adapter.filter_overflow() is None

    # search keeps its own row together with Clear only
    search_row = _row_with(panel, panel.search)
    assert search_row is not None
    assert search_row.indexOf(panel.clear_btn) >= 0
    for name in adapter.FILTER_WIDGETS:
        widget = getattr(panel, name)
        assert widget.parent() is panel, name        # instance-local, no popup
        assert search_row.indexOf(widget) < 0, name   # not on the search row

    # the secondary filters share one separate row below it
    filter_row = _row_with(panel, panel.sr_combo)
    assert filter_row is not None and filter_row is not search_row
    assert filter_row.indexOf(panel.search) < 0
    for name in ('ch_combo', 'tag_combo', 'flat_spin'):
        assert filter_row.indexOf(getattr(panel, name)) >= 0, name

    # instance-local minimum usable width for the search field (>= 160 px)
    assert panel.search.minimumWidth() >= 160
    assert panel.search.minimumHeight() >= 33
    assert panel.clear_btn.minimumHeight() >= 33


def test_u02_wide_filter_row_collapse_toggle(extended, qapp):
    adapter = _adapter(extended)
    panel = extended.library_panel
    _settle(extended, qapp, 1400)
    assert not adapter.filter_row_collapsed()
    for name in adapter.FILTER_WIDGETS:
        assert getattr(panel, name).isVisibleTo(panel), name

    adapter.toggle_filter_row()
    qapp.processEvents()
    assert adapter.filter_row_collapsed()
    for name in adapter.FILTER_WIDGETS:
        assert not getattr(panel, name).isVisibleTo(panel), name
    # the search row and the legacy table stay usable while collapsed
    assert panel.search.isVisibleTo(panel)
    assert panel.clear_btn.isVisibleTo(panel)

    adapter.toggle_filter_row()
    qapp.processEvents()
    assert not adapter.filter_row_collapsed()
    for name in adapter.FILTER_WIDGETS:
        assert getattr(panel, name).isVisibleTo(panel), name


def test_u02_wide_filter_signals_and_semantics_preserved(extended, qapp):
    adapter = _adapter(extended)
    panel = extended.library_panel
    _settle(extended, qapp, 1400)
    fired = []
    panel.filters_changed.connect(lambda: fired.append(dict(panel.filters())))

    panel.search.setText('a.wav')
    assert fired and fired[-1]['text'] == 'a.wav'
    panel.sr_combo.setCurrentIndex(2)               # '48000'
    assert fired[-1]['sr'] == 48000
    panel.ch_combo.setCurrentIndex(1)               # Mono
    assert fired[-1]['channels'] == 1
    panel.flat_spin.setValue(3.5)
    assert fired[-1]['max_flatness'] == 3.5
    panel.clear_btn.click()
    assert fired[-1]['text'] == '' and fired[-1]['sr'] == 0
    assert fired[-1]['channels'] == 0
    assert fired[-1]['max_flatness'] is None

    # the filter dictionary still drives the unchanged legacy predicate
    panel.search.setText('a.wav')
    hits = panel.apply_filters(list(extended.library))
    assert [os.path.basename(r.path) for r in hits] == ['a.wav']


def test_u02_compact_overflow_behavior_preserved_after_split(extended, qapp):
    adapter = _adapter(extended)
    panel = extended.library_panel
    _settle(extended, qapp, 1400)

    # collapse the wide filter row, then narrow down: the compact popup path
    # must behave exactly as before (original row restored, popup created)
    adapter.toggle_filter_row()
    _settle(extended, qapp, 1100)
    assert adapter.is_compact()
    assert adapter.filter_overflow() is not None
    assert adapter.filter_row_collapsed() is False   # no leaked collapsed state
    for name in adapter.FILTER_WIDGETS:
        widget = getattr(panel, name)
        assert widget.parent() is not panel, name
        assert widget.isVisibleTo(widget.parent()), name
    assert panel.search.parent() is panel
    search_row = _row_with(panel, panel.search)
    assert search_row is not None
    # The primary compact row contains no labels whose controls now live in
    # the popup.  Search/Clear and the overflow affordance remain usable.
    assert panel.clear_btn in [search_row.itemAt(i).widget()
                               for i in range(search_row.count())]
    texts = _row_widget_texts(search_row)
    assert 'Search' in texts and 'Filters ▾' in texts
    assert not {'SR', 'Ch', 'Flat ≤'}.intersection(texts)
    # only one row containing search exists in compact mode (the original one)
    assert len(_hbox_rows(panel)) == 2

    # filters still emit from inside the popup
    fired = []
    panel.filters_changed.connect(lambda: fired.append(dict(panel.filters())))
    panel.sr_combo.setCurrentIndex(1)               # '44100'
    assert fired and fired[-1]['sr'] == 44100

    _settle(extended, qapp, 1400)
    assert not adapter.is_compact()
    assert adapter.filter_overflow() is None
    assert panel.sr_combo.currentIndex() == 1       # value survives the trips
    assert panel.sr_combo.parent() is panel
    hits = panel.apply_filters(list(extended.library))   # all IRs are 48k
    assert hits == []


def test_u02_compact_overflow_survives_repeated_split_transitions(extended, qapp):
    """The retained popup action stays valid across repeated transitions."""
    adapter = _adapter(extended)
    panel = extended.library_panel
    _settle(extended, qapp, 1400)

    for _ in range(12):
        adapter.toggle_filter_row()
        _settle(extended, qapp, 1100)
        assert adapter.is_compact()
        assert adapter.filter_overflow() is not None
        for name in adapter.FILTER_WIDGETS:
            assert getattr(panel, name).parent() is not panel, name

        _settle(extended, qapp, 1400)
        # Process the transient button teardown before building the next
        # compact view.
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        qapp.processEvents()
        assert not adapter.is_compact()
        assert adapter.filter_overflow() is None
        assert panel.sr_combo.parent() is panel


def test_u02_legacy_library_panel_layout_untouched(qapp):
    """A plain legacy LibraryPanel (no adapter) keeps the original row."""
    from app.extensions.ui.responsive_layout import ResponsiveLayoutAdapter
    from app.ui.library_panel import LibraryPanel

    panel = LibraryPanel()
    try:
        rows = _hbox_rows(panel)
        assert len(rows) == 2                      # folders row + filter row
        frow = _row_with(panel, panel.search)
        assert frow is not None
        for name in ResponsiveLayoutAdapter.FILTER_WIDGETS:
            assert frow.indexOf(getattr(panel, name)) >= 0, name
        assert frow.indexOf(panel.clear_btn) >= 0
        # no instance-local minimum width, no toggle button, no second row
        assert panel.search.minimumWidth() < ResponsiveLayoutAdapter.SEARCH_MIN_WIDTH
        assert panel.search.minimumHeight() < ResponsiveLayoutAdapter.SEARCH_ROW_MIN_HEIGHT
        assert panel.clear_btn.minimumHeight() < ResponsiveLayoutAdapter.SEARCH_ROW_MIN_HEIGHT
        assert [b for b in panel.findChildren(QToolButton)
                if b.text().startswith('Filters')] == []
    finally:
        panel.deleteLater()


# ---- B18: Boro styling is instance-local, legacy globals untouched ----------
def test_b18_legacy_plot_module_globals_untouched(extended):
    for name, legacy_color in _LEGACY_PEN_COLORS.items():
        current = getattr(_plot_mod, name)
        assert current.color() == legacy_color, name
    # the extended window still shows its Boro target pen (instance-local)
    from app.extensions.ui.styles_boro import COLOR_DIFF

    assert extended.plot._target_item.opts['pen'].color() == QColor(COLOR_DIFF)


def test_b18_top_rank_tint_is_instance_local(extended):
    from app.extensions.ui.styles_boro import ACCENT_GOLD_BG
    from app.ui.model import IRTableModel

    recs = list(extended.library)
    for i, rec in enumerate(recs):
        rec.score = float(i)
    model = extended.library_panel.model
    model.set_records(recs, top_n=2)
    assert model.data(model.index(0, 0), Qt.BackgroundRole) == \
        QColor(ACCENT_GOLD_BG)
    assert model.data(model.index(len(recs) - 1, 0),
                      Qt.BackgroundRole) is None

    # a plain legacy model keeps the original global tint, and the module
    # global itself was never mutated
    plain = IRTableModel()
    plain.set_records(recs, top_n=2)
    assert plain.data(plain.index(0, 0), Qt.BackgroundRole) == \
        QColor(_LEGACY_TOP5_BG)
    assert _model_mod._TOP5_BG == QColor(_LEGACY_TOP5_BG)


# ---- U04/AB header: full path via tooltip + accessibility, swap name --------
class _Rec:
    """Duck-typed record with only the fields IRDeckCard.set_record reads."""

    def __init__(self, path):
        self.path = path
        self.sample_rate = 48000
        self.channels = 1
        self.effective_length_ms = 500.0
        self.score = None


def test_ab_header_carries_full_path_and_clears_on_reset(qapp, tmp_path):
    from app.extensions.ui.widgets import ABHeaderDeck

    path_a = str(tmp_path / 'cab_sim_121_front_far03m_neumann.wav')
    header = ABHeaderDeck()
    header.set_a(_Rec(path_a))
    name_lbl = header.card_a.name_lbl
    assert name_lbl.toolTip() == path_a
    assert name_lbl.accessibleDescription() == path_a
    assert name_lbl.text()                    # a (display) name is shown

    header.set_a(None)
    assert name_lbl.toolTip() == ''
    assert name_lbl.accessibleDescription() == ''
    assert name_lbl.accessibleName() == 'IR A name'


def test_ab_header_swap_button_is_accessible(qapp):
    from app.extensions.ui.widgets import ABHeaderDeck

    header = ABHeaderDeck()
    assert header.swap_btn.accessibleName() == 'Swap IR A and B'
    fired = []
    header.swap_requested.connect(lambda: fired.append(True))
    header.swap_btn.click()
    assert fired == [True]


# ---- Extension library folder removal --------------------------------------
def test_remove_folder_button_updates_library_and_folders_list(extended, qapp):
    panel = extended.library_panel
    assert hasattr(extended, 'remove_folder_btn')
    assert extended.remove_folder_btn.isVisibleTo(panel)

    folder_list = panel.folder_list
    folder_list.addItem('C:/test/ir_folder_1')
    folder_list.addItem('C:/test/ir_folder_2')
    assert folder_list.count() == 2

    # Select first folder item and click remove
    folder_list.setCurrentRow(0)
    assert len(folder_list.selectedItems()) == 1
    removed_path = folder_list.currentItem().text()

    extended.remove_folder_btn.click()
    # Path is gone from folder_list
    remaining_folders = [folder_list.item(i).text() for i in range(folder_list.count())]
    assert removed_path not in remaining_folders
    assert len(remaining_folders) == 1
