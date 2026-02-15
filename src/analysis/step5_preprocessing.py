"""Step 5: RFI/스파이크 마스킹 + 스무딩"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGroupBox, QFormLayout, QLabel,
    QPushButton, QComboBox, QSlider, QSpinBox, QCheckBox,
)

from src.analysis.step_base import StepBase
from src.core.preprocessing import preprocess
from src.core.cache import save_cache, clear_cache
from src.widgets.spectrum_plot import SpectrumPlotWidget
from src.widgets.obs_list import ObsListWidget
from src.models.project_state import ProjectState


class Step5Preprocessing(StepBase):
    """RFI 마스킹 + 스무딩 전처리"""

    def __init__(self, project_state: ProjectState, parent=None):
        super().__init__(
            step_index=4,
            step_name="전처리 (RFI/스무딩)",
            step_description=(
                "스파이크 제거(z-score 기반)와 스무딩(Savitzky-Golay/Gaussian)을 적용합니다. "
                "파라미터를 조정하고 적용 버튼을 누르세요."
            ),
            project_state=project_state,
            parent=parent,
        )

    def setup_ui(self):
        splitter = QSplitter(Qt.Orientation.Vertical)

        # 상: 플롯
        self.plot = SpectrumPlotWidget(display_mode="clean")
        splitter.addWidget(self.plot)

        # 하: 컨트롤
        bottom = QWidget()
        bottom_layout = QHBoxLayout(bottom)

        # 관측 리스트
        self.obs_list = ObsListWidget()
        self.obs_list.btn_open.hide()
        self.obs_list.setMaximumWidth(300)
        self.obs_list.observation_selected.connect(self._on_select)
        bottom_layout.addWidget(self.obs_list)

        # 파라미터
        ctrl = QGroupBox("전처리 파라미터")
        cl = QFormLayout(ctrl)

        self.slider_rfi_z = QSlider(Qt.Orientation.Horizontal)
        self.slider_rfi_z.setRange(20, 100)
        self.slider_rfi_z.setValue(50)
        self.lbl_rfi_z = QLabel("5.0")
        self.slider_rfi_z.valueChanged.connect(lambda v: self.lbl_rfi_z.setText(f"{v/10:.1f}"))
        row = QHBoxLayout()
        row.addWidget(self.slider_rfi_z)
        row.addWidget(self.lbl_rfi_z)
        cl.addRow("RFI Z-score:", row)

        self.combo_smooth = QComboBox()
        self.combo_smooth.addItems(["savgol", "gaussian", "none"])
        cl.addRow("스무딩:", self.combo_smooth)

        self.spin_smooth = QSpinBox()
        self.spin_smooth.setRange(3, 101)
        self.spin_smooth.setValue(11)
        self.spin_smooth.setSingleStep(2)
        cl.addRow("윈도우:", self.spin_smooth)

        self.chk_rfi_mask = QCheckBox("RFI 마스크 표시")
        self.chk_rfi_mask.setChecked(True)
        cl.addRow(self.chk_rfi_mask)

        btn_row = QHBoxLayout()
        self.btn_apply = QPushButton("현재 관측 적용")
        self.btn_apply.setStyleSheet(
            "QPushButton { background: #e65100; color: white; font-weight: bold; padding: 8px; }"
        )
        self.btn_apply.clicked.connect(self._on_apply)
        btn_row.addWidget(self.btn_apply)

        self.btn_apply_all = QPushButton("전체 적용")
        self.btn_apply_all.clicked.connect(self._on_apply_all)
        btn_row.addWidget(self.btn_apply_all)
        cl.addRow(btn_row)

        reset_row = QHBoxLayout()
        self.btn_reset_current = QPushButton("현재 초기화")
        self.btn_reset_current.clicked.connect(self._on_reset_current)
        reset_row.addWidget(self.btn_reset_current)

        self.btn_reset_all = QPushButton("전체 초기화")
        self.btn_reset_all.clicked.connect(self._on_reset_all)
        reset_row.addWidget(self.btn_reset_all)
        cl.addRow(reset_row)

        bottom_layout.addWidget(ctrl)
        splitter.addWidget(bottom)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        self.content_layout.addWidget(splitter, stretch=1)

    def on_enter(self):
        super().on_enter()
        self.obs_list.set_observations(self._observations)
        if self._observations:
            self._on_select(0)

    def _on_select(self, idx: int):
        self._current_idx = idx
        obs = self.current_obs
        if obs:
            self.plot.set_show_rfi_mask(self.chk_rfi_mask.isChecked())
            self.plot.plot_observation(obs)

    def _apply_to(self, obs):
        if obs is None or obs.psd_db is None:
            return
        obs.psd_db_clean, obs.mask_rfi = preprocess(
            obs.psd_db,
            rfi_zscore=self.slider_rfi_z.value() / 10.0,
            smooth_method=self.combo_smooth.currentText(),
            smooth_param=self.spin_smooth.value(),
        )
        obs.is_preprocessed = True

    def _on_apply(self):
        obs = self.current_obs
        self._apply_to(obs)
        if obs:
            save_cache(obs)
            self.plot.set_show_rfi_mask(self.chk_rfi_mask.isChecked())
            self.plot.plot_observation(obs)

    def _on_apply_all(self):
        for obs in self._observations:
            self._apply_to(obs)
            save_cache(obs)
        self.step_status_changed.emit(self.step_index, f"전체 {len(self._observations)}개 전처리 완료")
        if self.current_obs:
            self.plot.plot_observation(self.current_obs)

    def _reset_preprocessing(self, obs):
        if obs is None:
            return
        obs.psd_db_clean = None
        obs.mask_rfi = None
        obs.is_preprocessed = False

    def _on_reset_current(self):
        obs = self.current_obs
        self._reset_preprocessing(obs)
        if obs:
            save_cache(obs)
            self.plot.set_show_rfi_mask(self.chk_rfi_mask.isChecked())
            self.plot.plot_observation(obs)
            self.step_status_changed.emit(self.step_index, f"{obs.display_name} 전처리 초기화")

    def _on_reset_all(self):
        for obs in self._observations:
            self._reset_preprocessing(obs)
            save_cache(obs)
        self.step_status_changed.emit(self.step_index, f"전체 {len(self._observations)}개 전처리 초기화")
        if self.current_obs:
            self.plot.set_show_rfi_mask(self.chk_rfi_mask.isChecked())
            self.plot.plot_observation(self.current_obs)

    def validate_step(self) -> bool:
        return any(o.is_preprocessed for o in self._observations)

    def save_state(self):
        self.project_state.store_step_data("step5", {
            "rfi_zscore": self.slider_rfi_z.value() / 10.0,
            "smooth_method": self.combo_smooth.currentText(),
            "smooth_param": self.spin_smooth.value(),
        })

    def restore_state(self):
        data = self.project_state.get_step_data("step5")
        if not data:
            return
        if "rfi_zscore" in data:
            self.slider_rfi_z.setValue(int(data["rfi_zscore"] * 10))
        if "smooth_method" in data:
            idx = self.combo_smooth.findText(data["smooth_method"])
            if idx >= 0:
                self.combo_smooth.setCurrentIndex(idx)
        if "smooth_param" in data:
            self.spin_smooth.setValue(int(data["smooth_param"]))
