"""Step 4: QC(품질 점검) 지표 계산"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QSplitter, QPushButton, QLabel,
    QTreeWidget, QTreeWidgetItem, QHeaderView,
    QVBoxLayout,
)
from PySide6.QtGui import QColor

from src.analysis.step_base import StepBase
from src.core.qc import run_qc
from src.core.cache import save_cache
from src.models.observation import QCStatus
from src.widgets.spectrum_plot import SpectrumPlotWidget
from src.models.project_state import ProjectState


class Step4QC(StepBase):
    """스펙트럼 품질 점검을 수행한다."""

    def __init__(self, project_state: ProjectState, parent=None):
        super().__init__(
            step_index=3,
            step_name="QC 품질 점검",
            step_description=(
                "스펙트럼의 RMS, 스파이크 개수, NaN/Inf 여부 등을 점검하여 "
                "OK/WARN/BAD 상태를 판정합니다."
            ),
            project_state=project_state,
            parent=parent,
        )

    def setup_ui(self):
        # 일괄 QC 버튼
        self.btn_run_all = QPushButton("전체 QC 실행")
        self.btn_run_all.setStyleSheet(
            "QPushButton { background: #e65100; color: white; "
            "font-weight: bold; padding: 8px; }"
        )
        self.btn_run_all.clicked.connect(self._run_all_qc)
        self.content_layout.addWidget(self.btn_run_all)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 좌: QC 결과 테이블
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["관측 ID", "타입", "QC", "RMS", "스파이크", "메시지"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setStyleSheet("""
            QTreeWidget { background: #1e1e2e; color: white; border: 1px solid #444;
                          alternate-background-color: #252540; }
            QHeaderView::section { background: #2a2a3e; color: white;
                                   border: 1px solid #444; padding: 4px; }
        """)
        self.tree.currentItemChanged.connect(self._on_select)
        splitter.addWidget(self.tree)

        # 우: 스펙트럼
        self.plot = SpectrumPlotWidget(display_mode="raw")
        splitter.addWidget(self.plot)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        self.content_layout.addWidget(splitter, stretch=1)

    def on_enter(self):
        super().on_enter()
        self._refresh_table()

    def _run_all_qc(self):
        for obs in self._observations:
            obs.qc = run_qc(obs)
            save_cache(obs)
        self._refresh_table()

    def _refresh_table(self):
        self.tree.clear()
        qc_colors = {
            QCStatus.OK: QColor("#4caf50"),
            QCStatus.WARN: QColor("#ff9800"),
            QCStatus.BAD: QColor("#f44336"),
            QCStatus.UNCHECKED: QColor("#888"),
        }
        for obs in self._observations:
            item = QTreeWidgetItem([
                obs.display_name,
                obs.obs_type.value,
                obs.qc.status.value,
                f"{obs.qc.rms_total:.2f}",
                str(obs.qc.spike_count),
                "; ".join(obs.qc.messages),
            ])
            item.setForeground(2, qc_colors.get(obs.qc.status, QColor("#888")))
            self.tree.addTopLevelItem(item)

    def _on_select(self, current: QTreeWidgetItem, _prev):
        if current is None:
            return
        idx = self.tree.indexOfTopLevelItem(current)
        if 0 <= idx < len(self._observations):
            self._current_idx = idx
            self.plot.plot_observation(self._observations[idx])

    def validate_step(self) -> bool:
        # QC가 한 번이라도 실행되었는지
        return any(o.qc.status != QCStatus.UNCHECKED for o in self._observations)
