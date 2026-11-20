"""Vanyajeev visual theme: warm dark savanna palette with an ochre-gold accent."""
import sys

FONT = 'Segoe UI Variable Text' if sys.platform == 'win32' else 'Inter'
BG = '#14120f'
PANEL = '#1b1815'
SURFACE = '#24201c'
SURFACE_HI = '#2e2924'
BORDER = '#3a342e'
TEXT = '#efe8dd'
MUTED = '#9c9389'
ACCENT = '#d9a441'
ACCENT_HI = '#e9b95c'
ACCENT_TEXT = '#1a1510'
CANVAS = '#0f0e0c'

QSS = f"""
* {{ font-family: "{FONT}", "Segoe UI", "Inter", sans-serif; font-size: 10pt; color: {TEXT}; }}
QMainWindow, QWidget#root {{ background: {BG}; }}
QFrame#header {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; }}
QFrame#sidebar, QFrame#inspector {{ background: {PANEL}; }}
QFrame#sidebar {{ border-right: 1px solid {BORDER}; }}
QFrame#inspector {{ border-left: 1px solid {BORDER}; }}
QFrame#toolbar {{ background: {BG}; border-bottom: 1px solid {BORDER}; }}
QLabel#wordmark {{ font-size: 15pt; font-weight: 600; letter-spacing: 0.5px; }}
QLabel#devanagari {{ color: {ACCENT}; font-size: 11pt; }}
QLabel#section {{ color: {MUTED}; font-size: 8pt; font-weight: 700; letter-spacing: 1.4px; padding-top: 10px; }}
QLabel#muted, QLabel#hint {{ color: {MUTED}; }}
QLabel#hint {{ font-size: 9pt; }}
QLabel#value {{ color: {ACCENT}; font-weight: 600; }}
QLabel#info {{ color: {MUTED}; font-size: 9pt; background: {SURFACE}; border-radius: 8px; padding: 10px; }}

QPushButton {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; padding: 7px 14px; }}
QPushButton:hover {{ background: {SURFACE_HI}; border-color: #4a433b; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: #5e5750; border-color: #2c2823; }}
QPushButton#primary {{ background: {ACCENT}; color: {ACCENT_TEXT}; border: none; font-weight: 600; }}
QPushButton#primary:hover {{ background: {ACCENT_HI}; }}
QPushButton#primary:disabled {{ background: #5b4a2c; color: #2a2318; }}
QPushButton#ghost {{ background: transparent; border: none; color: {MUTED}; padding: 4px 8px; }}
QPushButton#ghost:hover {{ color: {TEXT}; }}
QPushButton#seg {{ background: transparent; border: none; border-radius: 7px; padding: 6px 14px; color: {MUTED}; }}
QPushButton#seg:hover {{ color: {TEXT}; background: {SURFACE}; }}
QPushButton#seg:checked {{ background: {SURFACE_HI}; color: {TEXT}; }}
QFrame#segbox {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 9px; }}

QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ border-radius: 10px; padding: 6px; margin: 3px; color: {MUTED}; }}
QListWidget::item:hover {{ background: {SURFACE}; }}
QListWidget::item:selected {{ background: {SURFACE_HI}; color: {TEXT}; border: 1px solid {ACCENT}; }}

QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {TEXT}; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; }}
QSlider::handle:horizontal:hover {{ background: #ffffff; }}

QCheckBox {{ spacing: 10px; }}
QCheckBox::indicator {{ width: 34px; height: 18px; border-radius: 9px; background: {BORDER}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; }}

QComboBox, QLineEdit {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px 10px; }}
QComboBox:hover, QLineEdit:hover {{ border-color: #4a433b; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {SURFACE}; border: 1px solid {BORDER}; selection-background-color: {SURFACE_HI}; }}

QScrollArea {{ background: transparent; border: none; }}
QWidget#inspectorBody {{ background: {PANEL}; }}
QStatusBar QLabel {{ padding-left: 10px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

QStatusBar {{ background: {PANEL}; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QProgressBar {{ background: {SURFACE}; border: none; border-radius: 4px; height: 8px; max-height: 8px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
QToolTip {{ background: {SURFACE_HI}; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px; border-radius: 6px; }}
"""


def apply_palette(app):
    from PySide6.QtGui import QPalette, QColor
    pal = QPalette()
    for role, col in ((QPalette.Window, BG), (QPalette.WindowText, TEXT), (QPalette.Base, SURFACE),
                      (QPalette.AlternateBase, PANEL), (QPalette.Text, TEXT), (QPalette.Button, SURFACE),
                      (QPalette.ButtonText, TEXT), (QPalette.Highlight, ACCENT), (QPalette.HighlightedText, ACCENT_TEXT),
                      (QPalette.ToolTipBase, SURFACE_HI), (QPalette.ToolTipText, TEXT), (QPalette.PlaceholderText, MUTED),
                      (QPalette.Link, ACCENT)):
        pal.setColor(role, QColor(col))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor('#6b635b'))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor('#6b635b'))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor('#6b635b'))
    app.setPalette(pal)
