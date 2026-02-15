"""Step 6: Baseline(연속선) 처리 — 모드 A(파일) / 모드 B(다항식) / 모드 C(Y-factor)"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGroupBox, QFormLayout, QLabel,
    QPushButton, QSpinBox, QDoubleSpinBox, QComboBox,
    QFileDialog, QMessageBox, QScrollArea,
)

from src.analysis.step_base import StepBase
from src.core.baseline import subtract_baseline_file, remove_baseline
from src.core.calibration import yfactor_calibrate
from src.core.cache import save_cache, clear_cache
from src.widgets.spectrum_plot import SpectrumPlotWidget
from src.widgets.obs_list import ObsListWidget
from src.models.observation import ObsType
from src.models.project_state import ProjectState


class Step6Baseline(StepBase):
    """Baseline(연속선) 제거 / Y-factor 교정"""

    def __init__(self, project_state: ProjectState, parent=None):
        super().__init__(
            step_index=5,
            step_name="Baseline 제거 / 교정",
            step_description=(
                "모드 A: 외부 baseline FITS를 빼기. "
                "모드 B: line-free 구간에서 다항식으로 연속선을 추정 후 제거. "
                "모드 C: SOU+AMB 쌍으로 Y-factor 교정 (안테나 온도 K)."
            ),
            project_state=project_state,
            parent=parent,
        )
        self._baseline_path: Path | None = None

    def setup_ui(self):
        splitter = QSplitter(Qt.Orientation.Vertical)

        self.plot = SpectrumPlotWidget(display_mode="baseline_removed")
        splitter.addWidget(self.plot)

        bottom = QWidget()
        bottom_layout = QHBoxLayout(bottom)

        self.obs_list = ObsListWidget()
        self.obs_list.btn_open.hide()
        self.obs_list.setMaximumWidth(300)
        self.obs_list.observation_selected.connect(self._on_select)
        bottom_layout.addWidget(self.obs_list)

        # --- 설정 패널 (스크롤) ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        ctrl_widget = QWidget()
        cl = QFormLayout(ctrl_widget)

        # ==================== 모드 A ====================
        lbl_a = QLabel("모드 A — 외부 Baseline 파일")
        lbl_a.setStyleSheet("color: #66ccff; font-weight: bold;")
        cl.addRow(lbl_a)

        self.btn_load = QPushButton("Baseline FITS 로드")
        self.btn_load.clicked.connect(self._on_load_file)
        cl.addRow(self.btn_load)

        self.lbl_file = QLabel("선택 안 됨")
        self.lbl_file.setStyleSheet("color: #888;")
        cl.addRow("파일:", self.lbl_file)

        self.btn_apply_a = QPushButton("모드 A 적용")
        self.btn_apply_a.setStyleSheet(
            "QPushButton { background: #7b1fa2; color: white; font-weight: bold; padding: 6px; }"
        )
        self.btn_apply_a.clicked.connect(self._on_apply_mode_a)
        cl.addRow(self.btn_apply_a)

        # ==================== 모드 B ====================
        lbl_b = QLabel("모드 B — 다항식 연속선 추정")
        lbl_b.setStyleSheet("color: #66ccff; font-weight: bold; margin-top: 8px;")
        cl.addRow(lbl_b)

        self.spin_deg = QSpinBox()
        self.spin_deg.setRange(1, 10)
        self.spin_deg.setValue(3)
        cl.addRow("다항식 차수:", self.spin_deg)

        self.btn_apply_b = QPushButton("모드 B 적용")
        self.btn_apply_b.setStyleSheet(
            "QPushButton { background: #7b1fa2; color: white; font-weight: bold; padding: 6px; }"
        )
        self.btn_apply_b.clicked.connect(self._on_apply_mode_b)
        cl.addRow(self.btn_apply_b)

        self.btn_apply_all = QPushButton("전체 적용 (모드 B)")
        self.btn_apply_all.clicked.connect(self._on_apply_all_b)
        cl.addRow(self.btn_apply_all)

        # ==================== 모드 C ====================
        lbl_c = QLabel("모드 C — Y-factor 교정 (SOU × AMB)")
        lbl_c.setStyleSheet("color: #ff9800; font-weight: bold; margin-top: 8px;")
        cl.addRow(lbl_c)

        desc_c = QLabel(
            "SOU와 AMB 관측의 비율로 수신기 이득 G(f)를 상쇄하고\n"
            "안테나 온도(K)를 구합니다."
        )
        desc_c.setStyleSheet("color: #aaa; font-size: 10px;")
        desc_c.setWordWrap(True)
        cl.addRow(desc_c)

        self.combo_amb = QComboBox()
        cl.addRow("AMB 관측:", self.combo_amb)

        # T_amb 입력 (K 또는 °C)
        tamb_row = QHBoxLayout()
        self.spin_t_amb = QDoubleSpinBox()
        self.spin_t_amb.setRange(-50, 400)
        self.spin_t_amb.setDecimals(1)
        self.spin_t_amb.setValue(295.0)
        tamb_row.addWidget(self.spin_t_amb)

        self.combo_t_unit = QComboBox()
        self.combo_t_unit.addItems(["K", "°C"])
        self.combo_t_unit.setMaximumWidth(50)
        self.combo_t_unit.currentTextChanged.connect(self._on_unit_changed)
        tamb_row.addWidget(self.combo_t_unit)
        cl.addRow("T_amb:", tamb_row)

        self.btn_apply_c = QPushButton("모드 C 적용 (Y-factor)")
        self.btn_apply_c.setStyleSheet(
            "QPushButton { background: #e65100; color: white; font-weight: bold; padding: 6px; }"
        )
        self.btn_apply_c.clicked.connect(self._on_apply_mode_c)
        cl.addRow(self.btn_apply_c)

        self.lbl_yfactor = QLabel("")
        self.lbl_yfactor.setStyleSheet("color: #ff9800; font-size: 11px;")
        self.lbl_yfactor.setWordWrap(True)
        cl.addRow(self.lbl_yfactor)

        # ==================== 공통 ====================
        reset_row = QHBoxLayout()
        self.btn_reset_current = QPushButton("현재 초기화")
        self.btn_reset_current.clicked.connect(self._on_reset_current)
        reset_row.addWidget(self.btn_reset_current)

        self.btn_reset_all = QPushButton("전체 초기화")
        self.btn_reset_all.clicked.connect(self._on_reset_all)
        reset_row.addWidget(self.btn_reset_all)
        cl.addRow(reset_row)

        scroll.setWidget(ctrl_widget)
        bottom_layout.addWidget(scroll)
        splitter.addWidget(bottom)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        self.content_layout.addWidget(splitter, stretch=1)

    # ----------------------------------------------------------------
    # 진입 / 선택
    # ----------------------------------------------------------------

    def on_enter(self):
        super().on_enter()
        self.obs_list.set_observations(self._observations)
        self._refresh_amb_combo()
        if self._observations:
            self._on_select(self._default_obs_index())

    def _default_obs_index(self) -> int:
        """Step 6 진입 시 기본 선택 인덱스 (SOU 우선)."""
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
            self._load_t_amb_from_meta()
            self.plot.plot_observation(obs)

    def _refresh_amb_combo(self):
        """AMB 타입 관측만 콤보에 표시"""
        self.combo_amb.clear()
        for obs in self._observations:
            if obs.obs_type == ObsType.AMB:
                self.combo_amb.addItem(obs.display_name, obs.obs_id)
        if self.combo_amb.count() == 0:
            self.combo_amb.addItem("(AMB 관측 없음)")

    def _find_amb_obs(self):
        """콤보에서 선택된 AMB 관측 반환"""
        obs_id = self.combo_amb.currentData()
        if obs_id is None:
            return None
        for obs in self._observations:
            if obs.obs_id == obs_id:
                return obs
        return None

    def _load_t_amb_from_meta(self):
        """선택된 AMB의 메타데이터에서 T_amb 로드"""
        amb = self._find_amb_obs()
        if amb is None:
            return
        t_amb = amb.metadata.get("t_amb")
        if t_amb is not None:
            self.combo_t_unit.setCurrentText("K")
            self.spin_t_amb.setValue(float(t_amb))

    def _get_t_amb_kelvin(self) -> float:
        """현재 입력된 T_amb를 K으로 반환"""
        val = self.spin_t_amb.value()
        if self.combo_t_unit.currentText() == "°C":
            return val + 273.15
        return val

    def _on_unit_changed(self, unit: str):
        """K ↔ °C 전환 시 값 변환"""
        val = self.spin_t_amb.value()
        if unit == "°C":
            # K → °C
            self.spin_t_amb.blockSignals(True)
            self.spin_t_amb.setRange(-273.15, 400)
            self.spin_t_amb.setValue(val - 273.15)
            self.spin_t_amb.setSuffix(" °C")
            self.spin_t_amb.blockSignals(False)
        else:
            # °C → K
            self.spin_t_amb.blockSignals(True)
            self.spin_t_amb.setRange(-50, 700)
            self.spin_t_amb.setValue(val + 273.15)
            self.spin_t_amb.setSuffix(" K")
            self.spin_t_amb.blockSignals(False)

    # ----------------------------------------------------------------
    # 공통 유틸
    # ----------------------------------------------------------------

    def _source_psd(self, obs):
        return obs.psd_db_clean if obs.is_preprocessed else obs.psd_db

    def _on_load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Baseline FITS", "", "FITS (*.fits)")
        if path:
            self._baseline_path = Path(path)
            self.lbl_file.setText(Path(path).name)
            self.lbl_file.setStyleSheet("color: #4caf50;")

    # ----------------------------------------------------------------
    # 모드 A — 외부 파일 빼기
    # ----------------------------------------------------------------

    def _on_apply_mode_a(self):
        obs = self.current_obs
        if obs is None:
            return
        if self._baseline_path is None or not self._baseline_path.exists():
            QMessageBox.warning(self, "오류", "Baseline 파일을 먼저 로드하세요.")
            return
        source = self._source_psd(obs)
        if source is None:
            return
        result = subtract_baseline_file(source, self._baseline_path)
        if result is None:
            QMessageBox.warning(self, "오류", "NFFT 불일치 또는 로드 실패")
            return
        obs.psd_db_baseline_removed = result
        obs.is_baseline_removed = True
        obs.metadata["baseline_mode"] = "file"
        save_cache(obs)
        self.plot.plot_observation(obs)

    # ----------------------------------------------------------------
    # 모드 B — 다항식
    # ----------------------------------------------------------------

    def _apply_mode_b(self, obs):
        source = self._source_psd(obs)
        if source is None or obs.freq_mhz is None:
            return
        freq = obs.freq_mhz
        f_range = freq.max() - freq.min()
        line_free = [
            (freq.min(), freq.min() + f_range * 0.25),
            (freq.max() - f_range * 0.25, freq.max()),
        ]
        removed, _ = remove_baseline(freq, source, line_free, degree=self.spin_deg.value())
        obs.psd_db_baseline_removed = removed
        obs.is_baseline_removed = True
        obs.metadata["baseline_mode"] = "poly"
        save_cache(obs)

    def _on_apply_mode_b(self):
        obs = self.current_obs
        if obs:
            self._apply_mode_b(obs)
            self.plot.plot_observation(obs)

    def _on_apply_all_b(self):
        for obs in self._observations:
            self._apply_mode_b(obs)
        if self.current_obs:
            self.plot.plot_observation(self.current_obs)

    # ----------------------------------------------------------------
    # 모드 C — Y-factor 교정
    # ----------------------------------------------------------------

    def _on_apply_mode_c(self):
        obs = self.current_obs
        if obs is None:
            return
        if obs.obs_type == ObsType.AMB:
            QMessageBox.warning(
                self, "오류",
                "현재 선택된 관측이 AMB입니다.\n"
                "모드 C는 SOU(소스) 관측을 선택한 뒤 실행하세요."
            )
            return

        amb = self._find_amb_obs()
        if amb is None:
            QMessageBox.warning(self, "오류", "AMB 관측을 선택하세요.\n(Step 2에서 AMB로 분류 필요)")
            return
        if amb.obs_id == obs.obs_id:
            QMessageBox.warning(
                self, "오류",
                "SOU와 AMB가 같은 관측으로 선택되었습니다.\n"
                "서로 다른 관측 쌍을 선택하세요."
            )
            return

        # 전처리 결과가 있으면 RFI 영향을 줄이기 위해 우선 사용
        sou_psd = obs.psd_db_clean if (obs.is_preprocessed and obs.psd_db_clean is not None) else obs.psd_db
        amb_psd = amb.psd_db_clean if (amb.is_preprocessed and amb.psd_db_clean is not None) else amb.psd_db
        if sou_psd is None or amb_psd is None:
            QMessageBox.warning(self, "오류", "SOU 또는 AMB의 PSD 데이터가 없습니다.")
            return

        t_amb_k = self._get_t_amb_kelvin()
        if t_amb_k <= 0:
            QMessageBox.warning(self, "오류", f"T_amb={t_amb_k:.1f} K — 물리적으로 불가능한 값입니다.")
            return

        result = yfactor_calibrate(sou_psd, amb_psd, t_amb_k)

        if not result.success:
            hint = (
                "확인: (1) 현재 관측이 SOU인지, "
                "(2) AMB가 다른 관측인지, "
                "(3) AMB가 혼 안테나를 충분히 덮었는지"
            )
            msg = f"{result.message}\n\n{hint}"
            QMessageBox.warning(self, "Y-factor 교정 실패", msg)
            self.lbl_yfactor.setText(f"실패: {msg}")
            return

        # 결과 저장
        obs.antenna_temp_k = result.antenna_temp_k
        obs.is_calibrated = True
        obs.is_baseline_removed = True  # 후속 스텝 호환
        obs.metadata["r_median"] = result.r_median
        obs.metadata["t_sys_k"] = result.t_sys_k
        obs.metadata["t_amb_k"] = t_amb_k
        obs.metadata["calibration_amb"] = amb.obs_id
        obs.metadata["baseline_mode"] = "yfactor"
        save_cache(obs)

        self.lbl_yfactor.setText(
            f"R_0 = {result.r_median:.4f} | "
            f"T_sys = {result.t_sys_k:.0f} K | "
            f"T_amb = {t_amb_k:.1f} K"
        )
        self.plot.plot_observation(obs)

    # ----------------------------------------------------------------
    # 초기화
    # ----------------------------------------------------------------

    def _reset_baseline(self, obs):
        if obs is None:
            return
        obs.psd_db_baseline_removed = None
        obs.is_baseline_removed = False
        obs.antenna_temp_k = None
        obs.is_calibrated = False
        for key in ("r_median", "t_sys_k", "t_amb_k", "calibration_amb", "baseline_mode"):
            obs.metadata.pop(key, None)

    def _on_reset_current(self):
        obs = self.current_obs
        self._reset_baseline(obs)
        if obs:
            save_cache(obs)
            self.plot.plot_observation(obs)
            self.step_status_changed.emit(self.step_index, f"{obs.display_name} baseline 초기화")

    def _on_reset_all(self):
        for obs in self._observations:
            self._reset_baseline(obs)
            save_cache(obs)
        if self.current_obs:
            self.plot.plot_observation(self.current_obs)
        self.step_status_changed.emit(self.step_index, f"전체 {len(self._observations)}개 baseline 초기화")

    def validate_step(self) -> bool:
        # AMB는 baseline 제거 대상이 아니므로 제외
        targets = [o for o in self._observations if o.obs_type != ObsType.AMB]
        if not targets:
            return True
        return any(o.is_baseline_removed or o.is_calibrated for o in targets)

    def save_state(self):
        self.project_state.store_step_data("step6", {
            "poly_degree": self.spin_deg.value(),
            "baseline_file": str(self._baseline_path) if self._baseline_path else "",
            "t_amb": self.spin_t_amb.value(),
            "t_amb_unit": self.combo_t_unit.currentText(),
        })

    def restore_state(self):
        data = self.project_state.get_step_data("step6")
        if not data:
            return
        if "poly_degree" in data:
            self.spin_deg.setValue(int(data["poly_degree"]))
        if data.get("baseline_file"):
            p = Path(data["baseline_file"])
            if p.exists():
                self._baseline_path = p
                self.lbl_file.setText(p.name)
                self.lbl_file.setStyleSheet("color: #4caf50;")
        if "t_amb_unit" in data:
            self.combo_t_unit.setCurrentText(data["t_amb_unit"])
        if "t_amb" in data:
            self.spin_t_amb.setValue(float(data["t_amb"]))
