"""Step 3: 메타데이터 입력/편집 패널

관측 타입별 다른 필드를 표시한다:
  SOU/SKY: alt/az (포인팅 방향)
  AMB:     T_amb (흡수체 온도, Y-factor 교정용)
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QPushButton, QLabel, QGroupBox,
    QDoubleSpinBox, QTextEdit,
)

from src.models.observation import Observation, ObsType
from src.utils.constants import SITE_PRESETS


class MetadataPanel(QWidget):
    """메타데이터 편집 패널"""

    meta_saved = Signal(dict)      # 저장된 메타 dict
    type_changed = Signal(str)     # 새 관측 타입

    def __init__(self, parent=None):
        super().__init__(parent)
        self._obs: Observation | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # --- 관측 타입 ---
        type_group = QGroupBox("관측 타입")
        type_layout = QHBoxLayout(type_group)
        self.combo_type = QComboBox()
        self.combo_type.addItems(["SOU", "AMB", "SKY", "UNKNOWN"])
        self.combo_type.currentTextChanged.connect(self._on_type_changed)
        type_layout.addWidget(QLabel("Type:"))
        type_layout.addWidget(self.combo_type)
        layout.addWidget(type_group)

        # --- FITS 헤더 정보 (읽기 전용) ---
        header_group = QGroupBox("FITS 헤더")
        header_layout = QFormLayout(header_group)
        self.lbl_date = QLabel("-")
        self.lbl_freq_cen = QLabel("-")
        self.lbl_samprate = QLabel("-")
        self.lbl_gain = QLabel("-")
        self.lbl_nfft = QLabel("-")
        header_layout.addRow("DATE-OBS:", self.lbl_date)
        header_layout.addRow("FREQ-CEN:", self.lbl_freq_cen)
        header_layout.addRow("SAMPRATE:", self.lbl_samprate)
        header_layout.addRow("GAIN:", self.lbl_gain)
        header_layout.addRow("NFFT:", self.lbl_nfft)
        layout.addWidget(header_group)

        # --- 관측지 ---
        site_group = QGroupBox("관측지")
        site_layout = QFormLayout(site_group)

        self.combo_preset = QComboBox()
        self.combo_preset.addItems(list(SITE_PRESETS.keys()))
        self.combo_preset.currentTextChanged.connect(self._on_preset_changed)
        site_layout.addRow("프리셋:", self.combo_preset)

        self.spin_lat = QDoubleSpinBox()
        self.spin_lat.setRange(-90, 90)
        self.spin_lat.setDecimals(6)
        site_layout.addRow("위도 (°):", self.spin_lat)

        self.spin_lon = QDoubleSpinBox()
        self.spin_lon.setRange(-180, 180)
        self.spin_lon.setDecimals(6)
        site_layout.addRow("경도 (°):", self.spin_lon)

        self.spin_height = QDoubleSpinBox()
        self.spin_height.setRange(0, 9000)
        self.spin_height.setDecimals(1)
        self.spin_height.setSuffix(" m")
        site_layout.addRow("고도:", self.spin_height)

        layout.addWidget(site_group)

        # --- 포인팅 (SOU/SKY 전용) ---
        self.pointing_group = QGroupBox("포인팅 (SOU/SKY)")
        pointing_layout = QFormLayout(self.pointing_group)

        self.combo_tz = QComboBox()
        self.combo_tz.addItems(["KST", "UTC"])
        pointing_layout.addRow("시간대:", self.combo_tz)

        self.spin_alt = QDoubleSpinBox()
        self.spin_alt.setRange(-1, 90)
        self.spin_alt.setDecimals(2)
        self.spin_alt.setSuffix(" °")
        self.spin_alt.setSpecialValueText("미입력")
        self.spin_alt.setValue(-1)
        pointing_layout.addRow("Alt:", self.spin_alt)

        self.spin_az = QDoubleSpinBox()
        self.spin_az.setRange(-1, 360)
        self.spin_az.setDecimals(2)
        self.spin_az.setSuffix(" °")
        self.spin_az.setSpecialValueText("미입력")
        self.spin_az.setValue(-1)
        pointing_layout.addRow("Az:", self.spin_az)

        layout.addWidget(self.pointing_group)

        # --- AMB 교정 (AMB 전용) ---
        self.amb_group = QGroupBox("AMB 교정 파라미터")
        amb_layout = QFormLayout(self.amb_group)

        amb_desc = QLabel(
            "흡수체(상온 물체)의 물리적 온도를 입력하세요.\n"
            "Y-factor 교정: T_sys = (T_amb - Y·T_sky) / (Y - 1)"
        )
        amb_desc.setStyleSheet("color: #ff9800; font-size: 10px;")
        amb_desc.setWordWrap(True)
        amb_layout.addRow(amb_desc)

        self.spin_t_amb = QDoubleSpinBox()
        self.spin_t_amb.setRange(100, 400)
        self.spin_t_amb.setDecimals(1)
        self.spin_t_amb.setValue(295.0)
        self.spin_t_amb.setSuffix(" K")
        amb_layout.addRow("T_amb (흡수체 온도):", self.spin_t_amb)

        self.txt_amb_material = QLineEdit()
        self.txt_amb_material.setPlaceholderText("예: Eccosorb, 스티로폼+알루미늄")
        amb_layout.addRow("흡수체 재질:", self.txt_amb_material)

        self.amb_group.setVisible(False)  # 기본 숨김
        layout.addWidget(self.amb_group)

        # --- 메모 ---
        self.txt_note = QTextEdit()
        self.txt_note.setMaximumHeight(60)
        self.txt_note.setPlaceholderText("메모 (선택)")
        layout.addWidget(self.txt_note)

        # --- 저장 버튼 ---
        self.btn_save = QPushButton("메타 저장 (meta.json)")
        self.btn_save.setStyleSheet(
            "QPushButton { background: #4caf50; color: white; padding: 8px; "
            "border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background: #45a049; }"
        )
        self.btn_save.clicked.connect(self._on_save)
        layout.addWidget(self.btn_save)

        layout.addStretch()

    def _on_type_changed(self, type_str: str):
        """타입에 따라 포인팅/AMB 그룹 표시를 전환한다."""
        is_amb = (type_str == "AMB")
        self.pointing_group.setVisible(not is_amb)
        self.amb_group.setVisible(is_amb)
        self.type_changed.emit(type_str)

    def _on_preset_changed(self, name: str):
        if name in SITE_PRESETS:
            preset = SITE_PRESETS[name]
            self.spin_lat.setValue(preset["lat"])
            self.spin_lon.setValue(preset["lon"])
            self.spin_height.setValue(preset["height"])

    def load_observation(self, obs: Observation):
        """관측 데이터를 패널에 로드한다."""
        self._obs = obs

        # 관측 전환 시 기본값 초기화
        idx_user = self.combo_preset.findText("사용자 지정")
        if idx_user >= 0:
            self.combo_preset.setCurrentIndex(idx_user)
        self.spin_lat.setValue(0.0)
        self.spin_lon.setValue(0.0)
        self.spin_height.setValue(0.0)
        idx_kst = self.combo_tz.findText("KST")
        if idx_kst >= 0:
            self.combo_tz.setCurrentIndex(idx_kst)
        self.spin_alt.setValue(-1.0)
        self.spin_az.setValue(-1.0)
        self.spin_t_amb.setValue(295.0)
        self.txt_amb_material.clear()
        self.txt_note.clear()

        # 타입 (이벤트로 pointing/amb 그룹 전환)
        idx = self.combo_type.findText(obs.obs_type.value)
        if idx >= 0:
            self.combo_type.setCurrentIndex(idx)

        # 헤더
        self.lbl_date.setText(str(obs.header.get("DATE-OBS", "-")))
        self.lbl_freq_cen.setText(str(obs.header.get("FREQ-CEN", "-")))
        self.lbl_samprate.setText(str(obs.header.get("SAMPRATE", "-")))
        self.lbl_gain.setText(str(obs.header.get("GAIN", "-")))
        self.lbl_nfft.setText(str(obs.header.get("NFFT", "-")))

        # 메타데이터 로드
        meta = obs.metadata
        if "site_name" in meta and meta["site_name"]:
            idx = self.combo_preset.findText(str(meta["site_name"]))
            if idx >= 0:
                self.combo_preset.setCurrentIndex(idx)
        if "lat" in meta and meta["lat"] is not None:
            self.spin_lat.setValue(float(meta["lat"]))
        if "lon" in meta and meta["lon"] is not None:
            self.spin_lon.setValue(float(meta["lon"]))
        if "height" in meta and meta["height"] is not None:
            self.spin_height.setValue(float(meta["height"]))
        if "timezone" in meta and meta["timezone"]:
            idx = self.combo_tz.findText(meta["timezone"])
            if idx >= 0:
                self.combo_tz.setCurrentIndex(idx)
        if "alt_deg" in meta and meta["alt_deg"] is not None:
            self.spin_alt.setValue(float(meta["alt_deg"]))
        if "az_deg" in meta and meta["az_deg"] is not None:
            self.spin_az.setValue(float(meta["az_deg"]))
        if "t_amb" in meta and meta["t_amb"] is not None:
            self.spin_t_amb.setValue(float(meta["t_amb"]))
        if "amb_material" in meta and meta["amb_material"]:
            self.txt_amb_material.setText(str(meta["amb_material"]))
        if "note" in meta and meta["note"] is not None:
            self.txt_note.setPlainText(str(meta["note"]))

    def _on_save(self):
        meta = self.collect_meta()
        self.meta_saved.emit(meta)

    def collect_meta(self) -> dict:
        """현재 입력값을 dict로 수집한다."""
        alt = self.spin_alt.value()
        az = self.spin_az.value()
        obs_type = self.combo_type.currentText()

        meta = {
            "site_name": self.combo_preset.currentText(),
            "lat": self.spin_lat.value(),
            "lon": self.spin_lon.value(),
            "height": self.spin_height.value(),
            "timezone": self.combo_tz.currentText(),
            "note": self.txt_note.toPlainText(),
        }

        if obs_type == "AMB":
            # AMB: 포인팅 대신 흡수체 온도
            meta["t_amb"] = self.spin_t_amb.value()
            meta["amb_material"] = self.txt_amb_material.text()
            meta["alt_deg"] = None
            meta["az_deg"] = None
        else:
            # SOU/SKY: 포인팅 정보
            meta["alt_deg"] = alt if alt >= 0 else None
            meta["az_deg"] = az if az >= 0 else None

        return meta
