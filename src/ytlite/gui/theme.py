"""Dark theme. Flat colours only: no gradients, shadows, blur or animations."""

BG = "#101318"
SIDEBAR = "#151A22"
CARD = "#1B222D"
BLUE = "#2878E5"
TEXT = "#F4F6FA"
TEXT2 = "#A0A8B5"
BORDER = "#29313D"
HOVER = "#202B3A"
WARN = "#E5A028"
ERROR = "#E5604F"
OK = "#4FBF7F"


def stylesheet() -> str:
    return f"""
* {{ font-family: "Segoe UI", "Noto Sans", sans-serif; font-size: 9pt; }}
QMainWindow, QWidget {{ background: {BG}; color: {TEXT}; }}
QToolTip {{ background: {CARD}; color: {TEXT}; border: 1px solid {BORDER}; padding: 3px; }}
QLabel {{ background: transparent; }}
QLabel#Secondary {{ color: {TEXT2}; }}
QLabel#Heading {{ font-size: 13pt; font-weight: 600; }}
QLabel#Logo {{ font-size: 12pt; font-weight: 700; padding: 0 8px; }}
QLabel#Warn {{ color: {WARN}; }}
QLabel#Error {{ color: {ERROR}; }}
QLabel#Badge {{ background: rgba(0,0,0,200); color: {TEXT}; padding: 0 4px; border-radius: 2px; font-size: 8pt; }}
QLabel#Pill {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 9px; padding: 2px 8px; color: {TEXT2}; }}
QLabel#CardTitle {{ font-weight: 600; }}
QFrame#Header {{ background: {SIDEBAR}; border-bottom: 1px solid {BORDER}; }}
QFrame#Sidebar {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
QFrame#Card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 6px; }}
QFrame#Card:hover {{ background: {HOVER}; border-color: {BLUE}; }}
QFrame#Panel {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 6px; }}
QLabel#Thumb {{ background: #0B0E12; border-radius: 4px; color: {TEXT2}; }}
QPushButton, QToolButton {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 4px;
    padding: 4px 10px; color: {TEXT}; }}
QPushButton:hover, QToolButton:hover {{ background: {HOVER}; }}
QPushButton:disabled, QToolButton:disabled {{ color: #5E6672; }}
QPushButton#Primary {{ background: {BLUE}; border-color: {BLUE}; font-weight: 600; }}
QPushButton#Primary:hover {{ background: #3A88F0; }}
QPushButton#Danger:hover {{ background: #5A2A28; border-color: {ERROR}; }}
QToolButton#Nav {{ background: transparent; border: none; border-radius: 4px; padding: 8px 12px; text-align: left; }}
QToolButton#Nav:hover {{ background: {HOVER}; }}
QToolButton#Nav:checked {{ background: {HOVER}; color: {BLUE}; font-weight: 600; }}
QToolButton#Chip {{ border-radius: 12px; padding: 3px 12px; }}
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{ background: {BG}; border: 1px solid {BORDER};
    border-radius: 4px; padding: 4px 6px; color: {TEXT}; selection-background-color: {BLUE}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border-color: {BLUE}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{ background: {CARD}; color: {TEXT}; border: 1px solid {BORDER};
    selection-background-color: {BLUE}; outline: 0; }}
QCheckBox {{ spacing: 6px; background: transparent; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {BORDER}; border-radius: 3px; background: {BG}; }}
QCheckBox::indicator:checked {{ background: {BLUE}; border-color: {BLUE}; }}
QScrollArea {{ border: none; background: {BG}; }}
QScrollBar:vertical {{ background: {BG}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: #3A4452; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: {BG}; height: 10px; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 4px; min-width: 24px; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 4px; top: -1px; }}
QTabBar::tab {{ background: {SIDEBAR}; padding: 6px 12px; border: 1px solid {BORDER}; border-bottom: none;
    border-top-left-radius: 4px; border-top-right-radius: 4px; color: {TEXT2}; }}
QTabBar::tab:selected {{ background: {CARD}; color: {TEXT}; }}
QTableWidget {{ background: {BG}; gridline-color: {BORDER}; border: 1px solid {BORDER};
    selection-background-color: {BLUE}; selection-color: {TEXT}; }}
QHeaderView::section {{ background: {SIDEBAR}; color: {TEXT2}; border: none; border-right: 1px solid {BORDER};
    padding: 4px 6px; }}
QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {BLUE}; width: 12px; margin: -5px 0; border-radius: 6px; }}
QStatusBar {{ background: {SIDEBAR}; color: {TEXT2}; border-top: 1px solid {BORDER}; }}
QMenu {{ background: {CARD}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 5px 22px; border-radius: 3px; }}
QMenu::item:selected {{ background: {BLUE}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}
QMessageBox, QDialog {{ background: {BG}; }}
"""
