"""Step 8: LSR 보정 및 좌표 변환 (가능한 경우에만)"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGroupBox, QFormLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QHeaderView,
)
from PySide6.QtGui import QColor

from src.analysis.step_base import StepBase
from src.core.lsr import altaz_to_radec, radec_to_galactic, compute_lsr_correction
from src.core.cache import save_cache
from src.models.project_state import ProjectState


class Step8LSRCorrection(StepBase):
    """LSR 보정 및 좌표 변환 — 메타 누락 시 스킵 가능"""

    def __init__(self, project_state: ProjectState, parent=None):
        super().__init__(
            step_index=7,
            step_name="LSR 보정 / 좌표 변환",
            step_description=(
                "관측지, 관측시각, 포인팅(alt/az) 정보가 있는 경우에만 "
                "LSR 보정과 galactic 좌표 변환을 수행합니다. "
                "메타 누락 시 건너뛸 수 있습니다."
            ),
            project_state=project_state,
            parent=parent,
        )

    def setup_ui(self):
        self.btn_compute = QPushButton("LSR 보정 계산")
        self.btn_compute.setStyleSheet(
            "QPushButton { background: #5c6bc0; color: white; font-weight: bold; padding: 8px; }"
        )
        self.btn_compute.clicked.connect(self._on_compute)
        self.content_layout.addWidget(self.btn_compute)

        self.lbl_info = QLabel("메타데이터가 완비된 관측만 보정됩니다.")
        self.lbl_info.setStyleSheet("color: #888; font-size: 11px; padding: 4px;")
        self.content_layout.addWidget(self.lbl_info)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([
            "관측 ID", "RA (°)", "Dec (°)", "l (°)", "b (°)",
            "V_LSR (km/s)", "상태",
        ])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setStyleSheet("""
            QTreeWidget { background: #1e1e2e; color: white; border: 1px solid #444;
                          alternate-background-color: #252540; }
            QHeaderView::section { background: #2a2a3e; color: white;
                                   border: 1px solid #444; padding: 4px; }
        """)
        self.content_layout.addWidget(self.tree, stretch=1)

    def on_enter(self):
        super().on_enter()
        self._refresh_table()

    def _on_compute(self):
        from src.models.observation import ObsType
        for obs in self._observations:
            # AMB 관측은 포인팅 정보가 불필요 — 건너뛴다
            if obs.obs_type == ObsType.AMB:
                obs.metadata["lsr_status"] = "AMB — 해당 없음"
                continue

            meta = obs.metadata
            lat = meta.get("lat", 0)
            lon = meta.get("lon", 0)
            height = meta.get("height", 0)
            alt_deg = meta.get("alt_deg")
            az_deg = meta.get("az_deg")

            # 시각 파싱
            date_obs = obs.header.get("DATE-OBS", "")
            try:
                obstime = datetime.fromisoformat(str(date_obs))
            except (ValueError, TypeError):
                obs.metadata["lsr_status"] = "시각 누락"
                continue

            # 위치 검증
            if lat is None and lon is None:
                obs.metadata["lsr_status"] = "관측지 누락"
                continue

            # Alt/Az → RA/Dec
            if alt_deg is not None and az_deg is not None:
                result = altaz_to_radec(alt_deg, az_deg, lat, lon, height, obstime)
                if result:
                    obs.metadata["ra_deg"], obs.metadata["dec_deg"] = result
                else:
                    obs.metadata["lsr_status"] = "좌표 변환 실패"
                    continue
            elif "ra_deg" not in obs.metadata:
                obs.metadata["lsr_status"] = "포인팅 누락"
                continue

            ra = obs.metadata.get("ra_deg", 0)
            dec = obs.metadata.get("dec_deg", 0)

            # Galactic
            gal = radec_to_galactic(ra, dec)
            if gal:
                obs.metadata["gal_l"], obs.metadata["gal_b"] = gal

            # LSR
            v_lsr = compute_lsr_correction(ra, dec, obstime, lat, lon, height)
            if v_lsr is not None:
                obs.metadata["v_lsr_correction"] = v_lsr
                # 속도축에 LSR 보정 적용 (중복 적용 방지)
                if obs.vel_kms is not None and not obs.metadata.get("lsr_applied"):
                    import numpy as np
                    vel = np.asarray(obs.vel_kms, dtype=float)
                    obs.vel_kms = np.where(np.isfinite(vel), vel - v_lsr, vel)
                    obs.metadata["lsr_applied"] = True
                    obs.metadata["lsr_status"] = "완료 (적용됨)"
                elif obs.metadata.get("lsr_applied"):
                    obs.metadata["lsr_status"] = "완료 (이미 적용됨)"
                else:
                    obs.metadata["lsr_applied"] = False
                    obs.metadata["lsr_status"] = "완료 (속도축 없음 — Step 7 먼저)"
                save_cache(obs)
            else:
                obs.metadata["lsr_status"] = "LSR 계산 실패"

        self._refresh_table()

    def _refresh_table(self):
        self.tree.clear()
        for obs in self._observations:
            m = obs.metadata
            status = m.get("lsr_status", "미처리")
            if "해당 없음" in status:
                color = QColor("#888888")
            elif "완료" in status:
                color = QColor("#4caf50")
            else:
                color = QColor("#ff9800")

            item = QTreeWidgetItem([
                obs.display_name,
                f"{m.get('ra_deg', ''):.4f}" if m.get("ra_deg") else "-",
                f"{m.get('dec_deg', ''):.4f}" if m.get("dec_deg") else "-",
                f"{m.get('gal_l', ''):.2f}" if m.get("gal_l") else "-",
                f"{m.get('gal_b', ''):.2f}" if m.get("gal_b") else "-",
                f"{m.get('v_lsr_correction', ''):.2f}" if m.get("v_lsr_correction") else "-",
                status,
            ])
            item.setForeground(6, color)
            self.tree.addTopLevelItem(item)

    def validate_step(self) -> bool:
        # LSR은 선택이므로 항상 통과
        return True
