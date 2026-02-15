"""HHAT 메인 애플리케이션 윈도우

레이아웃:
  ┌──────────────────────────────────────────────────────────────┐
  │                  [ 관측 ]    [ 분석 ]                         │
  ├──────────────────────────────────────────────────────────────┤
  │                                                              │
  │   관측 탭: SDR 연결 / 파라미터 / 타입 선택 / 관측 실행          │
  │                                                              │
  │   분석 탭: Step 1~13 파이프라인 (좌측 네비게이션 + 우측 Step)    │
  │                                                              │
  └──────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QTabWidget,
)

from src.observe.observe_tab import ObserveTab
from src.analysis.analysis_tab import AnalysisTab


DARK_STYLE = """
QMainWindow, QWidget { background: #1e1e2e; color: #e0e0e0; }

/* ── 상위 탭 (관측/분석) ── */
QTabWidget#mainTabs > QTabBar::tab {
    background: #16162a; color: #888; padding: 12px 36px;
    border: none; border-bottom: 3px solid transparent;
    font-size: 14px; font-weight: bold;
}
QTabWidget#mainTabs > QTabBar::tab:selected {
    color: #66ccff; border-bottom: 3px solid #3a7bd5; background: #1e1e2e;
}
QTabWidget#mainTabs > QTabBar::tab:hover { color: #aadcff; background: #22223a; }
QTabWidget#mainTabs::pane { border: none; border-top: 1px solid #333; }

QGroupBox {
    border: 1px solid #444; border-radius: 4px;
    margin-top: 8px; padding-top: 16px; color: #ccc; font-weight: bold;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    background: #2a2a3e; color: white; border: 1px solid #555;
    padding: 4px; border-radius: 3px;
}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover { border-color: #3a7bd5; }
QComboBox::drop-down { border: none; }
QPushButton {
    background: #3a3a5e; color: white; padding: 6px 12px;
    border: 1px solid #555; border-radius: 4px;
}
QPushButton:hover { background: #4a4a6e; border-color: #3a7bd5; }
QSlider::groove:horizontal { height: 6px; background: #444; border-radius: 3px; }
QSlider::handle:horizontal {
    background: #3a7bd5; width: 14px; margin: -4px 0; border-radius: 7px;
}
QSplitter::handle { background: #444; }
QStatusBar { background: #16162a; color: #aaa; }
QTextEdit { background: #16162a; color: #ccc; border: 1px solid #444; }
QScrollBar:vertical { background: #1e1e2e; width: 10px; border: none; }
QScrollBar::handle:vertical { background: #555; border-radius: 5px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QTreeWidget {
    background: #1e1e2e; color: white; border: 1px solid #444;
    alternate-background-color: #252540;
}
QTreeWidget::item:selected { background: #3a7bd5; }
QHeaderView::section {
    background: #2a2a3e; color: white; border: 1px solid #444;
    padding: 4px; font-weight: bold;
}
QCheckBox { spacing: 6px; }
QRadioButton { spacing: 6px; }
QProgressBar {
    background: #2a2a3e; border: 1px solid #444; border-radius: 3px;
    text-align: center; color: white; font-size: 11px;
}
QProgressBar::chunk { background: #3a7bd5; border-radius: 3px; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HHAT — HI Horn Antenna Analysis Tool")
        self.setMinimumSize(1300, 800)
        self.setStyleSheet(DARK_STYLE)

        self._setup_ui()
        self.statusBar().showMessage("HHAT v0.1 — 관측 또는 분석 탭을 선택하세요.")

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.main_tabs = QTabWidget()
        self.main_tabs.setObjectName("mainTabs")

        # ■ 관측 탭
        self.observe_tab = ObserveTab()
        self.main_tabs.addTab(self.observe_tab, "  관측  ")

        # ■ 분석 탭
        self.analysis_tab = AnalysisTab()
        self.main_tabs.addTab(self.analysis_tab, "  분석  ")

        # 관측 완료 → 분석 탭에 데이터 전달
        self.observe_tab.observation_completed.connect(self._on_observation_done)

        # 탭 변경 시 초기화
        self.main_tabs.currentChanged.connect(self._on_tab_changed)

        layout.addWidget(self.main_tabs)

    @Slot(str)
    def _on_observation_done(self, folder: str):
        """관측 완료 후 분석 탭에 자동 로드 + 탭 전환"""
        self.analysis_tab.load_observation_folder(folder)
        self.main_tabs.setCurrentWidget(self.analysis_tab)
        self.statusBar().showMessage(f"관측 완료: {folder} — 분석 탭으로 이동됨")

    @Slot(int)
    def _on_tab_changed(self, index: int):
        if index == 0:
            self.observe_tab.initialize()
