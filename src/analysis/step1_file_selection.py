"""Step 1: 데이터 로딩 — 폴더 스캔 + FITS 파싱"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QSplitter,
)
from PySide6.QtCore import Qt

from src.analysis.step_base import StepBase
from src.core.fits_io import scan_folder
from src.core.metadata import load_meta_json
from src.core.cache import load_cache
from src.widgets.obs_list import ObsListWidget
from src.widgets.spectrum_plot import SpectrumPlotWidget
from src.models.project_state import ProjectState


class Step1FileSelection(StepBase):
    """폴더를 스캔하여 관측 세트를 로드한다."""

    data_loaded = Signal(list)  # observations 리스트

    def __init__(self, project_state: ProjectState, parent=None):
        super().__init__(
            step_index=0,
            step_name="데이터 로딩",
            step_description=(
                "관측 데이터 폴더를 선택하면 하위 폴더의 FITS 파일을 자동으로 "
                "스캔하여 관측 리스트를 생성합니다. "
                "raw_observation.fits 에서 freq_MHz, psd_dB를 읽어옵니다."
            ),
            project_state=project_state,
            parent=parent,
        )

    def setup_ui(self):
        # 폴더 선택
        folder_row = QHBoxLayout()
        self.btn_open = QPushButton("관측 폴더 열기")
        self.btn_open.setStyleSheet(
            "QPushButton { background: #3a7bd5; color: white; "
            "font-weight: bold; padding: 10px 20px; border-radius: 6px; }"
        )
        self.btn_open.clicked.connect(self._on_open)
        folder_row.addWidget(self.btn_open)

        self.lbl_folder = QLabel("폴더를 선택하세요")
        self.lbl_folder.setStyleSheet("color: #888;")
        folder_row.addWidget(self.lbl_folder, stretch=1)
        self.content_layout.addLayout(folder_row)

        # 메인: 리스트 + 프리뷰
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.obs_list = ObsListWidget()
        self.obs_list.btn_open.hide()  # 상위 버튼 사용
        self.obs_list.observation_selected.connect(self._on_select)
        splitter.addWidget(self.obs_list)

        self.plot = SpectrumPlotWidget(display_mode="raw")
        splitter.addWidget(self.plot)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        self.content_layout.addWidget(splitter, stretch=1)

        # 요약
        self.lbl_summary = QLabel("")
        self.lbl_summary.setStyleSheet("color: #aaa; font-size: 11px; padding: 4px;")
        self.content_layout.addWidget(self.lbl_summary)

    def _apply_observations(self, observations: list, folder: Path):
        self._observations = observations
        self.obs_list.set_observations(observations)
        self.lbl_folder.setText(str(folder))
        self.lbl_summary.setText(f"{len(observations)}개 관측 로드됨")

        if observations:
            if not (0 <= self._current_idx < len(observations)):
                self._current_idx = 0
            self.plot.plot_observation(observations[self._current_idx])

    def _load_folder(
        self,
        path: Path,
        *,
        save_state: bool = True,
        emit_signal: bool = True,
        show_empty_message: bool = True,
    ) -> bool:
        observations = scan_folder(path)
        if not observations:
            if show_empty_message:
                QMessageBox.information(self, "알림", "FITS 파일을 찾을 수 없습니다.")
            return False

        for obs in observations:
            obs.metadata = load_meta_json(obs)
            load_cache(obs)

        self._apply_observations(observations, path)

        if emit_signal:
            self.data_loaded.emit(observations)

        if save_state:
            self.project_state.store_step_data("step1", {
                "folder": str(path),
                "count": len(observations),
            })
        return True

    def on_enter(self):
        super().on_enter()
        if self._observations:
            folder_text = self.lbl_folder.text()
            if folder_text == "폴더를 선택하세요":
                data = self.project_state.get_step_data("step1")
                if data.get("folder"):
                    self.lbl_folder.setText(data["folder"])
            self.obs_list.set_observations(self._observations)
            self.lbl_summary.setText(f"{len(self._observations)}개 관측 로드됨")
            if 0 <= self._current_idx < len(self._observations):
                self.plot.plot_observation(self._observations[self._current_idx])
            elif self._observations:
                self._current_idx = 0
                self.plot.plot_observation(self._observations[0])
            return

        data = self.project_state.get_step_data("step1")
        folder = data.get("folder")
        if folder:
            self._load_folder(
                Path(folder),
                save_state=False,
                emit_signal=True,
                show_empty_message=False,
            )

    def _on_open(self):
        folder = QFileDialog.getExistingDirectory(self, "관측 데이터 폴더 선택")
        if not folder:
            return

        self._load_folder(Path(folder))

    def _on_select(self, idx: int):
        self._current_idx = idx
        if 0 <= idx < len(self._observations):
            self.plot.plot_observation(self._observations[idx])

    def validate_step(self) -> bool:
        if not self._observations:
            QMessageBox.warning(self, "검증 실패", "먼저 데이터를 로드하세요.")
            return False
        return True

    def save_state(self):
        self.project_state.store_step_data("step1", {
            "folder": self.lbl_folder.text(),
            "count": len(self._observations),
        })

    def restore_state(self):
        data = self.project_state.get_step_data("step1")
        if data.get("folder"):
            self.lbl_folder.setText(data["folder"])
