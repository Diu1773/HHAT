"""Step 3: 메타데이터 입력/보강"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QSplitter, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt

from src.analysis.step_base import StepBase
from src.widgets.metadata_panel import MetadataPanel
from src.widgets.obs_list import ObsListWidget
from src.core.metadata import save_meta_json, merge_header_and_meta
from src.models.project_state import ProjectState


class Step3Metadata(StepBase):
    """관측지, 시간대, alt/az 등 메타데이터를 입력/편집한다."""

    def __init__(self, project_state: ProjectState, parent=None):
        super().__init__(
            step_index=2,
            step_name="메타데이터 입력",
            step_description=(
                "LSR 보정/좌표 변환에 필요한 메타 필드를 확보합니다. "
                "관측지(lat/lon/height), 시간대, alt/az를 입력하고 meta.json으로 저장합니다."
            ),
            project_state=project_state,
            parent=parent,
        )

    def setup_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 좌: 관측 리스트
        self.obs_list = ObsListWidget()
        self.obs_list.btn_open.hide()
        self.obs_list.observation_selected.connect(self._on_select)
        splitter.addWidget(self.obs_list)

        # 우: 메타데이터 패널 + 일괄 적용
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.meta_panel = MetadataPanel()
        self.meta_panel.meta_saved.connect(self._on_save)
        right_layout.addWidget(self.meta_panel)

        self.btn_apply_all = QPushButton("현재 관측지 설정을 전체 관측에 일괄 적용")
        self.btn_apply_all.setStyleSheet(
            "QPushButton { background: #e65100; color: white; "
            "font-weight: bold; padding: 8px; border-radius: 4px; }"
        )
        self.btn_apply_all.clicked.connect(self._on_apply_all)
        right_layout.addWidget(self.btn_apply_all)

        splitter.addWidget(right)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        self.content_layout.addWidget(splitter, stretch=1)

    def on_enter(self):
        super().on_enter()
        self.obs_list.set_observations(self._observations)
        if self._observations:
            self._on_select(0)

    def _on_select(self, idx: int):
        self._current_idx = idx
        if 0 <= idx < len(self._observations):
            self.meta_panel.load_observation(self._observations[idx])

    def _on_save(self, meta: dict):
        obs = self.current_obs
        if obs is None:
            return
        obs.metadata.update(meta)
        meta_path = save_meta_json(obs, merge_header_and_meta(obs))
        QMessageBox.information(
            self,
            "저장 완료",
            f"meta.json 저장 완료\n{meta_path}",
        )

    def _on_apply_all(self):
        """현재 패널의 관측지/시간 설정을 전체 관측에 일괄 적용."""
        meta = self.meta_panel.collect_meta()
        # 관측지/시간 필드만 일괄 적용 (note 제외)
        site_keys = ["site_name", "lat", "lon", "height", "timezone"]
        count = 0
        for obs in self._observations:
            for key in site_keys:
                if key in meta:
                    obs.metadata[key] = meta[key]
            save_meta_json(obs, merge_header_and_meta(obs))
            count += 1
        QMessageBox.information(
            self, "일괄 적용",
            f"{count}개 관측에 관측지 설정을 적용하고 저장했습니다."
        )

    def validate_step(self) -> bool:
        return len(self._observations) > 0

    def save_state(self):
        if self._observations:
            # 마지막으로 사용한 관측지 설정 기억
            meta = self.meta_panel.collect_meta()
            self.project_state.store_step_data("step3", {
                "site_name": meta.get("site_name", ""),
                "lat": meta.get("lat", 0),
                "lon": meta.get("lon", 0),
                "height": meta.get("height", 0),
                "timezone": meta.get("timezone", "KST"),
            })
