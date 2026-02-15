"""관측 데이터 모델"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np


class ObsType(enum.Enum):
    SOU = "SOU"
    AMB = "AMB"
    SKY = "SKY"
    UNKNOWN = "UNKNOWN"


class QCStatus(enum.Enum):
    OK = "OK"
    WARN = "WARN"
    BAD = "BAD"
    UNCHECKED = "UNCHECKED"


@dataclass
class QCResult:
    status: QCStatus = QCStatus.UNCHECKED
    rms_total: float = 0.0
    rms_center: float = 0.0
    spike_count: int = 0
    nan_count: int = 0
    inf_count: int = 0
    mean_level_db: float = 0.0
    messages: list[str] = field(default_factory=list)


@dataclass
class FitComponent:
    """가우시안 피팅 단일 성분"""
    amplitude: float = 0.0
    center: float = 0.0      # km/s 또는 MHz
    sigma: float = 0.0
    fwhm: float = 0.0
    model: str = "gaussian"
    shape: float = 0.0       # skewed_gaussian: alpha, voigt: gamma


@dataclass
class FitResult:
    components: list[FitComponent] = field(default_factory=list)
    residual_rms: float = 0.0
    success: bool = False
    message: str = ""
    model: str = "gaussian"
    x_unit: str = ""  # "km/s" | "MHz" | ""
    baseline_offset: float = 0.0  # y = offset + slope * (x - baseline_x_ref)
    baseline_slope: float = 0.0
    baseline_x_ref: float = 0.0


@dataclass
class Observation:
    """단일 관측 데이터 컨테이너"""

    # 식별
    obs_id: str = ""
    path: Path = field(default_factory=Path)
    fits_path: Path = field(default_factory=Path)

    # 원시 데이터
    freq_mhz: Optional[np.ndarray] = field(default=None, repr=False)
    psd_db: Optional[np.ndarray] = field(default=None, repr=False)

    # FITS 헤더 정보
    header: dict = field(default_factory=dict)

    # 분류
    obs_type: ObsType = ObsType.UNKNOWN

    # 메타데이터 (사용자 입력 + 헤더)
    metadata: dict = field(default_factory=dict)

    # 처리 결과 (단계별로 채워짐)
    psd_db_clean: Optional[np.ndarray] = field(default=None, repr=False)
    mask_rfi: Optional[np.ndarray] = field(default=None, repr=False)
    psd_db_baseline_removed: Optional[np.ndarray] = field(default=None, repr=False)
    vel_kms: Optional[np.ndarray] = field(default=None, repr=False)

    # Y-factor 교정 결과
    antenna_temp_k: Optional[np.ndarray] = field(default=None, repr=False)

    # QC
    qc: QCResult = field(default_factory=QCResult)

    # 피팅
    fit_result: Optional[FitResult] = None

    # 상태 플래그
    is_loaded: bool = False
    is_preprocessed: bool = False
    is_baseline_removed: bool = False
    is_velocity_converted: bool = False
    is_calibrated: bool = False

    @property
    def display_name(self) -> str:
        """리스트 표시용 이름"""
        return self.obs_id or self.path.name

    @property
    def date_obs(self) -> str:
        return self.header.get("DATE-OBS", "N/A")

    @property
    def nfft(self) -> int:
        if self.freq_mhz is not None:
            return len(self.freq_mhz)
        return self.header.get("NFFT", 0)
