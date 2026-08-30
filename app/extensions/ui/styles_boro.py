"""Boro UI Design System for BestIR Compare Workbench & Extensions.

Directly adapted from Figma Boro UI specifications:
- Matte Obsidian / Dark Graphite layered surfaces (#080808, #141414, #1a1a1a, #212121)
- Golden Honey / Amber accents (#fec903, #fed215, #f2c503)
- Signal semantics: Electric Cyan (#58bcf8 for IR A), Emerald (#42cf00 / #5fcd8b for IR B),
  Coral (#ee7b69 / #ff1e1c for Comb Risk & Differences)
- Tactile soft neumorphic / contrast borders (#2c2c2c, #393939)
- High-glanceability tabular figures and compact metric cards
"""
from __future__ import annotations

# ---- Base Canvas & Surfaces ----
BG_CANVAS = '#080808'          # main app/dialog canvas
SURFACE_CARD = '#141414'       # card backgrounds
SURFACE_RAISED = '#1a1a1a'     # raised cards, inputs, tabs
SURFACE_HOVER = '#242424'      # hover state
BORDER_SUBTLE = '#222222'      # subtle 1px border
BORDER_CARD = '#2c2c2c'        # card border
BORDER_FOCUS = '#3e3e3e'       # focus border

# ---- Typography ----
TEXT_MAIN = '#ffffff'          # primary headings and values
TEXT_BODY = '#eceff5'          # body text
TEXT_MUTED = '#949494'         # labels and secondary units
TEXT_DISABLED = '#575757'      # disabled text
FONT_FAMILY_PRIMARY = 'Segoe UI, Arial, sans-serif'
FONT_FAMILY_MONO = 'Consolas, monospace'

# ---- Boro Signature Accents ----
ACCENT_GOLD = '#fec903'        # primary Boro yellow/gold
ACCENT_GOLD_HOVER = '#fed215'  # hover yellow
ACCENT_GOLD_DIM = '#c2a203'    # pressed / dim yellow
ACCENT_GOLD_BG = '#282200'     # subtle gold container background
ACCENT_GOLD_BORDER = '#524400' # gold container border

# ---- Domain Identities (IR A vs IR B) ----
COLOR_IR_A = '#58bcf8'         # Electric Cyan for IR A
COLOR_IR_A_BG = '#0d2230'      # Cyan container bg
COLOR_IR_A_BORDER = '#154160'  # Cyan border

COLOR_IR_B = '#42cf00'         # Neon Emerald Green for IR B
COLOR_IR_B_BG = '#0e2b02'      # Emerald container bg
COLOR_IR_B_BORDER = '#1a4e05'  # Emerald border

COLOR_DIFF = '#ee7b69'         # Coral Orange (A-B difference / comb risk)
COLOR_DIFF_BG = '#301511'      # Coral container bg
COLOR_DIFF_BORDER = '#5c231b'  # Coral border

# ---- Acoustic Validity Chips ----
COLOR_VALID = '#42cf00'
COLOR_VALID_BG = '#0c2604'
COLOR_VALID_BORDER = '#1a4e05'

COLOR_WARN = '#fec903'
COLOR_WARN_BG = '#282200'
COLOR_WARN_BORDER = '#524400'

COLOR_INVALID = '#ff1e1c'
COLOR_INVALID_BG = '#330807'
COLOR_INVALID_BORDER = '#661210'


BORO_QSS = f"""
* {{
    outline: none;
}}

QDialog, QWidget {{
    background-color: {BG_CANVAS};
    color: {TEXT_BODY};
    font-family: {FONT_FAMILY_PRIMARY};
    font-size: 9pt;
}}

/* ---- Tactile Boro Cards ---- */
QGroupBox {{
    background-color: {SURFACE_CARD};
    border: 1px solid {BORDER_CARD};
    border-radius: 10px;
    margin-top: 14px;
    padding: 12px 8px 8px 8px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    top: 4px;
    color: {ACCENT_GOLD};
    font-size: 8.5pt;
    letter-spacing: 0.5px;
}}

/* ---- Boro Tabs ---- */
QTabWidget::pane {{
    border: 1px solid {BORDER_CARD};
    background-color: {SURFACE_CARD};
    border-radius: 10px;
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_MUTED};
    padding: 8px 18px;
    font-weight: 500;
    font-size: 9pt;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 4px;
}}
QTabBar::tab:selected {{
    color: {ACCENT_GOLD};
    font-weight: 600;
    border-bottom: 2px solid {ACCENT_GOLD};
}}
QTabBar::tab:hover:!selected {{
    color: {TEXT_MAIN};
    background: {SURFACE_RAISED};
    border-radius: 6px 6px 0 0;
}}

/* ---- Inputs & Dropdowns ---- */
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {{
    background-color: {SURFACE_RAISED};
    color: {TEXT_MAIN};
    border: 1px solid {BORDER_CARD};
    border-radius: 8px;
    padding: 6px 10px;
    selection-background-color: {ACCENT_GOLD_BG};
    selection-color: {ACCENT_GOLD};
    font-family: {FONT_FAMILY_MONO};
}}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
    border: 1px solid {ACCENT_GOLD};
}}
QLineEdit:disabled, QComboBox:disabled, QDoubleSpinBox:disabled {{
    color: {TEXT_DISABLED};
    border-color: {BORDER_SUBTLE};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: {SURFACE_CARD};
    border: 1px solid {BORDER_CARD};
    border-radius: 8px;
    selection-background-color: {ACCENT_GOLD_BG};
    selection-color: {ACCENT_GOLD};
    outline: 0;
    padding: 4px;
}}
QDoubleSpinBox::up-button, QSpinBox::up-button,
QDoubleSpinBox::down-button, QSpinBox::down-button {{
    background: {SURFACE_CARD};
    border: none;
    width: 16px;
    border-radius: 4px;
}}

/* ---- Tactile Buttons ---- */
QPushButton {{
    background-color: {SURFACE_RAISED};
    color: {TEXT_MAIN};
    border: 1px solid {BORDER_CARD};
    border-radius: 8px;
    padding: 6px 14px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {SURFACE_HOVER};
    border-color: {BORDER_FOCUS};
}}
QPushButton:pressed {{
    background-color: {SURFACE_CARD};
}}
QPushButton:disabled {{
    color: {TEXT_DISABLED};
    background-color: {SURFACE_CARD};
    border-color: {BORDER_SUBTLE};
}}

/* Boro Signature Golden Action Button */
QPushButton#primaryGoldBtn, QPushButton[primary="true"] {{
    background-color: {ACCENT_GOLD};
    color: #000000;
    border: 1px solid {ACCENT_GOLD_HOVER};
    font-weight: 600;
}}
QPushButton#primaryGoldBtn:hover, QPushButton[primary="true"]:hover {{
    background-color: {ACCENT_GOLD_HOVER};
}}
QPushButton#primaryGoldBtn:pressed, QPushButton[primary="true"]:pressed {{
    background-color: {ACCENT_GOLD_DIM};
}}

/* ---- Boro Tactile Slider ---- */
QSlider::groove:horizontal {{
    height: 6px;
    background: {SURFACE_RAISED};
    border: 1px solid {BORDER_CARD};
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT_GOLD};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
    background: #ffffff;
    border: 2px solid {ACCENT_GOLD};
}}
QSlider::handle:horizontal:hover {{
    background: {ACCENT_GOLD};
    border: 2px solid #ffffff;
}}

/* ---- Tables ---- */
QTableWidget, QTableView {{
    background-color: {SURFACE_CARD};
    alternate-background-color: #111111;
    border: 1px solid {BORDER_CARD};
    border-radius: 8px;
    gridline-color: {BORDER_SUBTLE};
    selection-background-color: {ACCENT_GOLD_BG};
    selection-color: {ACCENT_GOLD};
    font-family: {FONT_FAMILY_MONO};
}}
QHeaderView::section {{
    background-color: {SURFACE_RAISED};
    color: {TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {BORDER_CARD};
    padding: 6px 8px;
    font-weight: 600;
    font-size: 8.5pt;
}}

/* ---- Text Edits ---- */
QTextEdit {{
    background-color: {SURFACE_CARD};
    border: 1px solid {BORDER_CARD};
    border-radius: 8px;
    padding: 8px;
    color: {TEXT_BODY};
    font-family: {FONT_FAMILY_PRIMARY};
}}

/* ---- Scrollbars ---- */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #2a2a2a;
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: #3e3e3e;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #2a2a2a;
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: #3e3e3e;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0;
    height: 0;
}}

/* ---- Main Window & Splitters ---- */
QMainWindow::separator {{
    background: {BG_CANVAS};
    width: 4px;
}}
QSplitter::handle {{
    background: {BG_CANVAS};
}}

/* ---- List Widgets ---- */
QListWidget {{
    background-color: {SURFACE_CARD};
    border: 1px solid {BORDER_CARD};
    border-radius: 8px;
}}
QListWidget::item {{
    padding: 4px 8px;
    border-radius: 6px;
}}
QListWidget::item:selected {{
    background-color: {ACCENT_GOLD_BG};
    color: {ACCENT_GOLD};
}}
QListWidget::item:hover:!selected {{
    background-color: {SURFACE_HOVER};
}}

/* ---- Progress Bars ---- */
QProgressBar {{
    border: 1px solid {BORDER_CARD};
    border-radius: 4px;
    background: {SURFACE_CARD};
    text-align: center;
    color: {TEXT_MUTED};
}}
QProgressBar::chunk {{
    background: {ACCENT_GOLD};
    border-radius: 3px;
}}

/* ---- Checkboxes ---- */
QCheckBox {{
    spacing: 6px;
    color: {TEXT_BODY};
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {BORDER_CARD};
    border-radius: 4px;
    background: {SURFACE_RAISED};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT_GOLD};
    border-color: {ACCENT_GOLD};
}}

/* ---- Status Bar ---- */
QStatusBar {{
    background: {BG_CANVAS};
    color: {TEXT_MUTED};
    border-top: 1px solid {BORDER_SUBTLE};
}}
QStatusBar::item {{
    border: none;
}}

/* ---- Tooltips ---- */
QToolTip {{
    background: {SURFACE_RAISED};
    color: {TEXT_BODY};
    border: 1px solid {BORDER_CARD};
    border-radius: 6px;
    padding: 5px 8px;
}}

/* ---- Toolbar ---- */
QToolBar {{
    background: {BG_CANVAS};
    border-bottom: 1px solid {BORDER_CARD};
    spacing: 4px;
    padding: 2px 6px;
}}
QToolBar::separator {{
    background: {BORDER_CARD};
    width: 1px;
    margin: 4px 6px;
}}
QToolButton {{
    background: transparent;
    color: {TEXT_BODY};
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 5px 12px;
    font-weight: 500;
}}
QToolButton:hover {{
    background: {SURFACE_RAISED};
    border-color: {BORDER_CARD};
    color: {ACCENT_GOLD};
}}
QToolButton:pressed {{
    background: {SURFACE_CARD};
}}
QToolButton:checked {{
    background: {ACCENT_GOLD_BG};
    color: {ACCENT_GOLD};
    border-color: {ACCENT_GOLD_BORDER};
}}

/* ---- Table Corner ---- */
QTableCornerButton::section {{
    background: {SURFACE_RAISED};
    border: none;
}}
"""

