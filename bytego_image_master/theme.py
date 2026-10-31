APP_NAME = "BytegoImageMaster"

COLORS = {
    "bg": "#0E1116",
    "surface": "#151A21",
    "surface2": "#1B212B",
    "elevated": "#222A36",
    "border": "#252C38",
    "border_light": "#323B49",
    "text": "#E7ECF3",
    "text_dim": "#9BA6B7",
    "text_mute": "#6C7889",
    "accent": "#4C8DFF",
    "accent_hover": "#6BA1FF",
    "accent_press": "#2F6FE0",
    "accent_soft": "#1D2A44",
    "ok": "#37D399",
    "warn": "#F5A524",
    "danger": "#FF5C6C",
    "danger_soft": "#3A1F27",
    "white": "#FFFFFF",
}

QSS = """
QWidget {{
    background: transparent;
    color: {text};
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
    font-size: 13px;
}}

QMainWindow, #root {{
    background: {bg};
}}

#sidebar {{
    background: {surface};
    border-right: 1px solid {border};
}}

#brandTitle {{
    font-size: 17px;
    font-weight: 700;
    color: {text};
    letter-spacing: 0.3px;
}}

#brandSub {{
    font-size: 11px;
    color: {text_mute};
    letter-spacing: 1.6px;
}}

QPushButton {{
    background: {elevated};
    border: 1px solid {border_light};
    border-radius: 8px;
    padding: 7px 14px;
    color: {text};
}}
QPushButton:hover {{
    background: #2A3342;
    border-color: #3E4A5C;
}}
QPushButton:pressed {{
    background: #1E2531;
}}
QPushButton:disabled {{
    color: {text_mute};
    background: #171C24;
    border-color: {border};
}}

QPushButton#primary {{
    background: {accent};
    border: 1px solid {accent};
    color: {white};
    font-weight: 600;
    padding: 10px 18px;
}}
QPushButton#primary:hover {{
    background: {accent_hover};
    border-color: {accent_hover};
}}
QPushButton#primary:pressed {{
    background: {accent_press};
}}
QPushButton#primary:disabled {{
    background: #2A3546;
    border-color: #2A3546;
    color: #6E7A8C;
}}

QPushButton#ghost {{
    background: transparent;
    border: 1px solid {border_light};
    color: {text_dim};
}}
QPushButton#ghost:hover {{
    color: {text};
    border-color: {accent};
    background: {accent_soft};
}}
QPushButton#ghost:checked {{
    color: {accent};
    border-color: {accent};
    background: {accent_soft};
}}

QPushButton#chip {{
    background: {surface2};
    border: 1px solid {border};
    border-radius: 14px;
    padding: 5px 12px;
    color: {text_dim};
    font-size: 12px;
}}
QPushButton#chip:hover {{
    color: {text};
    border-color: {accent};
}}
QPushButton#chip:checked {{
    color: {white};
    background: {accent_soft};
    border-color: {accent};
}}

QPushButton#danger {{
    background: {danger_soft};
    border: 1px solid #5A2A33;
    color: {danger};
}}
QPushButton#danger:hover {{
    background: #4A2630;
}}

QToolButton#nav {{
    background: transparent;
    border: none;
    border-radius: 9px;
    padding: 10px 12px;
    color: {text_dim};
    text-align: left;
    font-size: 13px;
}}
QToolButton#nav:hover {{
    background: {surface2};
    color: {text};
}}
QToolButton#nav:checked {{
    background: {accent_soft};
    color: {white};
    font-weight: 600;
}}

QFrame#card {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 14px;
}}

QFrame#cardFlat {{
    background: {surface2};
    border: 1px solid {border};
    border-radius: 12px;
}}

QFrame#topbar {{
    background: {surface};
    border-bottom: 1px solid {border};
}}

QLabel#cardTitle {{
    font-size: 13px;
    font-weight: 600;
    color: {text};
}}

QLabel#hint {{
    color: {text_mute};
    font-size: 11px;
}}

QLabel#muted {{
    color: {text_dim};
}}

QLabel#sectionTitle {{
    font-size: 15px;
    font-weight: 700;
    color: {text};
}}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
    background: {surface2};
    border: 1px solid {border_light};
    border-radius: 9px;
    padding: 7px 10px;
    color: {text};
    selection-background-color: {accent};
    selection-color: {white};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: {accent};
    background: #1E2531;
}}
QLineEdit::placeholder {{
    color: {text_mute};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background: {elevated};
    border: 1px solid {border_light};
    border-radius: 8px;
    selection-background-color: {accent_soft};
    selection-color: {white};
    padding: 4px;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    width: 0;
    border: none;
}}

QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #333C4B;
    border-radius: 5px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{
    background: #435064;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

QListWidget, QTreeWidget, QTableWidget {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 10px;
    outline: none;
}}
QListWidget::item {{
    padding: 8px;
    border-radius: 8px;
}}
QListWidget::item:selected {{
    background: {accent_soft};
}}

QCheckBox, QRadioButton {{
    spacing: 8px;
    color: {text_dim};
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {border_light};
    border-radius: 4px;
    background: {surface2};
}}
QRadioButton::indicator {{
    border-radius: 8px;
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {accent};
    border-color: {accent};
}}

QFrame#modelRow {{
    background: transparent;
}}
QLabel#modelName {{
    color: {text_dim};
    font-size: 12px;
    padding: 2px 0;
}}
QCheckBox#modelItem {{
    color: {text_dim};
    font-size: 12px;
}}
QLabel#modelBadge {{
    color: {bg};
    background: {accent};
    border-radius: 7px;
    font-size: 10px;
    font-weight: bold;
}}

QLabel#bigTimer {{
    color: {accent};
    font-size: 17px;
    font-weight: 700;
    letter-spacing: 0.4px;
}}

QLabel#devLine {{
    color: {text_mute};
    font-size: 11px;
}}

QFrame#devCard {{
    background: {surface2};
    border: 1px solid {border};
    border-radius: 10px;
}}

QMenu {{
    background: {elevated};
    border: 1px solid {border_light};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{
    padding: 6px 22px 6px 14px;
    border-radius: 7px;
    color: {text_dim};
}}
QMenu::item:selected {{
    background: {accent_soft};
    color: {text};
}}
QMenu::separator {{
    height: 1px;
    background: {border};
    margin: 4px 8px;
}}

QProgressBar {{
    background: {surface2};
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
}}
QProgressBar::chunk {{
    background: {accent};
    border-radius: 4px;
}}

QSplitter::handle {{
    background: transparent;
}}
QSplitter::handle:hover {{
    background: {accent_soft};
}}

QGroupBox {{
    border: 1px solid {border};
    border-radius: 12px;
    margin-top: 14px;
    padding: 12px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {text_dim};
}}

QSplitter::handle {{
    background: transparent;
}}

QToolTip {{
    background: {elevated};
    color: {text};
    border: 1px solid {border_light};
    padding: 5px;
}}

#statusPill {{
    background: {surface2};
    border: 1px solid {border};
    border-radius: 12px;
    padding: 3px 10px;
    color: {text_dim};
    font-size: 11px;
}}

#bottomBar {{
    background: {surface};
    border-top: 1px solid {border};
}}
"""


def build_qss() -> str:
    return QSS.format(**COLORS)
