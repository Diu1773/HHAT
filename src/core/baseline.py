"""Step 6: Baseline(연속선) 처리"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Optional

import numpy as np

from src.core.fits_io import load_baseline_fits


def subtract_baseline_file(
    psd_db: np.ndarray,
    baseline_path: Path,
) -> Optional[np.ndarray]:
    """모드 A: 외부 baseline FITS 파일을 빼기.

    Returns:
        baseline이 제거된 psd, 실패 시 None
    """
    base = load_baseline_fits(baseline_path)
    if base is None:
        return None
    if len(base) != len(psd_db):
        return None
    return psd_db - base


def estimate_baseline_poly(
    freq: np.ndarray,
    psd_db: np.ndarray,
    line_free_ranges: list[tuple[float, float]],
    degree: int = 3,
) -> np.ndarray:
    """모드 B: line-free 구간에서 다항식으로 연속선 추정.

    Args:
        freq: 주파수 축 (MHz)
        psd_db: 스펙트럼 (dB)
        line_free_ranges: [(f_start, f_end), ...] line-free 주파수 구간
        degree: 다항식 차수

    Returns:
        baseline 모델 배열
    """
    mask = np.zeros(len(freq), dtype=bool)
    for f_start, f_end in line_free_ranges:
        mask |= (freq >= f_start) & (freq <= f_end)

    if np.sum(mask) < degree + 1:
        # 데이터 부족 시 전체로 피팅
        mask = np.ones(len(freq), dtype=bool)

    # 수치 안정성을 위해 x를 정규화한다.
    x_ref = freq[mask]
    x_mean = float(np.mean(x_ref))
    x_std = float(np.std(x_ref))
    if x_std <= 0:
        x_std = 1.0
    x = (freq - x_mean) / x_std

    # 반복 sigma-clipping으로 강한 선 성분/이상치를 완화한다.
    fit_mask = mask.copy()
    baseline = np.zeros_like(psd_db, dtype=float)
    for _ in range(4):
        if np.sum(fit_mask) < degree + 1:
            fit_mask = mask.copy()
            if np.sum(fit_mask) < degree + 1:
                break

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", np.RankWarning)
            coeffs = np.polyfit(x[fit_mask], psd_db[fit_mask], degree)
        baseline = np.polyval(coeffs, x)

        resid = psd_db - baseline
        med = float(np.median(resid[fit_mask]))
        mad = float(np.median(np.abs(resid[fit_mask] - med)))
        sigma = 1.4826 * mad if mad > 0 else float(np.std(resid[fit_mask]))
        if not np.isfinite(sigma) or sigma <= 0:
            break

        clip_mask = np.abs(resid - med) <= 3.0 * sigma
        new_fit_mask = clip_mask & mask
        if np.array_equal(new_fit_mask, fit_mask):
            break
        fit_mask = new_fit_mask
    return baseline


def remove_baseline(
    freq: np.ndarray,
    psd_db: np.ndarray,
    line_free_ranges: list[tuple[float, float]],
    degree: int = 3,
) -> tuple[np.ndarray, np.ndarray]:
    """연속선 제거 (모드 B).

    Returns:
        (baseline_removed, baseline_model)
    """
    baseline = estimate_baseline_poly(freq, psd_db, line_free_ranges, degree)
    return psd_db - baseline, baseline
