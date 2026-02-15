"""Step 5: RFI/스파이크 마스킹 + 스무딩"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import savgol_filter


def detect_spikes(psd_db: np.ndarray, zscore_thresh: float = 5.0) -> np.ndarray:
    """Robust z-score 기반 스파이크 마스크 생성.

    Returns:
        bool 배열 (True = 스파이크)
    """
    median = np.median(psd_db)
    mad = np.median(np.abs(psd_db - median))
    if mad == 0:
        return np.zeros(len(psd_db), dtype=bool)
    z = np.abs(psd_db - median) / (mad * 1.4826)
    return z > zscore_thresh


def mask_rfi(
    psd_db: np.ndarray,
    zscore_thresh: float = 5.0,
    median_kernel: int = 5,
) -> tuple[np.ndarray, np.ndarray]:
    """RFI 마스킹: 스파이크를 median 값으로 대체.

    Returns:
        (cleaned_psd, mask) - mask는 True가 마스킹된 부분
    """
    mask = detect_spikes(psd_db, zscore_thresh)
    cleaned = psd_db.copy()
    if np.any(mask):
        med_filtered = median_filter(psd_db, size=median_kernel)
        cleaned[mask] = med_filtered[mask]
    return cleaned, mask


def smooth_savgol(
    psd_db: np.ndarray,
    window_length: int = 11,
    polyorder: int = 3,
) -> np.ndarray:
    """Savitzky-Golay 스무딩"""
    wl = min(window_length, len(psd_db))
    if wl % 2 == 0:
        wl -= 1
    if wl < polyorder + 2:
        return psd_db.copy()
    return savgol_filter(psd_db, wl, polyorder)


def smooth_gaussian(
    psd_db: np.ndarray,
    sigma: float = 3.0,
) -> np.ndarray:
    """가우시안 커널 스무딩"""
    from scipy.ndimage import gaussian_filter1d
    return gaussian_filter1d(psd_db, sigma=sigma)


def preprocess(
    psd_db: np.ndarray,
    rfi_zscore: float = 5.0,
    rfi_median_kernel: int = 5,
    smooth_method: str = "savgol",
    smooth_param: int = 11,
) -> tuple[np.ndarray, np.ndarray]:
    """전처리 파이프라인: RFI 마스킹 → 스무딩

    Returns:
        (cleaned_smoothed_psd, rfi_mask)
    """
    cleaned, mask = mask_rfi(psd_db, rfi_zscore, rfi_median_kernel)

    if smooth_method == "savgol":
        result = smooth_savgol(cleaned, window_length=smooth_param)
    elif smooth_method == "gaussian":
        result = smooth_gaussian(cleaned, sigma=max(1.0, smooth_param / 3.0))
    else:
        result = cleaned

    return result, mask
