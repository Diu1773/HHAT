"""Step 9: HI 선 검출 (피크 후보 찾기)"""

from __future__ import annotations

import numpy as np

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGroupBox, QFormLayout, QLabel,
    QPushButton, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QMessageBox,
    QTreeWidget, QTreeWidgetItem,
)

from src.analysis.step_base import StepBase
from src.core.detection import detect_peaks, PeakCandidate
from src.core.cache import save_cache
from src.widgets.spectrum_plot import SpectrumPlotWidget
from src.widgets.obs_list import ObsListWidget
from src.models.observation import ObsType
from src.models.project_state import ProjectState


class Step9PeakDetection(StepBase):
    """자동 피크 탐지 + 수동 확인"""

    def __init__(self, project_state: ProjectState, parent=None):
        super().__init__(
            step_index=8,
            step_name="피크 검출",
            step_description=(
                "scipy.signal.find_peaks를 사용하여 HI 선 후보를 자동 탐지합니다. "
                "SNR, 최소 폭 기준을 조정할 수 있습니다."
            ),
            project_state=project_state,
            parent=parent,
        )
        self._peaks = []

    def setup_ui(self):
        splitter = QSplitter(Qt.Orientation.Vertical)

        self.plot = SpectrumPlotWidget(display_mode="auto")
        splitter.addWidget(self.plot)

        bottom = QWidget()
        bl = QHBoxLayout(bottom)

        # 관측 리스트
        self.obs_list = ObsListWidget()
        self.obs_list.btn_open.hide()
        self.obs_list.setMaximumWidth(250)
        self.obs_list.observation_selected.connect(self._on_select)
        bl.addWidget(self.obs_list)

        # 파라미터
        ctrl = QGroupBox("피크 검출 파라미터")
        cl = QFormLayout(ctrl)

        self.spin_snr = QDoubleSpinBox()
        self.spin_snr.setRange(0.1, 20.0)
        self.spin_snr.setSingleStep(0.1)
        self.spin_snr.setDecimals(1)
        self.spin_snr.setValue(3.0)
        cl.addRow("최소 SNR:", self.spin_snr)

        self.spin_width = QSpinBox()
        self.spin_width.setRange(1, 50)
        self.spin_width.setValue(8)
        cl.addRow("최소 폭 (ch):", self.spin_width)

        self.combo_polarity = QComboBox()
        self.combo_polarity.addItems(["양의 피크", "음의 피크(흡수)", "둘 다"])
        cl.addRow("검출 타입:", self.combo_polarity)

        self.chk_exclude_dc = QCheckBox("DC spike 제외 (중심 주파수)")
        self.chk_exclude_dc.setChecked(True)
        self.chk_exclude_dc.setToolTip("RTL-SDR 중심 주파수의 DC spike를 검출에서 제외합니다")
        cl.addRow(self.chk_exclude_dc)

        self.btn_detect = QPushButton("피크 검출")
        self.btn_detect.setStyleSheet(
            "QPushButton { background: #f57c00; color: white; font-weight: bold; padding: 8px; }"
        )
        self.btn_detect.clicked.connect(self._on_detect)
        cl.addRow(self.btn_detect)

        reset_row = QHBoxLayout()
        self.btn_reset_current = QPushButton("현재 피크 초기화")
        self.btn_reset_current.clicked.connect(self._on_reset_current)
        reset_row.addWidget(self.btn_reset_current)
        self.btn_reset_all = QPushButton("전체 피크 초기화")
        self.btn_reset_all.clicked.connect(self._on_reset_all)
        reset_row.addWidget(self.btn_reset_all)
        cl.addRow(reset_row)

        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet("color: #ffeb3b; font-weight: bold;")
        cl.addRow("검출:", self.lbl_count)

        self.lbl_axis = QLabel("")
        self.lbl_axis.setStyleSheet("color: #aaa; font-size: 10px;")
        cl.addRow("축 단위:", self.lbl_axis)

        bl.addWidget(ctrl)

        # 피크 테이블
        self.peak_tree = QTreeWidget()
        self.peak_tree.setHeaderLabels(["#", "타입", "위치", "진폭", "폭", "SNR"])
        self.peak_tree.setRootIsDecorated(False)
        self.peak_tree.setStyleSheet("""
            QTreeWidget { background: #1e1e2e; color: white; border: 1px solid #444; }
            QHeaderView::section { background: #2a2a3e; color: white;
                                   border: 1px solid #444; padding: 3px; }
        """)
        bl.addWidget(self.peak_tree)

        splitter.addWidget(bottom)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        self.content_layout.addWidget(splitter, stretch=1)

    def on_enter(self):
        super().on_enter()
        self.obs_list.set_observations(self._observations)
        if self._observations:
            self._on_select(self._default_obs_index())

    def _default_obs_index(self) -> int:
        for i, obs in enumerate(self._observations):
            if obs.obs_type == ObsType.SOU:
                return i
        for i, obs in enumerate(self._observations):
            if obs.obs_type != ObsType.AMB:
                return i
        return 0

    def _axis_is_velocity(self, obs) -> bool:
        return bool(obs.is_velocity_converted and obs.vel_kms is not None)

    def _sync_axis_ui(self, obs):
        use_velocity = self._axis_is_velocity(obs)
        self.plot.set_velocity_mode(use_velocity)
        pos_unit = "km/s" if use_velocity else "MHz"
        self.peak_tree.setHeaderLabels(["#", "타입", f"위치 ({pos_unit})", "진폭", f"폭 ({pos_unit})", "SNR"])
        self.lbl_axis.setText(f"{'속도축' if use_velocity else '주파수축'} 기준 검출")

    def _on_select(self, idx: int):
        self._current_idx = idx
        obs = self.current_obs
        if obs:
            self._sync_axis_ui(obs)
            self._peaks = self._load_peaks_from_obs(obs)
            self._render_peaks(obs)

    def _get_xy(self, obs):
        if obs.is_calibrated and obs.antenna_temp_k is not None:
            y = obs.antenna_temp_k
        elif obs.is_baseline_removed and obs.psd_db_baseline_removed is not None:
            y = obs.psd_db_baseline_removed
        elif obs.is_preprocessed and obs.psd_db_clean is not None:
            y = obs.psd_db_clean
        else:
            y = obs.psd_db
        x = obs.vel_kms if obs.is_velocity_converted and obs.vel_kms is not None else obs.freq_mhz
        return x, y

    def _on_detect(self):
        obs = self.current_obs
        if obs is None:
            self.lbl_count.setText("대상 없음")
            return

        self._sync_axis_ui(obs)
        x, y = self._get_xy(obs)
        if x is None or y is None:
            self.lbl_count.setText("데이터 없음")
            return

        try:
            snr = float(self.spin_snr.value())
            min_width = self.spin_width.value()
            mode = self.combo_polarity.currentText()
            exclude_dc = 0.02 if self.chk_exclude_dc.isChecked() else 0.0
            peaks: list[PeakCandidate] = []

            if mode in ("양의 피크", "둘 다"):
                peaks.extend(detect_peaks(
                    x, y, snr_threshold=snr, min_width=min_width,
                    exclude_center_frac=exclude_dc,
                ))

            if mode in ("음의 피크(흡수)", "둘 다"):
                neg = detect_peaks(
                    x, -y, snr_threshold=snr, min_width=min_width,
                    exclude_center_frac=exclude_dc,
                )
                peaks.extend([
                    PeakCandidate(
                        index=p.index,
                        position=p.position,
                        amplitude=-abs(p.amplitude),
                        width=p.width,
                        snr=p.snr,
                    )
                    for p in neg
                ])

            peaks.sort(key=lambda p: abs(p.snr), reverse=True)
            self._peaks = peaks
        except Exception as e:
            self._peaks = []
            self.lbl_count.setText("오류")
            QMessageBox.warning(self, "검출 실패", f"피크 검출 중 오류가 발생했습니다.\n{e}")
            return

        # obs에 저장
        obs.metadata["peaks"] = [
            {
                "pos": p.position,
                "amp": p.amplitude,
                "width": p.width,
                "snr": p.snr,
                "type": "absorption" if p.amplitude < 0 else "emission",
                "unit": "km/s" if self._axis_is_velocity(obs) else "MHz",
            }
            for p in self._peaks
        ]
        save_cache(obs)
        self._render_peaks(obs)

    def _to_axis_value(self, obs, value: float, from_unit: str, to_unit: str) -> float | None:
        """저장된 피크 위치를 현재 축 단위로 변환한다."""
        if not np.isfinite(value):
            return None
        from_unit = str(from_unit).strip().lower()
        to_unit = str(to_unit).strip().lower()
        if from_unit == to_unit:
            return float(value)

        if obs.freq_mhz is None or obs.vel_kms is None:
            return None
        freq = np.asarray(obs.freq_mhz, dtype=float)
        vel = np.asarray(obs.vel_kms, dtype=float)
        valid = np.isfinite(freq) & np.isfinite(vel)
        if np.count_nonzero(valid) < 2:
            return None
        freq = freq[valid]
        vel = vel[valid]

        if from_unit == "mhz" and to_unit == "km/s":
            order = np.argsort(freq)
            return float(np.interp(value, freq[order], vel[order]))
        if from_unit == "km/s" and to_unit == "mhz":
            order = np.argsort(vel)
            return float(np.interp(value, vel[order], freq[order]))
        return None

    def _to_axis_width(
        self,
        obs,
        width: float,
        pos: float,
        from_unit: str,
        to_unit: str,
    ) -> float:
        """저장된 피크 폭을 현재 축 단위로 변환한다."""
        try:
            w = abs(float(width))
        except (TypeError, ValueError):
            return 0.0
        if not np.isfinite(w) or w <= 0:
            return 0.0
        from_unit = str(from_unit).strip().lower()
        to_unit = str(to_unit).strip().lower()
        if from_unit == to_unit:
            return w

        left = self._to_axis_value(obs, pos - 0.5 * w, from_unit, to_unit)
        right = self._to_axis_value(obs, pos + 0.5 * w, from_unit, to_unit)
        if left is None or right is None:
            return 0.0
        return float(abs(right - left))

    def _load_peaks_from_obs(self, obs) -> list[PeakCandidate]:
        """metadata의 저장 피크를 현재 축 기준 PeakCandidate로 복원한다."""
        x, y = self._get_xy(obs)
        if x is None or y is None:
            return []

        axis_unit = "km/s" if self._axis_is_velocity(obs) else "mhz"
        loaded: list[PeakCandidate] = []
        for p in obs.metadata.get("peaks", []):
            try:
                pos_saved = float(p.get("pos"))
                unit_saved = str(p.get("unit", axis_unit))
                pos = self._to_axis_value(obs, pos_saved, unit_saved, axis_unit)
                if pos is None:
                    continue
                width = self._to_axis_width(
                    obs,
                    p.get("width", 0.0),
                    pos_saved,
                    unit_saved,
                    axis_unit,
                )
                idx = int(np.argmin(np.abs(x - pos)))
                loaded.append(PeakCandidate(
                    index=idx,
                    position=pos,
                    amplitude=float(p.get("amp", 0.0)),
                    width=width,
                    snr=float(p.get("snr", 0.0)),
                ))
            except (TypeError, ValueError):
                continue

        loaded.sort(key=lambda pk: abs(pk.snr), reverse=True)
        return loaded

    def _render_peaks(self, obs):
        """현재 선택 관측의 피크 테이블/플롯 오버레이를 동기화한다."""
        x, y = self._get_xy(obs)
        self.peak_tree.clear()
        if x is None or y is None:
            self.lbl_count.setText("데이터 없음")
            self.plot.plot_observation(obs)
            return

        for i, p in enumerate(self._peaks):
            peak_type = "흡수" if p.amplitude < 0 else "방출"
            QTreeWidgetItem(self.peak_tree, [
                str(i + 1),
                peak_type,
                f"{p.position:.2f}",
                f"{p.amplitude:.2f}",
                f"{p.width:.2f}",
                f"{p.snr:.1f}",
            ])

        self.lbl_count.setText(f"{len(self._peaks)}개" if self._peaks else "없음")

        self.plot.plot_observation(obs)
        ax = self.plot.ax
        for p in self._peaks:
            is_absorption = p.amplitude < 0
            color = "#ff9800" if is_absorption else "#ffeb3b"
            marker = "v" if is_absorption else "^"
            ax.axvline(p.position, color=color, ls=":", alpha=0.7, lw=0.8)
            if 0 <= p.index < len(y):
                ax.plot(p.position, y[p.index], marker, color=color, ms=8)
        self.plot.canvas.draw()

    def _on_reset_current(self):
        obs = self.current_obs
        if obs is None:
            return
        obs.metadata.pop("peaks", None)
        self._peaks = []
        save_cache(obs)
        self._render_peaks(obs)

    def _on_reset_all(self):
        for obs in self._observations:
            obs.metadata.pop("peaks", None)
            save_cache(obs)
        self._peaks = []
        if self.current_obs:
            self._render_peaks(self.current_obs)

    @property
    def peaks(self):
        return self._peaks

    def save_state(self):
        self.project_state.store_step_data("step9", {
            "snr": self.spin_snr.value(),
            "min_width": self.spin_width.value(),
            "polarity": self.combo_polarity.currentText(),
            "exclude_dc": self.chk_exclude_dc.isChecked(),
        })

    def restore_state(self):
        data = self.project_state.get_step_data("step9")
        if not data:
            return
        if "snr" in data:
            self.spin_snr.setValue(float(data["snr"]))
        if "min_width" in data:
            self.spin_width.setValue(int(data["min_width"]))
        if "polarity" in data:
            idx = self.combo_polarity.findText(data["polarity"])
            if idx >= 0:
                self.combo_polarity.setCurrentIndex(idx)
        if "exclude_dc" in data:
            self.chk_exclude_dc.setChecked(bool(data["exclude_dc"]))

    def validate_step(self) -> bool:
        if len(self._peaks) == 0:
            QMessageBox.information(
                self,
                "검출 없음",
                "검출된 피크가 없습니다.\n"
                "SNR/최소 폭을 낮추고, 필요하면 '음의 피크(흡수)'로 바꿔 다시 시도하세요.",
            )
            return False
        return True
