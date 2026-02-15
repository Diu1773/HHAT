"""Step 7: 주파수축 → 속도축 변환"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGroupBox, QFormLayout, QLabel,
    QPushButton, QComboBox, QCheckBox, QDoubleSpinBox,
)

from src.analysis.step_base import StepBase
from src.core.velocity import convert_velocity
from src.core.cache import save_cache
from src.utils.constants import HI_REST_FREQ_MHZ
from src.widgets.spectrum_plot import SpectrumPlotWidget
from src.widgets.obs_list import ObsListWidget
from src.models.project_state import ProjectState


class Step7Velocity(StepBase):
    """주파수축 → 속도축 변환 (21cm HI 기준)"""

    def __init__(self, project_state: ProjectState, parent=None):
        super().__init__(
            step_index=6,
            step_name="속도축 변환",
            step_description=(
                f"HI 정지 주파수 {HI_REST_FREQ_MHZ} MHz 기준으로 "
                "주파수를 속도(km/s)로 변환합니다. "
                "Radio/Optical/Relativistic 관례를 선택할 수 있습니다."
            ),
            project_state=project_state,
            parent=parent,
        )

    def setup_ui(self):
        splitter = QSplitter(Qt.Orientation.Vertical)

        self.plot = SpectrumPlotWidget(display_mode="auto")
        splitter.addWidget(self.plot)

        bottom = QWidget()
        bl = QHBoxLayout(bottom)

        self.obs_list = ObsListWidget()
        self.obs_list.btn_open.hide()
        self.obs_list.setMaximumWidth(300)
        self.obs_list.observation_selected.connect(self._on_select)
        bl.addWidget(self.obs_list)

        ctrl = QGroupBox("속도 변환 설정")
        cl = QFormLayout(ctrl)

        self.combo_conv = QComboBox()
        self.combo_conv.addItems(["radio", "optical", "relativistic"])
        cl.addRow("관례:", self.combo_conv)

        self.spin_rest_freq = QDoubleSpinBox()
        self.spin_rest_freq.setRange(0.001, 2000)
        self.spin_rest_freq.setDecimals(5)
        self.spin_rest_freq.setValue(HI_REST_FREQ_MHZ)
        self.spin_rest_freq.setSuffix(" MHz")
        cl.addRow("정지 주파수:", self.spin_rest_freq)

        self.chk_vel_axis = QCheckBox("속도축으로 표시")
        self.chk_vel_axis.setChecked(True)
        self.chk_vel_axis.toggled.connect(self._on_toggle_axis)
        cl.addRow(self.chk_vel_axis)

        btn_row = QHBoxLayout()
        self.btn_apply = QPushButton("변환 적용")
        self.btn_apply.setStyleSheet(
            "QPushButton { background: #00897b; color: white; font-weight: bold; padding: 8px; }"
        )
        self.btn_apply.clicked.connect(self._on_apply)
        btn_row.addWidget(self.btn_apply)

        self.btn_apply_all = QPushButton("전체 적용")
        self.btn_apply_all.clicked.connect(self._on_apply_all)
        btn_row.addWidget(self.btn_apply_all)
        cl.addRow(btn_row)

        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet("color: #aaa; font-size: 10px;")
        self.lbl_info.setWordWrap(True)
        cl.addRow(self.lbl_info)

        bl.addWidget(ctrl)
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
            self.plot.set_velocity_mode(self.chk_vel_axis.isChecked())
            self.plot.plot_observation(obs)

    def _apply_to(self, obs):
        if obs.freq_mhz is None:
            return
        obs.vel_kms = convert_velocity(
            obs.freq_mhz,
            convention=self.combo_conv.currentText(),
            rest_freq_mhz=self.spin_rest_freq.value(),
        )
        obs.is_velocity_converted = True
        save_cache(obs)

    def _on_apply(self):
        obs = self.current_obs
        if obs:
            self._apply_to(obs)
            self.plot.set_velocity_mode(self.chk_vel_axis.isChecked())
            self.plot.plot_observation(obs)
            if obs.vel_kms is not None:
                self.lbl_info.setText(
                    f"변환 완료: {obs.vel_kms.min():.1f} ~ {obs.vel_kms.max():.1f} km/s "
                    f"({self.combo_conv.currentText()} convention)"
                )

    def _on_apply_all(self):
        for obs in self._observations:
            self._apply_to(obs)
        if self.current_obs:
            self._on_apply()

    def _on_toggle_axis(self, checked: bool):
        self.plot.set_velocity_mode(checked)

    def validate_step(self) -> bool:
        return any(o.is_velocity_converted for o in self._observations)

    def save_state(self):
        self.project_state.store_step_data("step7", {
            "convention": self.combo_conv.currentText(),
            "rest_freq_mhz": self.spin_rest_freq.value(),
        })

    def restore_state(self):
        data = self.project_state.get_step_data("step7")
        if not data:
            return
        if "convention" in data:
            idx = self.combo_conv.findText(data["convention"])
            if idx >= 0:
                self.combo_conv.setCurrentIndex(idx)
        if "rest_freq_mhz" in data:
            self.spin_rest_freq.setValue(float(data["rest_freq_mhz"]))
