"""CSD view: renderer selection + band-decay numeric panel (WP-07).

Enhanced with Boro UI styling and numeric evidence cards.

B09: A and B results are stored separately and only the explicitly selected
source is rendered (deterministic default: A), so completion order can never
decide what the user sees.  B13: band-decay validity is read through the
single contract accessor in ``app.extensions.csd`` and the UI distinguishes
invalid / noisy / unsupported / insufficient-duration states.
"""
from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QRadioButton, QTextEdit, QVBoxLayout,
                               QWidget)

from app.extensions.contracts import AnalysisStatus
from app.extensions.csd import (DECAY_UNAVAILABLE_INSUFFICIENT,
                                DECAY_UNAVAILABLE_INVALID,
                                DECAY_UNAVAILABLE_NOISY,
                                DECAY_UNAVAILABLE_UNSUPPORTED, decay_metric_key,
                                decay_validity)
from .renderers.csd_base import try_opengl_renderer
from .renderers.csd_fallback import FallbackCsdRenderer, RidgeCsdRenderer
from .styles_boro import (ACCENT_GOLD, BORDER_CARD, COLOR_IR_A, COLOR_IR_B,
                          FONT_FAMILY_MONO, FONT_FAMILY_PRIMARY, SURFACE_CARD,
                          SURFACE_RAISED, TEXT_MAIN, TEXT_MUTED)
from .widgets.validity_chip import ValidityChip

# B13: every unavailability reason gets its own UI tag — never lumped together.
_STATE_TAGS = {
    'valid': ' ✓',
    DECAY_UNAVAILABLE_NOISY: ' (noisy)',
    DECAY_UNAVAILABLE_INSUFFICIENT: ' (insufficient duration)',
    DECAY_UNAVAILABLE_UNSUPPORTED: ' (not measured)',
    DECAY_UNAVAILABLE_INVALID: ' (invalid)',
}


class CsdView(QWidget):
    """Heatmap CSD (OpenGL surface when available) + band-decay readouts.

    The view owns one stored result per source (A/B) and renders only the
    selected one; the selector defaults deterministically to A.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._renderer = None
        self._using_gl = False
        gl = try_opengl_renderer()
        self._plot = None
        if gl is not None:
            try:
                self._plot = gl.create_view()
                self._renderer = gl
                self._using_gl = True
            except Exception:
                # Import support does not guarantee that a native GL widget can
                # be constructed (remote desktop and drivers commonly fail).
                self._plot = None
                self._renderer = FallbackCsdRenderer()
        if self._renderer is None:
            self._renderer = FallbackCsdRenderer()
        if self._plot is None:
            self._plot = self._create_fallback_plot()

        # B09: per-source storage — storing one never discards the other.
        self._csd_by_source: dict[str, object | None] = {'A': None, 'B': None}
        self._selected = 'A'

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # B09: explicit A/B source selector; deterministic default = A, so the
        # displayed plot is decided by selection, never by completion order.
        selector_row = QHBoxLayout()
        selector = QWidget()
        radio_box = QHBoxLayout(selector)
        radio_box.setContentsMargins(0, 0, 0, 0)
        self.btn_source_a = QRadioButton('IR A')
        self.btn_source_b = QRadioButton('IR B')
        self.btn_source_a.setChecked(True)
        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self.btn_source_a)
        group.addButton(self.btn_source_b)
        self.btn_source_a.setStyleSheet(
            f'QRadioButton {{ color: {COLOR_IR_A}; font-weight: 600; }}')
        self.btn_source_b.setStyleSheet(
            f'QRadioButton {{ color: {COLOR_IR_B}; font-weight: 600; }}')
        radio_box.addWidget(self.btn_source_a)
        radio_box.addWidget(self.btn_source_b)
        selector_row.addWidget(selector)
        selector_row.addStretch(1)
        self.source_caption = QLabel('')
        self.source_caption.setStyleSheet(
            f'color: {TEXT_MUTED}; font-family: {FONT_FAMILY_MONO};'
            f'font-size: 8.5pt;')
        selector_row.addWidget(self.source_caption)
        layout.addLayout(selector_row)
        self.btn_source_a.toggled.connect(self._on_source_toggled)

        # Plot on top
        self._plot_layout = QVBoxLayout()
        self._plot_layout.setContentsMargins(0, 0, 0, 0)
        self._plot_layout.addWidget(self._plot)
        layout.addLayout(self._plot_layout, 3)

        # Numeric Evidence section
        bottom_box = QFrame()
        bottom_box.setStyleSheet(f"""
            QFrame {{
                background-color: {SURFACE_CARD};
                border: 1px solid {BORDER_CARD};
                border-radius: 8px;
                padding: 6px;
            }}
        """)
        b_lay = QVBoxLayout(bottom_box)
        b_lay.setContentsMargins(8, 6, 8, 6)
        b_lay.setSpacing(4)

        header_row = QHBoxLayout()
        hdr_lbl = QLabel('Band Decay & Tail Persistence (Numeric Evidence):')
        hdr_lbl.setStyleSheet(f"color: {ACCENT_GOLD}; font-weight: 600; font-size: 8.5pt;")
        header_row.addWidget(hdr_lbl, 1)

        self._renderer_badge = ValidityChip(
            text='OpenGL 3D' if self._using_gl else '2D Fallback',
            state='valid' if self._using_gl else 'warn'
        )
        header_row.addWidget(self._renderer_badge, 0)
        b_lay.addLayout(header_row)

        self._decay_text = QTextEdit()
        self._decay_text.setReadOnly(True)
        self._decay_text.setMaximumHeight(90)
        self._decay_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {SURFACE_RAISED};
                border: 1px solid {BORDER_CARD};
                border-radius: 6px;
                color: {TEXT_MAIN};
                font-family: {FONT_FAMILY_MONO};
                font-size: 8.5pt;
                padding: 6px;
            }}
        """)
        b_lay.addWidget(self._decay_text)
        layout.addWidget(bottom_box, 1)

    @property
    def using_opengl(self) -> bool:
        return self._using_gl

    @property
    def current_source(self) -> str:
        """'A' or 'B' — the explicitly selected source (default 'A')."""
        return self._selected

    @property
    def displayed_csd(self):
        """The CSD result currently rendered (None when unavailable)."""
        return self._csd_by_source[self._selected]

    @staticmethod
    def _source_for_mode(mode: str) -> str:
        return 'B' if str(mode).strip().upper().startswith('B') else 'A'

    def show_csd(self, csd_result, mode: str = 'A') -> None:
        """Store one source's result; only the selected source is rendered."""
        if csd_result is None:
            return
        self._csd_by_source[self._source_for_mode(mode)] = csd_result
        self._render_selected()

    def set_sources(self, csd_a, csd_b) -> None:
        """Store both A and B results; keep the user's selection (default A)."""
        self._csd_by_source['A'] = csd_a
        self._csd_by_source['B'] = csd_b
        self._render_selected()

    def reset(self) -> None:
        """Drop stored results and deterministically re-default to A."""
        self._csd_by_source = {'A': None, 'B': None}
        self.btn_source_a.setChecked(True)   # fires _on_source_toggled
        self._selected = 'A'
        self._render_selected()

    def _on_source_toggled(self, _checked: bool) -> None:
        selected = 'B' if self.btn_source_b.isChecked() else 'A'
        if selected != self._selected:
            self._selected = selected
            self._render_selected()

    def _render_selected(self) -> None:
        src = self._selected
        result = self._csd_by_source[src]
        self.source_caption.setText(f'Showing IR {src}')
        if not self._using_gl:
            self._plot.setTitle(f'CSD — IR {src}')
        if (result is None or getattr(result, 'magnitude_db', None) is None or
                getattr(result, 'status', None) not in (None,
                                                        AnalysisStatus.OK)):
            # Selected source has no renderable data yet: show an explicit
            # reason instead of letting the other source's plot stand in.
            self._plot.clear()
            if result is None:
                self._decay_text.setPlainText(
                    f'No CSD result for IR {src} yet.')
            else:
                self._decay_text.setPlainText(
                    f'CSD unavailable for IR {src}: '
                    f'status {getattr(result, "status", "unknown")}.')
            return
        try:
            rendered = self._renderer.render(self._plot, result, src)
            if self._using_gl and not rendered:
                # Invalid mesh data is represented as an empty GL scene; keep
                # numeric evidence visible and do not attempt unsafe 2D calls.
                self._decay_text.setPlainText(f'CSD surface unavailable for IR {src}.')
        except Exception:
            if self._using_gl:
                self._switch_to_fallback()
                try:
                    self._renderer.render(self._plot, result, src)
                except Exception:
                    self._plot.clear()
                    self._decay_text.setPlainText(f'CSD surface unavailable for IR {src}.')
            else:
                self._plot.clear()
                self._decay_text.setPlainText(f'CSD surface unavailable for IR {src}.')
        self._render_decay(result)

    @staticmethod
    def _create_fallback_plot():
        plot = pg.PlotWidget(background=SURFACE_CARD)
        plot.setMouseEnabled(x=True, y=True)
        return plot

    def _switch_to_fallback(self) -> None:
        """Replace a failed GL canvas with the deterministic 2D renderer."""
        if not self._using_gl:
            return
        old_plot = self._plot
        self._plot = self._create_fallback_plot()
        self._plot_layout.replaceWidget(old_plot, self._plot)
        old_plot.deleteLater()
        self._renderer = FallbackCsdRenderer()
        self._using_gl = False
        self._renderer_badge.set_state('warn', '2D Fallback',
                                       'OpenGL unavailable; using deterministic 2D view.')

    def _render_decay(self, csd_result) -> None:
        lines = []
        metrics = csd_result.metrics or {}
        for name, curve in (csd_result.band_decay or {}).items():
            d10 = metrics.get(decay_metric_key(name, 10.0))
            d20 = metrics.get(decay_metric_key(name, 20.0))
            d30 = metrics.get(decay_metric_key(name, 30.0))
            fmt = (lambda v: f'{v:.0f} ms' if isinstance(v, (int, float))
                   else 'n/a')
            # B13: same contract accessor as the producer; each unavailability
            # reason (noisy / insufficient / unsupported / invalid) is shown
            # distinctly instead of one lumped "invalid/noisy" label.
            _valid20, state20 = decay_validity(metrics, name, 20.0)
            valid_tag = _STATE_TAGS.get(state20, ' (invalid)')
            lines.append(f'• {name} Hz Band:  D10 = {fmt(d10):<7}  '
                         f'D20 = {fmt(d20):<7}{valid_tag:<18}  '
                         f'D30 = {fmt(d30)}')
        self._decay_text.setPlainText('\n'.join(lines) or 'No band decay data.')
