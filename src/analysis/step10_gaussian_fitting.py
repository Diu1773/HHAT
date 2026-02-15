"""Step 10: 가우시안 분해/피팅"""

from __future__ import annotations

import numpy as np
import zlib

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGroupBox, QFormLayout, QLabel, QSpinBox, QComboBox,
    QPushButton, QTextEdit, QMessageBox,
)

from src.analysis.step_base import StepBase
from src.core.detection import detect_peaks, PeakCandidate
from src.core.fitting import fit_gaussians, evaluate_fit
from src.core.cache import save_cache
from src.widgets.spectrum_plot import SpectrumPlotWidget
from src.widgets.obs_list import ObsListWidget
from src.models.observation import ObsType, FitResult, FitComponent
from src.models.project_state import ProjectState


class Step10GaussianFitting(StepBase):
    """가우시안 피팅"""

    def __init__(self, project_state: ProjectState, parent=None):
        super().__init__(
            step_index=9,
            step_name="프로파일 피팅",
            step_description=(
                "검출된 피크를 초기값으로 Gaussian / Skewed Gaussian / Voigt "
                "모드의 다성분 피팅을 수행합니다."
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
        self.obs_list.setMaximumWidth(250)
        self.obs_list.observation_selected.connect(self._on_select)
        bl.addWidget(self.obs_list)

        ctrl = QGroupBox("가우시안 피팅")
        cl = QVBoxLayout(ctrl)

        self.btn_fit = QPushButton("피팅 실행")
        self.btn_fit.setStyleSheet(
            "QPushButton { background: #00897b; color: white; "
            "font-weight: bold; padding: 10px; font-size: 13px; }"
        )
        self.btn_fit.clicked.connect(self._on_fit)
        cl.addWidget(self.btn_fit)

        row = QHBoxLayout()
        row.addWidget(QLabel("피팅 모드:"))
        self.combo_model = QComboBox()
        self.combo_model.addItems(["gaussian", "skewed_gaussian", "voigt"])
        row.addWidget(self.combo_model)

        row.addWidget(QLabel("해법:"))
        self.combo_solver = QComboBox()
        self.combo_solver.addItems(["curve_fit", "mcmc"])
        row.addWidget(self.combo_solver)

        row.addWidget(QLabel("최대 성분 수:"))
        self.spin_max_comp = QSpinBox()
        self.spin_max_comp.setRange(1, 8)
        self.spin_max_comp.setValue(3)
        row.addWidget(self.spin_max_comp)

        row.addWidget(QLabel("MCMC steps:"))
        self.spin_mcmc_steps = QSpinBox()
        self.spin_mcmc_steps.setRange(200, 20000)
        self.spin_mcmc_steps.setSingleStep(200)
        self.spin_mcmc_steps.setValue(2500)
        row.addWidget(self.spin_mcmc_steps)

        row.addStretch()
        cl.addLayout(row)

        self.txt_result = QTextEdit()
        self.txt_result.setReadOnly(True)
        self.txt_result.setPlaceholderText("피팅 결과가 여기에 표시됩니다")
        cl.addWidget(self.txt_result)

        bl.addWidget(ctrl)
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

    def _on_select(self, idx: int):
        self._current_idx = idx
        obs = self.current_obs
        if obs:
            self.plot.set_velocity_mode(bool(obs.is_velocity_converted and obs.vel_kms is not None))
            self._render_observation(obs)

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

    def _build_peak_candidates(self, obs, x, y, axis_unit: str) -> list[PeakCandidate]:
        def _negated(peaks: list[PeakCandidate]) -> list[PeakCandidate]:
            return [
                PeakCandidate(
                    index=p.index,
                    position=p.position,
                    amplitude=-abs(p.amplitude),
                    width=p.width,
                    snr=p.snr,
                )
                for p in peaks
            ]

        def _dedup_by_pos(peaks: list[PeakCandidate], limit: int) -> list[PeakCandidate]:
            x_arr = np.asarray(x, dtype=float)
            if x_arr.size > 1:
                dx = float(np.median(np.abs(np.diff(np.sort(x_arr[np.isfinite(x_arr)])))))
            else:
                dx = 1.0
            min_sep = max(dx * 6.0, 1e-6)
            out: list[PeakCandidate] = []
            for pk in sorted(peaks, key=lambda p: abs(p.snr), reverse=True):
                if any(abs(pk.position - q.position) < min_sep for q in out):
                    continue
                out.append(pk)
                if len(out) >= limit:
                    break
            return out

        target_n = max(1, int(self.spin_max_comp.value()))
        seed_limit = max(target_n * 2, 4)

        saved_peaks: list[PeakCandidate] = []
        for p in obs.metadata.get("peaks", []):
            try:
                pos_saved = float(p["pos"])
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
                saved_peaks.append(PeakCandidate(
                    index=int(np.argmin(np.abs(x - pos))),
                    position=pos,
                    amplitude=float(p.get("amp", 0.0)),
                    width=width,
                    snr=float(p.get("snr", 0.0)),
                ))
            except (TypeError, ValueError, KeyError):
                continue

        auto_pos = detect_peaks(x, y, snr_threshold=2.3, min_width=5)
        auto_neg = _negated(detect_peaks(x, -y, snr_threshold=2.3, min_width=5))

        merged = _dedup_by_pos(saved_peaks + auto_pos, limit=seed_limit)
        if len(merged) < target_n:
            merged = _dedup_by_pos(merged + auto_neg, limit=seed_limit)

        if merged:
            return merged
        return _negated(detect_peaks(x, -y, snr_threshold=3.0, min_width=8))

    def _fit_result_for_axis(self, obs, fit_result: FitResult, axis_unit: str) -> FitResult:
        unit_src = str(fit_result.x_unit or axis_unit).strip().lower()
        unit_dst = str(axis_unit).strip().lower()
        if unit_src == unit_dst:
            return fit_result

        converted_components: list[FitComponent] = []
        for c in fit_result.components:
            center = self._to_axis_value(obs, c.center, unit_src, unit_dst)
            if center is None:
                continue
            fwhm = self._to_axis_width(obs, c.fwhm, c.center, unit_src, unit_dst)
            sigma = fwhm / 2.355 if fwhm > 0 else c.sigma
            shape = c.shape
            if c.model == "voigt":
                gamma_width_src = 2.0 * c.shape
                gamma_width_dst = self._to_axis_width(obs, gamma_width_src, c.center, unit_src, unit_dst)
                if gamma_width_dst > 0:
                    shape = gamma_width_dst / 2.0
            converted_components.append(FitComponent(
                amplitude=c.amplitude,
                center=center,
                sigma=sigma,
                fwhm=fwhm if fwhm > 0 else c.fwhm,
                model=c.model,
                shape=shape,
            ))

        x_ref_src = float(getattr(fit_result, "baseline_x_ref", 0.0))
        x_ref_dst = self._to_axis_value(obs, x_ref_src, unit_src, unit_dst)
        if x_ref_dst is None:
            x_ref_dst = x_ref_src
        slope_src = float(getattr(fit_result, "baseline_slope", 0.0))
        width_dst = self._to_axis_width(obs, 1.0, x_ref_src, unit_src, unit_dst)
        slope_dst = slope_src / width_dst if width_dst > 0 else slope_src

        return FitResult(
            components=converted_components,
            residual_rms=fit_result.residual_rms,
            success=fit_result.success,
            message=fit_result.message,
            model=fit_result.model,
            x_unit=axis_unit,
            baseline_offset=float(getattr(fit_result, "baseline_offset", 0.0)),
            baseline_slope=float(slope_dst),
            baseline_x_ref=float(x_ref_dst),
        )

    def _format_fit_text(self, fit_result: FitResult) -> str:
        if not fit_result.success:
            return f"피팅 실패: {fit_result.message}"
        lines = [
            f"모드: {fit_result.model}",
            f"축 단위: {fit_result.x_unit}",
            fit_result.message,
            (
                "Baseline: "
                f"offset={fit_result.baseline_offset:.2f}, "
                f"slope={fit_result.baseline_slope:.4f}/x"
            ),
        ]
        for i, c in enumerate(fit_result.components):
            extra = ""
            if c.model == "skewed_gaussian":
                extra = f", alpha={c.shape:.2f}"
            elif c.model == "voigt":
                extra = f", gamma={c.shape:.2f}"
            lines.append(
                f"성분 {i+1}: center={c.center:.2f}, amp={c.amplitude:.2f}, "
                f"FWHM={c.fwhm:.2f}, σ={c.sigma:.2f}{extra}"
            )
        lines.append(f"잔차 RMS: {fit_result.residual_rms:.4f}")
        return "\n".join(lines)

    def _render_observation(self, obs):
        self.plot.plot_observation(obs)
        x, _ = self._get_xy(obs)
        if x is None or obs.fit_result is None or not obs.fit_result.success:
            self.txt_result.setPlainText("저장된 피팅 결과 없음")
            return

        axis_unit = "km/s" if (obs.is_velocity_converted and obs.vel_kms is not None) else "mhz"
        fit_disp = self._fit_result_for_axis(obs, obs.fit_result, axis_unit)
        if not fit_disp.components:
            self.txt_result.setPlainText("저장된 피팅 결과를 현재 축으로 변환할 수 없습니다.")
            return

        x_fine = np.linspace(x.min(), x.max(), 500)
        y_fit, comp_curves = evaluate_fit(x_fine, fit_disp)
        ax = self.plot.ax
        # 피팅 오버레이가 축 스케일을 흔들지 않도록 원래 데이터 축을 고정한다.
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        ax.plot(x_fine, y_fit, color="#ff5722", lw=2, label=f"Fit ({fit_disp.model})")
        for i, y_c in enumerate(comp_curves):
            ax.plot(x_fine, y_c, "--", lw=1, alpha=0.7, label=f"Comp {i+1}")
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)
        ax.legend(fontsize=8, facecolor="#2a2a3e", edgecolor="#555", labelcolor="white")
        self.plot.canvas.draw()
        self.txt_result.setPlainText(self._format_fit_text(fit_disp))

    def _on_fit(self):
        obs = self.current_obs
        if obs is None:
            return

        self.plot.set_velocity_mode(bool(obs.is_velocity_converted and obs.vel_kms is not None))
        x, y = self._get_xy(obs)
        if x is None or y is None:
            return

        axis_unit = "km/s" if (obs.is_velocity_converted and obs.vel_kms is not None) else "mhz"
        peaks = self._build_peak_candidates(obs, x, y, axis_unit)

        peaks.sort(key=lambda p: abs(p.snr), reverse=True)
        peaks = peaks[: self.spin_max_comp.value()]

        if not peaks:
            QMessageBox.information(self, "알림", "피크가 없습니다. Step 9에서 먼저 검출하세요.")
            return

        result = fit_gaussians(
            x, y, peaks,
            model=self.combo_model.currentText(),
            x_unit=axis_unit,
            solver=self.combo_solver.currentText(),
            mcmc_steps=self.spin_mcmc_steps.value(),
            mcmc_seed=(zlib.crc32(obs.display_name.encode("utf-8")) & 0xffffffff),
        )
        obs.fit_result = result
        save_cache(obs)

        if result.success:
            self._render_observation(obs)
        else:
            self.txt_result.setPlainText(f"피팅 실패: {result.message}")

    def save_state(self):
        self.project_state.store_step_data("step10", {
            "max_components": self.spin_max_comp.value(),
            "fit_model": self.combo_model.currentText(),
            "solver": self.combo_solver.currentText(),
            "mcmc_steps": self.spin_mcmc_steps.value(),
        })

    def restore_state(self):
        data = self.project_state.get_step_data("step10")
        if not data:
            return
        if "max_components" in data:
            self.spin_max_comp.setValue(int(data["max_components"]))
        if "fit_model" in data:
            idx = self.combo_model.findText(str(data["fit_model"]))
            if idx >= 0:
                self.combo_model.setCurrentIndex(idx)
        if "solver" in data:
            idx = self.combo_solver.findText(str(data["solver"]))
            if idx >= 0:
                self.combo_solver.setCurrentIndex(idx)
        if "mcmc_steps" in data:
            self.spin_mcmc_steps.setValue(int(data["mcmc_steps"]))

    def validate_step(self) -> bool:
        return any(
            o.fit_result is not None and o.fit_result.success
            for o in self._observations
        )
