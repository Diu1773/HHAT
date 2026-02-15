"""Step 11: 물리량 환산 (선택)"""

from __future__ import annotations

import numpy as np

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QFormLayout, QLabel,
    QPushButton, QDoubleSpinBox, QTextEdit, QComboBox,
)

from src.analysis.step_base import StepBase
from src.core.physics import (
    integrated_intensity, column_density_hi,
    component_integrated, psd_to_temperature, brightness_temperature,
)
from src.models.project_state import ProjectState
from src.widgets.obs_list import ObsListWidget


class Step11Physics(StepBase):
    """물리량 환산 — 적분 강도, N_HI 등"""

    def __init__(self, project_state: ProjectState, parent=None):
        super().__init__(
            step_index=10,
            step_name="물리량 환산",
            step_description=(
                "안테나 효율(η), 시스템 온도(Tsys) 등을 입력하면 "
                "적분 강도와 N_HI를 추정합니다. "
                "절대 교정 없이는 상대량 중심입니다."
            ),
            project_state=project_state,
            parent=parent,
        )

    def setup_ui(self):
        layout = QHBoxLayout()

        # 관측 리스트
        self.obs_list = ObsListWidget()
        self.obs_list.btn_open.hide()
        self.obs_list.setMaximumWidth(260)
        self.obs_list.observation_selected.connect(self._on_select)
        layout.addWidget(self.obs_list)

        # 파라미터
        param_group = QGroupBox("환산 파라미터")
        pl = QFormLayout(param_group)

        self.lbl_target = QLabel("-")
        self.lbl_target.setStyleSheet("color: #66ccff;")
        pl.addRow("대상:", self.lbl_target)

        self.spin_tsys = QDoubleSpinBox()
        self.spin_tsys.setRange(1, 10000)
        self.spin_tsys.setValue(150.0)
        self.spin_tsys.setSuffix(" K")
        pl.addRow("Tsys:", self.spin_tsys)

        self.spin_eta = QDoubleSpinBox()
        self.spin_eta.setRange(0.05, 1.0)
        self.spin_eta.setValue(0.5)
        self.spin_eta.setDecimals(3)
        pl.addRow("효율 η:", self.spin_eta)

        self.combo_integration = QComboBox()
        self.combo_integration.addItems(["피크 주변(자동)", "전체 구간"])
        pl.addRow("적분 구간:", self.combo_integration)

        warn = QLabel("절대 교정 없이 사용 시 '추측'으로 표기됩니다.")
        warn.setStyleSheet("color: #ff9800; font-size: 10px;")
        warn.setWordWrap(True)
        pl.addRow(warn)

        self.btn_compute = QPushButton("계산")
        self.btn_compute.setStyleSheet(
            "QPushButton { background: #6a1b9a; color: white; font-weight: bold; padding: 8px; }"
        )
        self.btn_compute.clicked.connect(self._on_compute)
        pl.addRow(self.btn_compute)

        layout.addWidget(param_group)

        # 결과
        result_group = QGroupBox("결과")
        rl = QVBoxLayout(result_group)
        self.txt_result = QTextEdit()
        self.txt_result.setReadOnly(True)
        self.txt_result.setPlaceholderText("계산 결과")
        rl.addWidget(self.txt_result)
        layout.addWidget(result_group)

        self.content_layout.addLayout(layout, stretch=1)

    def on_enter(self):
        super().on_enter()
        self.obs_list.set_observations(self._observations)
        if self._observations:
            idx = self._current_idx if 0 <= self._current_idx < len(self._observations) else 0
            self._on_select(idx)
        else:
            self.lbl_target.setText("-")

    def _on_select(self, idx: int):
        self._current_idx = idx
        obs = self.current_obs
        if obs is not None:
            self.lbl_target.setText(obs.display_name)
            # 관측 전환 시 이전 결과를 지우고 새 관측 기준으로 자동 계산
            self._on_compute()
        else:
            self.lbl_target.setText("-")
            self.txt_result.clear()

    def _to_axis_value(self, obs, value: float, from_unit: str, to_unit: str) -> float | None:
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

    def _build_auto_line_mask(self, obs, x, axis_unit: str) -> tuple[np.ndarray, str]:
        x_arr = np.asarray(x, dtype=float)
        mask = np.zeros(len(x_arr), dtype=bool)

        finite_x = x_arr[np.isfinite(x_arr)]
        if finite_x.size >= 2:
            dx = float(np.median(np.abs(np.diff(np.sort(finite_x)))))
        else:
            dx = 1.0
        min_half = max(dx * 6.0, 0.1)

        source = "없음"
        if obs.fit_result and obs.fit_result.success and obs.fit_result.components:
            fit_unit = str(obs.fit_result.x_unit or axis_unit)
            for c in obs.fit_result.components:
                center = self._to_axis_value(obs, c.center, fit_unit, axis_unit)
                if center is None:
                    continue
                width = self._to_axis_width(obs, c.fwhm, c.center, fit_unit, axis_unit)
                half = max(1.5 * width, min_half)
                mask |= np.abs(x_arr - center) <= half
            source = "fit"

        if not np.any(mask):
            peaks = obs.metadata.get("peaks", [])
            for p in peaks:
                try:
                    pos_saved = float(p.get("pos"))
                    unit_saved = str(p.get("unit", axis_unit))
                except (TypeError, ValueError):
                    continue
                pos = self._to_axis_value(obs, pos_saved, unit_saved, axis_unit)
                if pos is None:
                    continue
                width = self._to_axis_width(obs, p.get("width", 0.0), pos_saved, unit_saved, axis_unit)
                half = max(1.5 * width, min_half)
                mask |= np.abs(x_arr - pos) <= half
            source = "peaks"

        if np.count_nonzero(mask) < 3:
            mask = np.isfinite(x_arr)
            source = "full-fallback"

        return mask, source

    def _on_compute(self):
        obs = self.current_obs
        if obs is None:
            self.txt_result.setPlainText("관측 데이터 없음")
            return

        eta = self.spin_eta.value()
        lines = []
        lines.append(f"관측: {obs.display_name}")

        use_velocity = obs.is_velocity_converted and obs.vel_kms is not None
        x = obs.vel_kms if use_velocity else obs.freq_mhz
        integ_unit = "km/s" if use_velocity else "MHz"
        axis_unit = "km/s" if use_velocity else "mhz"

        integ_mode = self.combo_integration.currentText()
        mask = None
        mode_used = "full"
        if x is not None and integ_mode == "피크 주변(자동)":
            mask, mode_used = self._build_auto_line_mask(obs, x, axis_unit)
            lines.append(f"적분 구간: 피크 주변 자동 ({mode_used})")
        else:
            lines.append("적분 구간: 전체")

        if obs.is_calibrated and obs.antenna_temp_k is not None:
            # ── Y-factor 교정 데이터 사용 ──
            t_sys = obs.metadata.get("t_sys_k", 0)
            r0 = obs.metadata.get("r_median", 0)
            lines.append(f"[Y-factor 교정 완료] R_0={r0:.4f}, T_sys={t_sys:.0f} K")
            if t_sys and float(t_sys) > 3000:
                lines.append("[주의] T_sys가 비정상적으로 큽니다. AMB/SOU 레벨과 baseline을 다시 확인하세요.")
            lines.append(f"η = {eta:.3f}")
            lines.append("")

            t_ant = obs.antenna_temp_k
            t_b = brightness_temperature(t_ant, eta)

            if x is not None:
                n = min(len(x), len(t_ant), len(t_b))
                x_use = np.asarray(x[:n], dtype=float)
                t_ant_use = np.asarray(t_ant[:n], dtype=float)
                t_b_use = np.asarray(t_b[:n], dtype=float)
                if mask is not None:
                    m = np.asarray(mask[:n], dtype=bool)
                else:
                    m = np.ones(n, dtype=bool)

                integ_ant = integrated_intensity(x_use[m], t_ant_use[m])
                integ_b = integrated_intensity(x_use[m], t_b_use[m])
                lines.append(f"적분 강도 (T*_A): {integ_ant:.4f} K·{integ_unit}")
                lines.append(f"적분 강도 (T_B):  {integ_b:.4f} K·{integ_unit}")

                if not use_velocity:
                    lines.append("N_HI: 계산 생략 (속도축 변환 필요: Step 7)")
                elif integ_b > 0:
                    n_hi = column_density_hi(integ_b)
                    lines.append(f"N_HI = {n_hi:.3e} cm⁻²")
                    if n_hi > 1.0e22:
                        lines.append("[주의] N_HI가 매우 큽니다. 적분 구간/잔여 baseline 영향 여부를 점검하세요.")
                else:
                    lines.append("N_HI: 계산 생략 (적분값<=0)")
        else:
            # ── 비교정 (근사법) ──
            lines.append(f"Tsys = {self.spin_tsys.value():.1f} K (추측)")
            lines.append(f"η = {eta:.3f} (추측)")
            lines.append("")

            y = obs.psd_db_baseline_removed if obs.is_baseline_removed else (
                obs.psd_db_clean if obs.is_preprocessed else obs.psd_db
            )
            if x is not None and y is not None:
                n = min(len(x), len(y))
                x_use = np.asarray(x[:n], dtype=float)
                y_use = np.asarray(y[:n], dtype=float)
                if mask is not None:
                    m = np.asarray(mask[:n], dtype=bool)
                else:
                    m = np.ones(n, dtype=bool)

                integ = integrated_intensity(x_use[m], y_use[m])
                lines.append(f"적분 강도 (raw): {integ:.4f}")

                t_ant = psd_to_temperature(y_use, self.spin_tsys.value())
                t_b = brightness_temperature(t_ant, eta)
                integ_t = integrated_intensity(x_use[m], t_ant[m])
                integ_b = integrated_intensity(x_use[m], t_b[m])
                lines.append(f"적분 강도 (T*_A, 근사): {integ_t:.4f} K·{integ_unit}")
                lines.append(f"적분 강도 (T_B, 근사):  {integ_b:.4f} K·{integ_unit}")

                if not use_velocity:
                    lines.append("N_HI: 계산 생략 (속도축 변환 필요: Step 7)")
                elif integ_b > 0:
                    n_hi = column_density_hi(integ_b)
                    lines.append(f"N_HI (추정): {n_hi:.3e} cm⁻²")
                    if n_hi > 1.0e22:
                        lines.append("[주의] N_HI가 매우 큽니다. 적분 구간/잔여 baseline 영향 여부를 점검하세요.")
                else:
                    lines.append("N_HI: 계산 생략 (적분값<=0)")

        # 피팅 성분별
        if obs.fit_result and obs.fit_result.success:
            lines.append("\n── 피팅 성분별 ──")
            fit_unit = str(obs.fit_result.x_unit or "").strip().lower()
            for i, c in enumerate(obs.fit_result.components):
                ci = component_integrated(c)
                lines.append(f"  성분 {i+1}: ∫ = {ci:.4f}")
                if fit_unit == "km/s":
                    if obs.is_calibrated and eta > 0:
                        ci_tb = ci / eta
                        if ci_tb > 0:
                            lines.append(f"           N_HI(T_B) ≈ {column_density_hi(ci_tb):.3e} cm⁻²")
                    elif ci > 0:
                        lines.append(f"           N_HI(근사) ≈ {column_density_hi(ci):.3e} cm⁻²")

        self.txt_result.setPlainText("\n".join(lines))

    def save_state(self):
        self.project_state.store_step_data("step11", {
            "tsys": self.spin_tsys.value(),
            "eta": self.spin_eta.value(),
            "integration": self.combo_integration.currentText(),
        })

    def restore_state(self):
        data = self.project_state.get_step_data("step11")
        if not data:
            return
        if "tsys" in data:
            self.spin_tsys.setValue(float(data["tsys"]))
        if "eta" in data:
            self.spin_eta.setValue(float(data["eta"]))
        if "integration" in data:
            idx = self.combo_integration.findText(str(data["integration"]))
            if idx >= 0:
                self.combo_integration.setCurrentIndex(idx)

    def validate_step(self) -> bool:
        return True  # 선택 단계
