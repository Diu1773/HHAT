"""Matplotlib 기반 스펙트럼 플롯 위젯

display_mode로 각 Step이 원하는 데이터 레이어만 표시:
  "raw"              — 항상 원시 psd_db
  "clean"            — 전처리 결과 (없으면 raw fallback)
  "baseline_removed" — baseline 제거 결과 (없으면 clean → raw)
  "auto"             — 가장 진행된 결과 (기존 동작, 기본값)
"""

from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import QWidget, QVBoxLayout
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from src.models.observation import Observation
from src.utils.constants import HI_REST_FREQ_MHZ


class SpectrumCanvas(FigureCanvasQTAgg):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(8, 4), dpi=100)
        self.fig.set_facecolor("#1e1e2e")
        super().__init__(self.fig)
        self.ax = self.fig.add_subplot(111)
        self._style_axis()

    def _style_axis(self):
        self.ax.set_facecolor("#1e1e2e")
        self.ax.tick_params(colors="white")
        self.ax.xaxis.label.set_color("white")
        self.ax.yaxis.label.set_color("white")
        self.ax.title.set_color("white")
        for spine in self.ax.spines.values():
            spine.set_color("#555")
        self.ax.grid(True, alpha=0.3, color="#555")

    def clear(self):
        self.ax.clear()
        self._style_axis()
        self.draw()


class SpectrumPlotWidget(QWidget):
    """스펙트럼 표시 위젯

    Args:
        display_mode: "raw" | "clean" | "baseline_removed" | "auto"
    """

    def __init__(self, parent=None, display_mode: str = "auto"):
        super().__init__(parent)
        self._display_mode = display_mode
        self._use_velocity = False
        self._show_rfi_mask = False
        self._obs: Observation | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.canvas = SpectrumCanvas(self)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.toolbar.setStyleSheet("background: #2a2a3e; color: white;")

        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

    @property
    def ax(self):
        return self.canvas.ax

    def set_display_mode(self, mode: str):
        """표시 모드 변경: raw / clean / baseline_removed / auto"""
        self._display_mode = mode
        self._refresh()

    def plot_observation(self, obs: Observation):
        self._obs = obs
        self._refresh()

    def set_velocity_mode(self, enabled: bool):
        self._use_velocity = enabled
        self._refresh()

    def set_show_rfi_mask(self, enabled: bool):
        self._show_rfi_mask = enabled
        self._refresh()

    def _resolve_y(self, obs: Observation) -> tuple[np.ndarray | None, str]:
        """display_mode에 따라 Y축 데이터와 라벨을 결정한다."""
        mode = self._display_mode

        if mode == "raw":
            return obs.psd_db, "Power (dB, raw)"

        if mode == "clean":
            if obs.psd_db_clean is not None:
                return obs.psd_db_clean, "Power (dB, cleaned)"
            return obs.psd_db, "Power (dB, raw)"

        if mode == "baseline_removed":
            # Y-factor 교정 데이터 우선
            if obs.is_calibrated and obs.antenna_temp_k is not None:
                return obs.antenna_temp_k, "T*_A (K, Y-factor)"
            if obs.psd_db_baseline_removed is not None:
                return obs.psd_db_baseline_removed, "Power (dB, baseline removed)"
            if obs.psd_db_clean is not None:
                return obs.psd_db_clean, "Power (dB, cleaned)"
            return obs.psd_db, "Power (dB, raw)"

        # "auto" — 가장 진행된 결과
        if obs.is_calibrated and obs.antenna_temp_k is not None:
            return obs.antenna_temp_k, "T*_A (K, Y-factor)"
        if obs.psd_db_baseline_removed is not None and obs.is_baseline_removed:
            return obs.psd_db_baseline_removed, "Power (dB, baseline removed)"
        if obs.psd_db_clean is not None and obs.is_preprocessed:
            return obs.psd_db_clean, "Power (dB, cleaned)"
        return obs.psd_db, "Power (dB, raw)"

    def _refresh(self):
        obs = self._obs
        if obs is None or obs.psd_db is None:
            self.canvas.clear()
            return

        ax = self.ax
        ax.clear()
        self.canvas._style_axis()

        # X축
        if self._use_velocity and obs.vel_kms is not None:
            x = obs.vel_kms
            xlabel = "Velocity (km/s)"
        elif obs.freq_mhz is not None:
            x = obs.freq_mhz
            xlabel = "Frequency (MHz)"
        else:
            x = np.arange(len(obs.psd_db))
            xlabel = "Channel"

        # Y축 (display_mode에 따라)
        y, ylabel = self._resolve_y(obs)
        if y is None:
            self.canvas.clear()
            return

        # 길이 불일치 시 작은 쪽에 맞춤
        n = min(len(x), len(y))
        x = x[:n]
        y = y[:n]
        ax.plot(x, y, color="#66ccff", linewidth=0.7, label="Spectrum")

        # 속도축은 항상 일반적인 좌->우 증가 방향으로 표시한다.
        if self._use_velocity and len(x) > 1:
            finite_x = np.asarray(x, dtype=float)
            finite_x = finite_x[np.isfinite(finite_x)]
            if finite_x.size >= 2:
                ax.set_xlim(float(np.min(finite_x)), float(np.max(finite_x)))

        # RFI 마스크 오버레이
        if self._show_rfi_mask and obs.mask_rfi is not None:
            try:
                masked_x = x[obs.mask_rfi]
                masked_y = obs.psd_db[obs.mask_rfi]
                ax.scatter(masked_x, masked_y, color="red", s=4, alpha=0.6, label="RFI", zorder=3)
            except (IndexError, ValueError):
                pass

        # HI 선 표시
        if not self._use_velocity and obs.freq_mhz is not None:
            ax.axvline(HI_REST_FREQ_MHZ, color="#ff6666", ls="--", alpha=0.7,
                       label=f"HI ({HI_REST_FREQ_MHZ} MHz)")
        elif self._use_velocity:
            ax.axvline(0, color="#ff6666", ls="--", alpha=0.7, label="V=0 km/s")

        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(obs.display_name, fontsize=10)
        ax.legend(fontsize=8, loc="upper right", facecolor="#2a2a3e",
                  edgecolor="#555", labelcolor="white")

        self.canvas.fig.tight_layout()
        self.canvas.draw()
