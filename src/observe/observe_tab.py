"""관측 탭 — SDR 연결, 파라미터, 관측 실행, 라이브 프리뷰

레이아웃:
  ┌───────────────────────────────────────────────────────────┐
  │  SDR 상태 바                                     [연결확인] │
  ├────────────────────┬──────────────────────────────────────┤
  │                    │                                      │
  │  관측 설정 패널     │       라이브 스펙트럼 프리뷰            │
  │                    │                                      │
  │  ┌─ 관측 타입 ───┐ │                                      │
  │  │ SOU AMB SKY   │ │                                      │
  │  └───────────────┘ │                                      │
  │  ┌─ 파라미터 ────┐ │                                      │
  │  │ Gain/SR/CF/.. │ │                                      │
  │  └───────────────┘ │                                      │
  │  ┌─ 사이트/시간 ──┐ │                                      │
  │  │ 위도/경도/고도  │ │                                      │
  │  │ 시간대/alt/az  │ │                                      │
  │  └───────────────┘ │                                      │
  │  ┌─ 옵션 ────────┐ │      ┌────────────────────────────┐  │
  │  │ Bias-T/DC/Han │ │      │  관측 로그                   │  │
  │  └───────────────┘ │      └────────────────────────────┘  │
  │                    │                                      │
  │ [저장 경로 설정]    │        ┌─ 프로그레스 ─┐               │
  │ [ ★ 관측 시작 ★ ]  │        └──────────────┘               │
  └────────────────────┴──────────────────────────────────────┘
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGroupBox, QFormLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QDoubleSpinBox, QSpinBox,
    QCheckBox, QTextEdit, QFileDialog, QProgressBar,
    QButtonGroup, QRadioButton, QFrame, QScrollArea,
    QMessageBox,
)

from src.observe.sdr_controller import SDRController, ObsParams, ObservationWorker, SDRStatus
from src.widgets.spectrum_plot import SpectrumPlotWidget
from src.utils.constants import SITE_PRESETS


class ObserveTab(QWidget):
    """관측 탭 전체 위젯"""

    observation_completed = Signal(str)  # 완료된 폴더 경로

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sdr = SDRController()
        self._worker: ObservationWorker | None = None
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # ── SDR 상태 바 ──
        status_bar = QHBoxLayout()
        self.lbl_sdr_status = QLabel("SDR: 확인 중...")
        self.lbl_sdr_status.setStyleSheet(
            "font-weight: bold; font-size: 12px; padding: 4px 8px;"
        )
        status_bar.addWidget(self.lbl_sdr_status)
        status_bar.addStretch()
        self.btn_check_sdr = QPushButton("연결 확인")
        self.btn_check_sdr.clicked.connect(self._check_sdr)
        status_bar.addWidget(self.btn_check_sdr)
        main_layout.addLayout(status_bar)

        # 구분선
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #444;")
        main_layout.addWidget(line)

        # ── 메인 영역: 좌(설정) / 우(프리뷰) ──
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 좌측: 설정 패널 (스크롤)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(320)
        scroll.setMaximumWidth(420)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        settings_widget = QWidget()
        settings_layout = QVBoxLayout(settings_widget)
        settings_layout.setSpacing(6)

        settings_layout.addWidget(self._build_obs_type_group())
        settings_layout.addWidget(self._build_params_group())
        settings_layout.addWidget(self._build_site_group())
        settings_layout.addWidget(self._build_pointing_group())
        settings_layout.addWidget(self._build_options_group())
        settings_layout.addWidget(self._build_save_group())
        settings_layout.addWidget(self._build_control_group())
        settings_layout.addStretch()

        scroll.setWidget(settings_widget)
        splitter.addWidget(scroll)

        # 우측: 프리뷰 + 로그
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.preview_plot = SpectrumPlotWidget()
        right_layout.addWidget(self.preview_plot, stretch=3)

        # 프로그레스
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        right_layout.addWidget(self.progress_bar)

        # 로그
        log_group = QGroupBox("관측 로그")
        log_layout = QVBoxLayout(log_group)
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumHeight(150)
        log_layout.addWidget(self.txt_log)
        right_layout.addWidget(log_group)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)

    # ── 설정 그룹 빌더 ──

    def _build_obs_type_group(self) -> QGroupBox:
        """관측 타입 선택 (SOU / AMB / SKY) — 광학의 Light/Flat/Dark처럼"""
        group = QGroupBox("관측 타입")
        layout = QVBoxLayout(group)

        desc = QLabel(
            "관측 순서: SOU(은하면) 먼저 → AMB(흡수체/지면) 이어서 촬영\n"
            "같은 세션에서 SOU와 AMB를 쌍으로 기록해야 Y-factor 교정이 가능합니다."
        )
        desc.setStyleSheet("color: #ff9800; font-size: 10px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.obs_type_group = QButtonGroup(self)
        types = [
            ("SOU", "Source — 대상 관측 (은하면 등)", "#4caf50"),
            ("AMB", "Ambient — 주변 기준 (흡수체/상온)", "#ff9800"),
            ("SKY", "Sky — 하늘 기준 (빈 하늘)", "#42a5f5"),
        ]

        for type_id, label, color in types:
            rb = QRadioButton(label)
            rb.setStyleSheet(f"""
                QRadioButton {{ font-size: 12px; padding: 4px; }}
                QRadioButton::indicator:checked {{ background: {color}; border: 2px solid {color}; border-radius: 7px; }}
            """)
            rb.setProperty("obs_type", type_id)
            self.obs_type_group.addButton(rb)
            layout.addWidget(rb)
            if type_id == "SOU":
                rb.setChecked(True)

        # 관측 이름 (사용자 메모)
        name_layout = QFormLayout()
        self.txt_obs_name = QLineEdit()
        self.txt_obs_name.setPlaceholderText("예: Cygnus_A, 은하면_l90")
        name_layout.addRow("관측 이름:", self.txt_obs_name)
        layout.addLayout(name_layout)

        return group

    def _build_params_group(self) -> QGroupBox:
        """SDR 파라미터"""
        group = QGroupBox("수신 파라미터")
        layout = QFormLayout(group)

        # Gain (권장 가이드 포함)
        self.spin_gain = QDoubleSpinBox()
        self.spin_gain.setRange(0, 50)
        self.spin_gain.setValue(25.0)
        self.spin_gain.setSuffix(" dB")
        self.spin_gain.setDecimals(1)
        self.spin_gain.setToolTip(
            "권장: 20~30 dB\n"
            "스펙트럼 최대값이 -20 ~ -10 dB/Hz 범위에 오도록 조절하세요.\n"
            "너무 높으면 포화, 너무 낮으면 SNR 부족."
        )
        layout.addRow("Gain:", self.spin_gain)

        gain_hint = QLabel("권장 20~30 dB — 스펙트럼 피크가 -20~-10 dB/Hz 범위")
        gain_hint.setStyleSheet("color: #ff9800; font-size: 9px;")
        gain_hint.setWordWrap(True)
        layout.addRow(gain_hint)

        self.txt_sample_rate = QLineEdit("2.4e6")
        self.txt_sample_rate.setToolTip("Hz 단위. 수식 가능 (예: 2.4e6)\n실습 권장: 2.0~2.4 MHz")
        layout.addRow("Sample Rate:", self.txt_sample_rate)

        self.txt_center_freq = QLineEdit("1420.4e6")
        self.txt_center_freq.setToolTip("Hz 단위. HI 21cm 정지 주파수: 1420.405 MHz")
        layout.addRow("Center Freq:", self.txt_center_freq)

        self.spin_nfft = QComboBox()
        self.spin_nfft.addItems(["512", "1024", "2048", "4096", "8192"])
        self.spin_nfft.setCurrentText("2048")
        layout.addRow("NFFT:", self.spin_nfft)

        self.spin_iterations = QSpinBox()
        self.spin_iterations.setRange(100, 100000)
        self.spin_iterations.setValue(5000)
        self.spin_iterations.setSingleStep(500)
        self.spin_iterations.valueChanged.connect(self._update_integration_time)
        layout.addRow("Iterations:", self.spin_iterations)

        self.txt_samples_per_scan = QLineEdit("512*1024")
        self.txt_samples_per_scan.textChanged.connect(self._update_integration_time)
        layout.addRow("Samples/Scan:", self.txt_samples_per_scan)

        # 적분시간 표시 (초 단위)
        self.lbl_integration_time = QLabel("")
        self.lbl_integration_time.setStyleSheet("color: #66ccff; font-size: 10px; font-weight: bold;")
        layout.addRow("적분 시간:", self.lbl_integration_time)

        integ_hint = QLabel("50초 이상이면 충분합니다. 더 필요하면 여러 번 관측 후 평균.")
        integ_hint.setStyleSheet("color: #888; font-size: 9px;")
        integ_hint.setWordWrap(True)
        layout.addRow(integ_hint)

        return group

    def _update_integration_time(self):
        """iterations와 samples_per_scan으로 적분시간(초) 계산 표시"""
        try:
            sr = self._eval_expr(self.txt_sample_rate.text())
            sps = self._eval_expr(self.txt_samples_per_scan.text())
            iters = self.spin_iterations.value()
            if sr > 0 and sps > 0:
                total_sec = (sps * iters) / sr
                if total_sec >= 60:
                    self.lbl_integration_time.setText(f"{total_sec:.0f}초 ({total_sec/60:.1f}분)")
                else:
                    self.lbl_integration_time.setText(f"{total_sec:.1f}초")
            else:
                self.lbl_integration_time.setText("-")
        except Exception:
            self.lbl_integration_time.setText("-")

    def _build_site_group(self) -> QGroupBox:
        """관측지 설정"""
        group = QGroupBox("관측지")
        layout = QFormLayout(group)

        self.combo_site = QComboBox()
        self.combo_site.addItems(list(SITE_PRESETS.keys()))
        self.combo_site.currentTextChanged.connect(self._on_site_preset)
        layout.addRow("프리셋:", self.combo_site)

        self.spin_lat = QDoubleSpinBox()
        self.spin_lat.setRange(-90, 90)
        self.spin_lat.setDecimals(6)
        self.spin_lat.setValue(37.5665)
        self.spin_lat.setSuffix(" °")
        layout.addRow("위도:", self.spin_lat)

        self.spin_lon = QDoubleSpinBox()
        self.spin_lon.setRange(-180, 180)
        self.spin_lon.setDecimals(6)
        self.spin_lon.setValue(126.9780)
        self.spin_lon.setSuffix(" °")
        layout.addRow("경도:", self.spin_lon)

        self.spin_height = QDoubleSpinBox()
        self.spin_height.setRange(0, 9000)
        self.spin_height.setDecimals(1)
        self.spin_height.setValue(38.0)
        self.spin_height.setSuffix(" m")
        layout.addRow("고도:", self.spin_height)

        return group

    def _build_pointing_group(self) -> QGroupBox:
        """포인팅/시간 설정"""
        group = QGroupBox("포인팅 / 시간")
        layout = QFormLayout(group)

        self.combo_tz = QComboBox()
        self.combo_tz.addItems(["KST", "UTC"])
        layout.addRow("시간대:", self.combo_tz)

        self.chk_alt_az = QCheckBox("Alt/Az 입력")
        self.chk_alt_az.setChecked(False)
        layout.addRow(self.chk_alt_az)

        self.spin_alt = QDoubleSpinBox()
        self.spin_alt.setRange(0, 90)
        self.spin_alt.setDecimals(2)
        self.spin_alt.setSuffix(" °")
        self.spin_alt.setEnabled(False)
        layout.addRow("Alt (고도각):", self.spin_alt)

        self.spin_az = QDoubleSpinBox()
        self.spin_az.setRange(0, 360)
        self.spin_az.setDecimals(2)
        self.spin_az.setSuffix(" °")
        self.spin_az.setEnabled(False)
        layout.addRow("Az (방위각):", self.spin_az)

        self.chk_alt_az.toggled.connect(self.spin_alt.setEnabled)
        self.chk_alt_az.toggled.connect(self.spin_az.setEnabled)

        beam_info = QLabel(
            "빔 크기: ~14°×14° (피라미드 혼)\n"
            "포인팅 허용 오차: ±5° 이내면 충분"
        )
        beam_info.setStyleSheet("color: #888; font-size: 9px;")
        beam_info.setWordWrap(True)
        layout.addRow(beam_info)

        # 향후 ASCOM 연결
        self.btn_mount = QPushButton("가대 연결 (향후 지원)")
        self.btn_mount.setEnabled(False)
        self.btn_mount.setToolTip("ASCOM/INDI 드라이버 연결 시 Alt/Az 자동 기록")
        self.btn_mount.setStyleSheet("QPushButton { color: #666; }")
        layout.addRow(self.btn_mount)

        return group

    def _build_options_group(self) -> QGroupBox:
        group = QGroupBox("옵션")
        layout = QVBoxLayout(group)

        self.chk_bias_tee = QCheckBox("Bias-Tee (LNA 전원)")
        layout.addWidget(self.chk_bias_tee)

        self.chk_remove_dc = QCheckBox("DC Spike 제거")
        self.chk_remove_dc.setChecked(True)
        layout.addWidget(self.chk_remove_dc)

        self.chk_hanning = QCheckBox("Hanning Window 적용")
        self.chk_hanning.setChecked(True)
        layout.addWidget(self.chk_hanning)

        return group

    def _build_save_group(self) -> QGroupBox:
        group = QGroupBox("저장")
        layout = QVBoxLayout(group)

        path_row = QHBoxLayout()
        self.txt_save_dir = QLineEdit(str(Path.cwd()))
        self.txt_save_dir.setReadOnly(True)
        self.txt_save_dir.setStyleSheet("color: #66ccff;")
        path_row.addWidget(self.txt_save_dir)

        btn_browse = QPushButton("변경")
        btn_browse.clicked.connect(self._browse_save_dir)
        path_row.addWidget(btn_browse)
        layout.addLayout(path_row)

        return group

    def _build_control_group(self) -> QWidget:
        """관측 시작/중지 버튼"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 8, 0, 0)

        self.btn_start = QPushButton("★  관측 시작  ★")
        self.btn_start.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #c62828, stop:1 #e53935);
                color: white; font-size: 16px; font-weight: bold;
                padding: 14px; border-radius: 8px; border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #e53935, stop:1 #ef5350);
            }
            QPushButton:disabled { background: #555; color: #999; }
        """)
        self.btn_start.clicked.connect(self._on_start_observation)
        layout.addWidget(self.btn_start)

        return widget

    # ── 시그널 연결 ──

    def _connect_signals(self):
        self.sdr.status_changed.connect(self._on_sdr_status)

    # ── 슬롯 ──

    def _check_sdr(self):
        self.sdr.check_connection()

    @Slot(str, str)
    def _on_sdr_status(self, status: str, message: str):
        colors = {
            SDRStatus.CONNECTED: "#4caf50",
            SDRStatus.DISCONNECTED: "#f44336",
            SDRStatus.OBSERVING: "#ff9800",
            SDRStatus.ERROR: "#f44336",
        }
        color = colors.get(status, "#888")
        self.lbl_sdr_status.setText(f"SDR: {message}")
        self.lbl_sdr_status.setStyleSheet(
            f"font-weight: bold; font-size: 12px; padding: 4px 8px; color: {color};"
        )
        self.btn_start.setEnabled(status == SDRStatus.CONNECTED)

    def _on_site_preset(self, name: str):
        if name in SITE_PRESETS:
            p = SITE_PRESETS[name]
            self.spin_lat.setValue(p["lat"])
            self.spin_lon.setValue(p["lon"])
            self.spin_height.setValue(p["height"])

    def _browse_save_dir(self):
        d = QFileDialog.getExistingDirectory(self, "저장 폴더 선택")
        if d:
            self.txt_save_dir.setText(d)

    def _eval_expr(self, expr: str) -> float:
        """수식 문자열을 float으로 안전하게 평가 (숫자/산술만 허용)"""
        import ast
        import operator
        _ops = {
            ast.Add: operator.add, ast.Sub: operator.sub,
            ast.Mult: operator.mul, ast.Div: operator.truediv,
            ast.Pow: operator.pow, ast.USub: operator.neg,
        }
        def _safe_eval(node):
            if isinstance(node, ast.Expression):
                return _safe_eval(node.body)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return float(node.value)
            if isinstance(node, ast.BinOp) and type(node.op) in _ops:
                return _ops[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
            if isinstance(node, ast.UnaryOp) and type(node.op) in _ops:
                return _ops[type(node.op)](_safe_eval(node.operand))
            raise ValueError(f"허용되지 않는 표현식: {ast.dump(node)}")
        try:
            tree = ast.parse(expr.strip(), mode="eval")
            return float(_safe_eval(tree))
        except Exception:
            return 0.0

    def _collect_params(self) -> ObsParams:
        """UI에서 ObsParams를 수집한다."""
        checked = self.obs_type_group.checkedButton()
        obs_type = checked.property("obs_type") if checked else "SOU"

        return ObsParams(
            sample_rate=self._eval_expr(self.txt_sample_rate.text()),
            center_freq=self._eval_expr(self.txt_center_freq.text()),
            gain=self.spin_gain.value(),
            nfft=int(self.spin_nfft.currentText()),
            iterations=self.spin_iterations.value(),
            samples_per_scan=int(self._eval_expr(self.txt_samples_per_scan.text())),
            use_bias_tee=self.chk_bias_tee.isChecked(),
            remove_dc=self.chk_remove_dc.isChecked(),
            use_hanning=self.chk_hanning.isChecked(),
            obs_type=obs_type,
            site_name=self.combo_site.currentText(),
            lat=self.spin_lat.value(),
            lon=self.spin_lon.value(),
            height=self.spin_height.value(),
            timezone=self.combo_tz.currentText(),
            alt_deg=self.spin_alt.value() if self.chk_alt_az.isChecked() else None,
            az_deg=self.spin_az.value() if self.chk_alt_az.isChecked() else None,
            note=self.txt_obs_name.text(),
            save_dir=self.txt_save_dir.text(),
        )

    @Slot()
    def _on_start_observation(self):
        params = self._collect_params()

        if params.sample_rate <= 0 or params.center_freq <= 0:
            QMessageBox.warning(self, "파라미터 오류", "Sample Rate와 Center Freq를 확인하세요.")
            return

        self.btn_start.setEnabled(False)
        self.btn_start.setText("관측 중...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, params.iterations)
        self.progress_bar.setValue(0)

        integ_sec = (params.samples_per_scan * params.iterations) / params.sample_rate if params.sample_rate > 0 else 0
        self._log(f"관측 시작: {params.obs_type} | Gain={params.gain}dB | "
                  f"Iter={params.iterations} | NFFT={params.nfft} | "
                  f"적분시간={integ_sec:.0f}초")

        self._worker = ObservationWorker(self.sdr, params)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_obs_finished)
        self._worker.error.connect(self._on_obs_error)
        self._worker.start()

    @Slot(int, int)
    def _on_progress(self, current: int, total: int):
        self.progress_bar.setValue(current)

    @Slot(dict)
    def _on_obs_finished(self, result: dict):
        import numpy as np
        from src.models.observation import Observation

        self.btn_start.setEnabled(True)
        self.btn_start.setText("★  관측 시작  ★")
        self.progress_bar.setVisible(False)

        folder = result["folder"]
        self._log(f"관측 완료: {folder}")

        # 프리뷰 플롯
        obs = Observation(
            obs_id=folder.name,
            path=folder,
            fits_path=result["fits_path"],
            freq_mhz=result["freq_axis"],
            psd_db=result["raw_psd_db"],
            header=result["header"],
            is_loaded=True,
        )
        self.preview_plot.plot_observation(obs)
        self.observation_completed.emit(str(folder))

    @Slot(str)
    def _on_obs_error(self, msg: str):
        self.btn_start.setEnabled(True)
        self.btn_start.setText("★  관측 시작  ★")
        self.progress_bar.setVisible(False)
        self._log(f"[ERROR] {msg}")
        QMessageBox.critical(self, "관측 오류", msg)

    def _log(self, msg: str):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self.txt_log.append(f"[{ts}] {msg}")

    def initialize(self):
        """탭 초기화 시 SDR 상태 확인"""
        self.sdr.check_connection()
        self._update_integration_time()
