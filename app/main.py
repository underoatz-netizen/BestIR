"""BestIR application entry point.

Run:  python -m app.main            (or use run.bat)
"""
from __future__ import annotations

import sys


def run_selftest() -> int:
    """Headless check: analyze one synthetic IR and verify metrics appear."""
    import numpy as np
    from app.core.analysis import analyze_data
    ir = np.zeros((9600, 1))
    ir[48, 0] = 1.0
    res = analyze_data(ir, 48000, path='selftest')
    assert res.flatness_db < 1.0 and 'Flat' in res.tags
    print('BestIR selftest OK')
    return 0


def main() -> int:
    if '--selftest' in sys.argv:
        return run_selftest()

    import pyqtgraph as pg
    from PySide6.QtCore import QLocale
    from PySide6.QtWidgets import QApplication

    pg.setConfigOptions(antialias=True)

    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setApplicationName('BestIR')
    # Latin digits regardless of system locale (Thai digits confuse dB values)
    QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))

    from .ui.styles import BG, MODERN_QSS, TEXT
    from PySide6.QtGui import QPalette, QColor
    app.setStyleSheet(MODERN_QSS)
    pal = app.palette()
    pal.setColor(QPalette.Window, QColor(BG))
    pal.setColor(QPalette.WindowText, QColor(TEXT))
    pal.setColor(QPalette.Base, QColor(BG))
    pal.setColor(QPalette.Text, QColor(TEXT))
    pal.setColor(QPalette.ToolTipBase, QColor(BG))
    app.setPalette(pal)

    from .ui.main_window import MainWindow
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
