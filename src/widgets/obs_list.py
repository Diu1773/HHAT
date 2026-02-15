"""관측 리스트 위젯 (Step 1-2)"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QComboBox, QLabel, QFileDialog, QHeaderView,
)

from src.models.observation import Observation, ObsType, QCStatus


# QC 상태별 색상
QC_COLORS = {
    QCStatus.OK: QColor("#4caf50"),
    QCStatus.WARN: QColor("#ff9800"),
    QCStatus.BAD: QColor("#f44336"),
    QCStatus.UNCHECKED: QColor("#888888"),
}

OBS_TYPE_LABELS = {
    ObsType.SOU: "SOU (Source)",
    ObsType.AMB: "AMB (Ambient)",
    ObsType.SKY: "SKY (Sky)",
    ObsType.UNKNOWN: "UNKNOWN",
}


class ObsListWidget(QWidget):
    """관측 리스트 + 폴더 선택 위젯"""

    observation_selected = Signal(int)  # 선택된 관측 인덱스
    folder_opened = Signal(str)         # 폴더 경로
    type_changed = Signal(int, str)     # (인덱스, 새 타입)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._observations: list[Observation] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # 폴더 열기 버튼
        btn_layout = QHBoxLayout()
        self.btn_open = QPushButton("폴더 열기")
        self.btn_open.setStyleSheet(
            "QPushButton { background: #3a7bd5; color: white; padding: 6px 12px; "
            "border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background: #2a6bc5; }"
        )
        self.btn_open.clicked.connect(self._on_open_folder)
        btn_layout.addWidget(self.btn_open)
        layout.addLayout(btn_layout)

        # 경고 배지
        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet("color: #ff9800; font-size: 11px; padding: 2px;")
        self.warning_label.hide()
        layout.addWidget(self.warning_label)

        # 트리 위젯
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["ID", "날짜/시간", "타입", "QC", "NFFT"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setStyleSheet("""
            QTreeWidget {
                background: #1e1e2e; color: white; border: 1px solid #444;
                alternate-background-color: #252540;
                font-size: 12px;
            }
            QTreeWidget::item:selected { background: #3a7bd5; }
            QHeaderView::section {
                background: #2a2a3e; color: white; border: 1px solid #444;
                padding: 4px; font-weight: bold;
            }
        """)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self.tree.currentItemChanged.connect(self._on_selection_changed)
        layout.addWidget(self.tree)

        # 하단 요약
        self.summary_label = QLabel("관측 0개")
        self.summary_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(self.summary_label)

    def _on_open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "관측 데이터 폴더 선택")
        if folder:
            self.folder_opened.emit(folder)

    def _on_selection_changed(self, current: QTreeWidgetItem, _previous):
        if current is not None:
            idx = self.tree.indexOfTopLevelItem(current)
            if idx >= 0:
                self.observation_selected.emit(idx)

    def set_observations(self, observations: list[Observation]):
        """관측 리스트를 갱신한다."""
        self._observations = observations
        self.tree.clear()

        unknown_count = 0
        for obs in observations:
            item = QTreeWidgetItem([
                obs.display_name,
                obs.date_obs,
                obs.obs_type.value,
                obs.qc.status.value,
                str(obs.nfft),
            ])

            # QC 색상
            qc_color = QC_COLORS.get(obs.qc.status, QColor("#888"))
            item.setForeground(3, qc_color)

            # 타입 색상
            if obs.obs_type == ObsType.UNKNOWN:
                item.setForeground(2, QColor("#ff9800"))
                unknown_count += 1

            self.tree.addTopLevelItem(item)

        # 경고 배지
        if unknown_count > 0:
            self.warning_label.setText(f"⚠ 타입 미지정 {unknown_count}개")
            self.warning_label.show()
        else:
            self.warning_label.hide()

        self.summary_label.setText(f"관측 {len(observations)}개")

    def update_observation(self, idx: int, obs: Observation):
        """특정 인덱스의 관측 정보를 갱신한다."""
        if 0 <= idx < self.tree.topLevelItemCount():
            item = self.tree.topLevelItem(idx)
            item.setText(2, obs.obs_type.value)
            item.setText(3, obs.qc.status.value)
            qc_color = QC_COLORS.get(obs.qc.status, QColor("#888"))
            item.setForeground(3, qc_color)
            if obs.obs_type == ObsType.UNKNOWN:
                item.setForeground(2, QColor("#ff9800"))
            else:
                item.setForeground(2, QColor("white"))
