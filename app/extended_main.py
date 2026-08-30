"""Extended application entry point (WP-07).

Runs the legacy MainWindow through ExtendedMainWindow, adding the Compare A/B
workbench and Response Search without touching legacy code.
"""
from __future__ import annotations

import sys


def main() -> int:
    if '--selftest' in sys.argv:
        from app.main import run_selftest
        return run_selftest()

    import pyqtgraph as pg
    from PySide6.QtCore import QLocale
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtWidgets import QApplication

    pg.setConfigOptions(antialias=True)
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setApplicationName('BestIR Extended')
    QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))

    from app.ui.styles import BG, MODERN_QSS, TEXT
    app.setStyleSheet(MODERN_QSS)
    pal = app.palette()
    pal.setColor(QPalette.Window, QColor(BG))
    pal.setColor(QPalette.WindowText, QColor(TEXT))
    pal.setColor(QPalette.Base, QColor(BG))
    pal.setColor(QPalette.Text, QColor(TEXT))
    pal.setColor(QPalette.ToolTipBase, QColor(BG))
    app.setPalette(pal)

    from app.extensions.ui.main_window_adapter import ExtendedMainWindow
    win = ExtendedMainWindow()
    win.setWindowTitle('BestIR Extended — IR screener & compare')
    win.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
