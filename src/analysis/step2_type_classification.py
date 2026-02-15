"""Step 2: 관측 타입 분류 — SOU/AMB/SKY 자동 분류 + 수동 수정"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QTreeWidget, QTreeWidgetItem, QHeaderView,
    QPushButton, QMessageBox,
)
from PySide6.QtGui import QColor

from src.analysis.step_base import StepBase
from src.core.cache import save_cache
from src.models.observation import Observation, ObsType
from src.models.project_state import ProjectState


class Step2TypeClassification(StepBase):
    """파일명에서 관측 타입을 자동 분류하고, 수동 수정을 허용한다."""

    def __init__(self, project_state: ProjectState, parent=None):
        super().__init__(
            step_index=1,
            step_name="관측 타입 분류",
            step_description=(
                "파일/폴더명에서 SOU(Source), AMB(Ambient), SKY(Sky)를 자동 분류합니다. "
                "누락된 항목은 드롭다운으로 직접 지정하세요."
            ),
            project_state=project_state,
            parent=parent,
        )

    def setup_ui(self):
        # 경고
        self.lbl_warning = QLabel("")
        self.lbl_warning.setStyleSheet(
            "color: #ff9800; font-size: 12px; font-weight: bold; padding: 4px;"
        )
        self.content_layout.addWidget(self.lbl_warning)

        # 일괄 지정
        batch_row = QHBoxLayout()
        batch_row.addWidget(QLabel("선택 항목 일괄 지정:"))
        self.combo_batch = QComboBox()
        self.combo_batch.addItems(["SOU", "AMB", "SKY"])
        batch_row.addWidget(self.combo_batch)
        btn_apply = QPushButton("적용")
        btn_apply.clicked.connect(self._on_batch_apply)
        batch_row.addWidget(btn_apply)
        batch_row.addStretch()
        self.content_layout.addLayout(batch_row)

        # 테이블
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["관측 ID", "날짜", "현재 타입", "타입 지정"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree.setStyleSheet("""
            QTreeWidget { background: #1e1e2e; color: white; border: 1px solid #444;
                          alternate-background-color: #252540; }
            QTreeWidget::item:selected { background: #3a7bd5; }
            QHeaderView::section { background: #2a2a3e; color: white;
                                   border: 1px solid #444; padding: 4px; }
        """)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.content_layout.addWidget(self.tree, stretch=1)

    def on_enter(self):
        super().on_enter()
        self._refresh_table()

    def _refresh_table(self):
        self.tree.clear()
        unknown_count = 0

        for i, obs in enumerate(self._observations):
            item = QTreeWidgetItem([
                obs.display_name,
                obs.date_obs,
                obs.obs_type.value,
                "",
            ])

            # 타입 드롭다운
            combo = QComboBox()
            combo.addItems(["SOU", "AMB", "SKY", "UNKNOWN"])
            combo.setCurrentText(obs.obs_type.value)
            combo.setProperty("obs_index", i)
            combo.currentTextChanged.connect(self._on_type_changed)

            if obs.obs_type == ObsType.UNKNOWN:
                item.setForeground(2, QColor("#ff9800"))
                unknown_count += 1
            else:
                item.setForeground(2, QColor("#4caf50"))

            self.tree.addTopLevelItem(item)
            self.tree.setItemWidget(item, 3, combo)

        if unknown_count > 0:
            self.lbl_warning.setText(f"타입 미지정 {unknown_count}개 — 지정 후 완료하세요")
        else:
            self.lbl_warning.setText("모든 관측 타입이 지정되었습니다")
            self.lbl_warning.setStyleSheet(
                "color: #4caf50; font-size: 12px; font-weight: bold; padding: 4px;"
            )

    def _on_type_changed(self, type_str: str):
        combo = self.sender()
        idx = combo.property("obs_index")
        if 0 <= idx < len(self._observations):
            try:
                self._observations[idx].obs_type = ObsType(type_str)
            except ValueError:
                self._observations[idx].obs_type = ObsType.UNKNOWN

            # 테이블 갱신
            item = self.tree.topLevelItem(idx)
            if item:
                item.setText(2, type_str)
                color = QColor("#4caf50") if type_str != "UNKNOWN" else QColor("#ff9800")
                item.setForeground(2, color)

        # 경고 갱신
        unknown = sum(1 for o in self._observations if o.obs_type == ObsType.UNKNOWN)
        if unknown > 0:
            self.lbl_warning.setText(f"타입 미지정 {unknown}개")
            self.lbl_warning.setStyleSheet(
                "color: #ff9800; font-size: 12px; font-weight: bold; padding: 4px;"
            )
        else:
            self.lbl_warning.setText("모든 관측 타입이 지정되었습니다")
            self.lbl_warning.setStyleSheet(
                "color: #4caf50; font-size: 12px; font-weight: bold; padding: 4px;"
            )

    def _on_batch_apply(self):
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.information(self, "알림", "항목을 선택하세요.")
            return

        type_str = self.combo_batch.currentText()
        for item in selected:
            idx = self.tree.indexOfTopLevelItem(item)
            if 0 <= idx < len(self._observations):
                self._observations[idx].obs_type = ObsType(type_str)
                # 드롭다운 갱신
                combo = self.tree.itemWidget(item, 3)
                if combo:
                    combo.setCurrentText(type_str)

    def validate_step(self) -> bool:
        unknown = sum(1 for o in self._observations if o.obs_type == ObsType.UNKNOWN)
        if unknown > 0:
            QMessageBox.warning(
                self, "검증 실패",
                f"타입 미지정 관측이 {unknown}개 있습니다.\n모두 지정한 후 완료하세요."
            )
            return False
        return True

    def save_state(self):
        # 타입 분류 결과를 캐시에 저장
        for obs in self._observations:
            save_cache(obs)
        self.project_state.store_step_data("step2", {
            "types": {obs.obs_id: obs.obs_type.value for obs in self._observations},
        })
