"""Step 4: QC(품질 점검) 지표 계산"""

from __future__ import annotations

import numpy as np

from src.models.observation import Observation, QCResult, QCStatus
from src.utils.constants import QC_THRESHOLDS


def run_qc(obs: Observation) -> QCResult:
    """스펙트럼 품질 점검을 수행한다."""
    result = QCResult()

    if obs.psd_db is None:
        result.status = QCStatus.BAD
        result.messages.append("데이터 없음")
        return result

    psd = obs.psd_db

    # NaN / Inf 검사
    result.nan_count = int(np.isnan(psd).sum())
    result.inf_count = int(np.isinf(psd).sum())

    valid = psd[np.isfinite(psd)]
    if len(valid) == 0:
        result.status = QCStatus.BAD
        result.messages.append("유효한 데이터 없음 (전부 NaN/Inf)")
        return result

    # RMS
    result.rms_total = float(np.std(valid))
    n = len(valid)
    center_slice = valid[n // 4 : 3 * n // 4]
    result.rms_center = float(np.std(center_slice))

    # 평균 레벨
    result.mean_level_db = float(np.mean(valid))

    # 스파이크 검출 (z-score 기반)
    median = np.median(valid)
    mad = np.median(np.abs(valid - median))
    if mad > 0:
        z = np.abs(valid - median) / (mad * 1.4826)
        result.spike_count = int(np.sum(z > QC_THRESHOLDS["spike_zscore"]))
    else:
        result.spike_count = 0

    # 판정
    messages = []
    status = QCStatus.OK

    if result.nan_count > 0 or result.inf_count > 0:
        nan_ratio = (result.nan_count + result.inf_count) / len(psd)
        if nan_ratio > QC_THRESHOLDS["max_nan_ratio"]:
            status = QCStatus.BAD
            messages.append(f"NaN/Inf {result.nan_count + result.inf_count}개 ({nan_ratio:.1%})")
        else:
            if status != QCStatus.BAD:
                status = QCStatus.WARN
            messages.append(f"NaN/Inf {result.nan_count + result.inf_count}개")

    if result.mean_level_db < QC_THRESHOLDS["psd_min_db"]:
        status = QCStatus.WARN
        messages.append(f"평균 레벨 낮음 ({result.mean_level_db:.1f} dB) - 게인 부족?")

    if result.mean_level_db > QC_THRESHOLDS["psd_max_db"]:
        status = QCStatus.WARN
        messages.append(f"평균 레벨 높음 ({result.mean_level_db:.1f} dB) - 게인 과다?")

    if result.spike_count > 10:
        if status != QCStatus.BAD:
            status = QCStatus.WARN
        messages.append(f"스파이크 {result.spike_count}개 검출 - RFI 마스킹 권장")

    if not messages:
        messages.append("정상")

    result.status = status
    result.messages = messages
    return result
