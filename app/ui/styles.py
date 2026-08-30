"""Central design tokens + modern minimal stylesheet for BestIR."""
from __future__ import annotations

BG = '#15171c'          # app background
SURFACE = '#1b1e24'     # cards, inputs, plot
SURFACE2 = '#232830'    # hover / pressed / controls
BORDER = '#2a303a'
TEXT = '#e3e7ee'
TEXT_DIM = '#98a1af'
ACCENT = '#5c9ce0'
ACCENT_SOFT = '#37587e'
GREEN = '#66d18a'
RED = '#e07a7a'

MODERN_QSS = f"""
* {{
    outline: none;
}}
QWidget {{
    background: {BG};
    color: {TEXT};
    font-size: 9pt;
}}
QMainWindow::separator {{
    background: {BG};
    width: 4px;
}}
QSplitter::handle {{
    background: {BG};
}}

/* ---- inputs ------------------------------------------------------------ */
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: {ACCENT_SOFT};
}}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
    border-color: {ACCENT};
}}
QLineEdit:disabled, QComboBox:disabled, QDoubleSpinBox:disabled {{
    color: {TEXT_DIM};
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    selection-background-color: {ACCENT_SOFT};
    selection-color: {TEXT};
    outline: 0;
}}
QDoubleSpinBox::up-button, QSpinBox::up-button,
QDoubleSpinBox::down-button, QSpinBox::down-button {{
    background: {SURFACE2};
    border: none;
    width: 14px;
}}

/* ---- buttons ----------------------------------------------------------- */
QPushButton {{
    background: {SURFACE2};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 10px;
}}
QPushButton:hover {{
    background: #2a3039;
    border-color: #3a4150;
}}
QPushButton:pressed {{
    background: {SURFACE};
}}
QPushButton:disabled {{
    color: #5b6270;
    background: {SURFACE};
}}
QPushButton:default {{
    background: {ACCENT_SOFT};
    border-color: #46648c;
}}
QPushButton:default:hover {{
    background: #406193;
}}

/* ---- table ------------------------------------------------------------- */
QTableView {{
    background: {SURFACE};
    alternate-background-color: #1e2129;
    border: 1px solid {BORDER};
    border-radius: 6px;
    gridline-color: #22262e;
    selection-background-color: #2a3f5c;
    selection-color: {TEXT};
}}
QHeaderView::section {{
    background: {SURFACE};
    color: {TEXT_DIM};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 5px 6px;
}}
QTableCornerButton::section {{
    background: {SURFACE};
    border: none;
}}

/* ---- tabs -------------------------------------------------------------- */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_DIM};
    padding: 6px 14px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    color: {TEXT};
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover:!selected {{
    color: #c3cad4;
}}

/* ---- lists ------------------------------------------------------------- */
QListWidget {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}
QListWidget::item {{
    padding: 4px 8px;
    border-radius: 4px;
}}
QListWidget::item:selected {{
    background: #2a3f5c;
    color: {TEXT};
}}
QListWidget::item:hover:!selected {{
    background: {SURFACE2};
}}

/* ---- sliders / progress / checkbox -------------------------------------- */
QSlider::groove:horizontal {{
    height: 4px;
    background: {BORDER};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT_SOFT};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 13px;
    height: 13px;
    margin: -5px 0;
    border-radius: 6px;
    background: #cfd6e0;
}}
QSlider::handle:horizontal:hover {{
    background: {ACCENT};
}}
QProgressBar {{
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: {SURFACE};
    text-align: center;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 3px;
}}
QCheckBox {{
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: {SURFACE};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 10px;
    padding: 8px 4px 4px 4px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    color: {TEXT_DIM};
}}

/* ---- bars / status / tooltip / scrollbars ------------------------------- */
QStatusBar {{
    background: {BG};
    color: {TEXT_DIM};
}}
QStatusBar::item {{
    border: none;
}}
QToolTip {{
    background: {SURFACE2};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 5px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #2e3440;
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #3a4150;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #2e3440;
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: #3a4150;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
"""
