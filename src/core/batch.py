"""Step 13: 배치 처리"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from src.models.observation import Observation, ObsType
from src.core.qc import run_qc
from src.core.preprocessing import preprocess
from src.core.velocity import convert_velocity

logger = logging.getLogger(__name__)


@dataclass
class BatchConfig:
    """배치 처리 설정"""
    rfi_zscore: float = 5.0
    rfi_median_kernel: int = 5
    smooth_method: str = "savgol"
    smooth_param: int = 11
    velocity_convention: str = "radio"
    skip_unknown_type: bool = True


@dataclass
class BatchResult:
    total: int = 0
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    failed_ids: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)


def run_batch(
    observations: list[Observation],
    config: BatchConfig,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> BatchResult:
    """관측 리스트에 대해 일괄 전처리를 수행한다.

    progress_callback(current, total, message)
    """
    result = BatchResult(total=len(observations))

    for i, obs in enumerate(observations):
        msg = f"처리 중: {obs.display_name}"
        if progress_callback:
            progress_callback(i, result.total, msg)

        # 타입 미지정 건너뛰기
        if config.skip_unknown_type and obs.obs_type == ObsType.UNKNOWN:
            result.skipped += 1
            result.log.append(f"[SKIP] {obs.display_name}: 타입 미지정")
            continue

        if obs.psd_db is None:
            result.failed += 1
            result.failed_ids.append(obs.obs_id)
            result.log.append(f"[FAIL] {obs.display_name}: 데이터 없음")
            continue

        try:
            # QC
            obs.qc = run_qc(obs)

            # 전처리
            obs.psd_db_clean, obs.mask_rfi = preprocess(
                obs.psd_db,
                rfi_zscore=config.rfi_zscore,
                rfi_median_kernel=config.rfi_median_kernel,
                smooth_method=config.smooth_method,
                smooth_param=config.smooth_param,
            )
            obs.is_preprocessed = True

            # 속도 변환
            if obs.freq_mhz is not None:
                obs.vel_kms = convert_velocity(
                    obs.freq_mhz, convention=config.velocity_convention
                )
                obs.is_velocity_converted = True

            result.processed += 1
            result.log.append(f"[OK] {obs.display_name}")

        except Exception as e:
            result.failed += 1
            result.failed_ids.append(obs.obs_id)
            result.log.append(f"[FAIL] {obs.display_name}: {e}")
            logger.exception(f"배치 처리 실패: {obs.display_name}")

    if progress_callback:
        progress_callback(result.total, result.total, "완료")

    return result
