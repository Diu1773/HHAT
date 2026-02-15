"""Step 13: 은하지도 맵."""

from __future__ import annotations

import numpy as np

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGroupBox, QFormLayout, QLabel, QPushButton,
    QComboBox, QCheckBox, QDoubleSpinBox,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from src.analysis.step_base import StepBase
from src.models.observation import ObsType
from src.models.project_state import ProjectState


class GalacticMapCanvas(FigureCanvasQTAgg):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(8, 5), dpi=100)
        self.fig.set_facecolor("#1e1e2e")
        super().__init__(self.fig)
        self.ax = self.fig.add_subplot(111)
        self._cbar = None
        self._style_axis()

    def _style_axis(self):
        self.ax.set_facecolor("#1e1e2e")
        self.ax.tick_params(colors="white")
        self.ax.xaxis.label.set_color("white")
        self.ax.yaxis.label.set_color("white")
        self.ax.title.set_color("white")
        for spine in self.ax.spines.values():
            spine.set_color("#555")
        self.ax.grid(True, alpha=0.25, color="#555")

    def clear(self):
        self.ax.clear()
        self._style_axis()
        if self._cbar is not None:
            self._cbar.remove()
            self._cbar = None
        self.draw()


class Step13Batch(StepBase):
    """은하좌표(l,b) 스캐터 맵."""

    def __init__(self, project_state: ProjectState, parent=None):
        super().__init__(
            step_index=12,
            step_name="은하지도 맵",
            step_description=(
                "관측의 Galactic 좌표(l,b)를 은하지도 위에 표시합니다. "
                "색상은 타입/속도/세기로 선택할 수 있습니다."
            ),
            project_state=project_state,
            parent=parent,
        )

    def setup_ui(self):
        splitter = QSplitter(Qt.Orientation.Vertical)

        top = QWidget()
        tl = QHBoxLayout(top)

        cfg = QGroupBox("맵 옵션")
        cl = QFormLayout(cfg)

        self.combo_color = QComboBox()
        self.combo_color.addItems([
            "관측 타입",
            "대표 속도 (km/s)",
            "대표 세기",
        ])
        cl.addRow("색상 기준:", self.combo_color)

        self.combo_render = QComboBox()
        self.combo_render.addItems(["빔 커버리지", "포인트"])
        self.combo_render.currentTextChanged.connect(self._on_render_mode_changed)
        cl.addRow("표시 방식:", self.combo_render)

        self.spin_beam = QDoubleSpinBox()
        self.spin_beam.setRange(1.0, 60.0)
        self.spin_beam.setDecimals(1)
        self.spin_beam.setValue(10.0)
        self.spin_beam.setSuffix(" deg")
        cl.addRow("빔 FWHM:", self.spin_beam)

        self.chk_label = QCheckBox("관측 ID 라벨 표시")
        self.chk_label.setChecked(False)
        cl.addRow(self.chk_label)

        self.btn_plot = QPushButton("맵 갱신")
        self.btn_plot.setStyleSheet(
            "QPushButton { background: #1565c0; color: white; font-weight: bold; padding: 8px; }"
        )
        self.btn_plot.clicked.connect(self._plot_map)
        cl.addRow(self.btn_plot)

        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet("color: #aaa; font-size: 11px;")
        self.lbl_info.setWordWrap(True)
        cl.addRow(self.lbl_info)

        tl.addWidget(cfg)
        tl.addStretch()

        splitter.addWidget(top)

        self.canvas = GalacticMapCanvas()
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.toolbar.setStyleSheet("background: #2a2a3e; color: white;")

        plot_container = QWidget()
        pl = QVBoxLayout(plot_container)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.addWidget(self.toolbar)
        pl.addWidget(self.canvas)
        splitter.addWidget(plot_container)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self.content_layout.addWidget(splitter, stretch=1)
        self._on_render_mode_changed(self.combo_render.currentText())

    def on_enter(self):
        super().on_enter()
        self._plot_map()

    def _on_render_mode_changed(self, mode: str):
        is_point = (mode == "포인트")
        self.combo_color.setEnabled(is_point)
        self.chk_label.setEnabled(is_point)
        self.spin_beam.setEnabled(not is_point)

    def _value_from_obs(self, obs):
        metric = self.combo_color.currentText()
        if metric == "대표 속도 (km/s)":
            if obs.fit_result and obs.fit_result.success and obs.fit_result.components:
                strongest = max(obs.fit_result.components, key=lambda c: abs(c.amplitude))
                fit_unit = (obs.fit_result.x_unit or "").lower()
                center = float(strongest.center)
                if fit_unit == "km/s":
                    return center
                if fit_unit == "mhz":
                    converted = self._freq_to_vel(obs, center)
                    if converted is not None:
                        return converted
            peaks = obs.metadata.get("peaks", [])
            if peaks:
                p = peaks[0]
                unit = str(p.get("unit", "")).lower()
                try:
                    pos = float(p.get("pos"))
                except (TypeError, ValueError):
                    pos = np.nan
                if np.isfinite(pos):
                    if unit == "km/s":
                        return pos
                    if unit == "mhz":
                        converted = self._freq_to_vel(obs, pos)
                        if converted is not None:
                            return converted
            return np.nan

        if metric == "대표 세기":
            if obs.fit_result and obs.fit_result.success and obs.fit_result.components:
                strongest = max(obs.fit_result.components, key=lambda c: abs(c.amplitude))
                return float(strongest.amplitude)
            peaks = obs.metadata.get("peaks", [])
            if peaks:
                try:
                    return float(peaks[0].get("amp", np.nan))
                except (TypeError, ValueError):
                    return np.nan
            return np.nan

        return np.nan

    def _freq_to_vel(self, obs, freq_mhz: float) -> float | None:
        if obs.freq_mhz is None or obs.vel_kms is None:
            return None
        freq = np.asarray(obs.freq_mhz, dtype=float)
        vel = np.asarray(obs.vel_kms, dtype=float)
        valid = np.isfinite(freq) & np.isfinite(vel)
        if np.count_nonzero(valid) < 2:
            return None
        freq = freq[valid]
        vel = vel[valid]
        order = np.argsort(freq)
        return float(np.interp(freq_mhz, freq[order], vel[order]))

    def _plot_map(self):
        self.canvas.clear()
        ax = self.canvas.ax
        ax.set_title("Galactic Map (l, b)")
        ax.set_xlabel("Galactic Longitude l (deg)")
        ax.set_ylabel("Galactic Latitude b (deg)")
        ax.set_xlim(0, 360)
        ax.set_ylim(-90, 90)

        rows = []
        for obs in self._observations:
            # AMB 관측은 하늘을 관측한 것이 아니므로 은하지도에서 제외
            if obs.obs_type == ObsType.AMB:
                continue
            l = obs.metadata.get("gal_l")
            b = obs.metadata.get("gal_b")
            if l is None or b is None:
                continue
            try:
                ll = float(l)
                bb = float(b)
            except (TypeError, ValueError):
                continue
            rows.append((obs, ll % 360.0, bb))

        if not rows:
            self.lbl_info.setText("표시할 좌표가 없습니다. Step 8에서 LSR/좌표 변환을 먼저 실행하세요.")
            self.canvas.draw()
            return

        render_mode = self.combo_render.currentText()
        if render_mode == "빔 커버리지":
            self._plot_beam_coverage(rows)
            return

        metric = self.combo_color.currentText()
        if metric == "관측 타입":
            palette = {
                ObsType.SOU: "#66ccff",
                ObsType.AMB: "#ff9800",
                ObsType.SKY: "#9c27b0",
                ObsType.UNKNOWN: "#9e9e9e",
            }
            for obs_type in ObsType:
                subset = [(o, l, b) for (o, l, b) in rows if o.obs_type == obs_type]
                if not subset:
                    continue
                xs = [l for _, l, _ in subset]
                ys = [b for _, _, b in subset]
                ax.scatter(xs, ys, s=46, c=palette[obs_type], edgecolors="#111", linewidths=0.6, label=obs_type.value)
        else:
            xs = np.array([l for _, l, _ in rows], dtype=float)
            ys = np.array([b for _, _, b in rows], dtype=float)
            vals = np.array([self._value_from_obs(o) for o, _, _ in rows], dtype=float)
            finite = np.isfinite(vals)

            if np.any(finite):
                sc = ax.scatter(
                    xs[finite], ys[finite], c=vals[finite],
                    cmap="coolwarm", s=52, edgecolors="#111", linewidths=0.6,
                )
                self.canvas._cbar = self.canvas.fig.colorbar(sc, ax=ax, pad=0.02)
                self.canvas._cbar.ax.tick_params(colors="white")
                self.canvas._cbar.outline.set_edgecolor("#555")
                self.canvas._cbar.set_label(metric, color="white")
            if np.any(~finite):
                ax.scatter(xs[~finite], ys[~finite], s=46, c="#777", edgecolors="#111", linewidths=0.6, label="N/A")

        if self.chk_label.isChecked():
            for obs, l, b in rows:
                ax.text(l + 1.5, b + 1.0, obs.display_name, fontsize=7, color="#ddd")

        ax.legend(fontsize=8, facecolor="#2a2a3e", edgecolor="#555", labelcolor="white", loc="upper right")
        self.lbl_info.setText(f"표시 관측: {len(rows)}개")
        self.canvas.fig.tight_layout()
        self.canvas.draw()

    def _plot_beam_coverage(self, rows):
        """빔 분해능(FWHM) 기반 커버리지 맵."""
        ax = self.canvas.ax
        beam_fwhm = float(self.spin_beam.value())
        sigma = max(beam_fwhm / 2.355, 0.2)

        l_bins = np.linspace(0.0, 360.0, 361)
        b_bins = np.linspace(-90.0, 90.0, 181)
        ll, bb = np.meshgrid(l_bins, b_bins)
        coverage = np.zeros_like(ll, dtype=float)

        for _, l0, b0 in rows:
            dlon = np.abs(ll - l0)
            dlon = np.minimum(dlon, 360.0 - dlon)  # 경도 주기 처리
            dlat = bb - b0
            # 구면 근사: 경도 거리 축소(cos b) 반영
            mean_lat = 0.5 * (bb + b0)
            cos_lat = np.clip(np.cos(np.deg2rad(mean_lat)), 0.05, 1.0)
            dist2 = (dlon * cos_lat) ** 2 + dlat ** 2
            coverage += np.exp(-0.5 * dist2 / (sigma ** 2))

        im = ax.imshow(
            coverage,
            extent=[0, 360, -90, 90],
            origin="lower",
            cmap="magma",
            aspect="auto",
            interpolation="bilinear",
        )
        self.canvas._cbar = self.canvas.fig.colorbar(im, ax=ax, pad=0.02)
        self.canvas._cbar.ax.tick_params(colors="white")
        self.canvas._cbar.outline.set_edgecolor("#555")
        self.canvas._cbar.set_label("Coverage (beam-weighted)", color="white")

        # 관측 중심점은 작은 마커로 같이 표시
        xs = [l for _, l, _ in rows]
        ys = [b for _, _, b in rows]
        ax.scatter(xs, ys, s=18, c="#a7f3d0", edgecolors="#111", linewidths=0.5, alpha=0.9)

        ax.set_title(f"Galactic Beam Coverage (FWHM={beam_fwhm:.1f}°)")
        self.lbl_info.setText(f"빔 커버리지 표시: {len(rows)}개 관측")
        self.canvas.fig.tight_layout()
        self.canvas.draw()

    def save_state(self):
        self.project_state.store_step_data("step13", {
            "color_metric": self.combo_color.currentText(),
            "show_labels": self.chk_label.isChecked(),
            "render_mode": self.combo_render.currentText(),
            "beam_fwhm": self.spin_beam.value(),
        })

    def restore_state(self):
        data = self.project_state.get_step_data("step13")
        if not data:
            return
        if "color_metric" in data:
            idx = self.combo_color.findText(str(data["color_metric"]))
            if idx >= 0:
                self.combo_color.setCurrentIndex(idx)
        if "show_labels" in data:
            self.chk_label.setChecked(bool(data["show_labels"]))
        if "render_mode" in data:
            idx = self.combo_render.findText(str(data["render_mode"]))
            if idx >= 0:
                self.combo_render.setCurrentIndex(idx)
        if "beam_fwhm" in data:
            self.spin_beam.setValue(float(data["beam_fwhm"]))
        self._on_render_mode_changed(self.combo_render.currentText())

    def validate_step(self) -> bool:
        return True
