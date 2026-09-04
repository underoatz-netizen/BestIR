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

    from app.extensions.ui.styles_boro import (BG_CANVAS, BORO_QSS,
                                                SURFACE_CARD, TEXT_BODY)
    app.setStyleSheet(BORO_QSS)
    pal = app.palette()
    pal.setColor(QPalette.Window, QColor(BG_CANVAS))
    pal.setColor(QPalette.WindowText, QColor(TEXT_BODY))
    pal.setColor(QPalette.Base, QColor(SURFACE_CARD))
    pal.setColor(QPalette.Text, QColor(TEXT_BODY))
    pal.setColor(QPalette.ToolTipBase, QColor(BG_CANVAS))
    app.setPalette(pal)

    # Set Window & Taskbar Icon
    from pathlib import Path
    from PySide6.QtGui import QIcon
    icon_path = Path(__file__).resolve().parent / 'assets' / 'bestir.ico'
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    from app.extensions.ui.main_window_adapter import ExtendedMainWindow
    win = ExtendedMainWindow()
    win.setWindowTitle('BestIR Extended \u2014 IR screener & compare')
    win.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
