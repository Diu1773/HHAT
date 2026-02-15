"""Step 11: 물리량 환산 (선택)"""

from __future__ import annotations

import numpy as np
from scipy.special import wofz

from src.models.observation import FitComponent


def integrated_intensity(
    vel_kms: np.ndarray,
    spectrum: np.ndarray,
) -> float:
    """적분 강도 ∫T(v)dv (K·km/s 또는 상대 단위)"""
    if len(vel_kms) < 2 or len(spectrum) < 2:
        return 0.0

    n = min(len(vel_kms), len(spectrum))
    x = np.asarray(vel_kms[:n], dtype=float)
    y = np.asarray(spectrum[:n], dtype=float)
    finite = np.isfinite(x) & np.isfinite(y)
    if np.count_nonzero(finite) < 2:
        return 0.0
    x = x[finite]
    y = y[finite]

    # 축 방향(증가/감소)에 따른 부호 뒤집힘을 방지하기 위해 x를 정렬 후 적분한다.
    order = np.argsort(x)
    return float(np.trapz(y[order], x[order]))


def column_density_hi(
    integrated_k_kms: float,
    optically_thin: bool = True,
) -> float:
    """N_HI 추정 (cm^-2).

    광학적으로 얇은 경우:
        N_HI = 1.823e18 * ∫T_b(v) dv  [K·km/s]
    """
    if optically_thin:
        return 1.823e18 * integrated_k_kms
    return 0.0


def component_integrated(comp: FitComponent, dv: float = 1.0) -> float:
    """단일 성분 적분값.

    - gaussian / skewed_gaussian: A * sigma * sqrt(2π)
    - voigt: peak-normalized Voigt를 수치적분
    """
    mode = (comp.model or "gaussian").lower()
    sigma = abs(float(comp.sigma))
    amp = float(comp.amplitude)

    if mode in ("gaussian", "skewed_gaussian"):
        # skewed_gaussian는 정의상 전체 적분에서 홀함수 항이 상쇄되어 gaussian과 동일
        return amp * sigma * np.sqrt(2 * np.pi)

    if mode == "voigt":
        gamma = abs(float(comp.shape))
        sigma = max(sigma, 1e-12)
        gamma = max(gamma, 1e-12)
        span = max(12.0 * sigma, 12.0 * gamma)
        x = np.linspace(-span, span, 4096)
        z = (x + 1j * gamma) / (sigma * np.sqrt(2.0))
        profile = np.real(wofz(z)) / (sigma * np.sqrt(2.0 * np.pi))
        peak = float(np.nanmax(profile)) if profile.size else 1.0
        if not np.isfinite(peak) or peak <= 0:
            peak = 1.0
        normalized = profile / peak
        return amp * float(np.trapz(normalized, x))

    # fallback
    return amp * sigma * np.sqrt(2 * np.pi)


def psd_to_temperature(
    psd_db: np.ndarray,
    t_sys: float = 150.0,
) -> np.ndarray:
    """PSD(dB) → 안테나 온도 T*_A(K) 근사 변환.

    Baseline 제거 후 dB 데이터 기준:
        P_ratio = 10^(Δ_dB/10) ≈ P(f)/P_baseline
        T*_A(f) ≈ T_sys × (P_ratio - 1)

    Line-free에서 Δ_dB ≈ 0 → P_ratio ≈ 1 → T*_A ≈ 0 (정상).
    T_B는 별도로 brightness_temperature()로 변환.

    주의: 절대 교정 없이는 상대값 중심이다.
    """
    psd_linear = 10.0 ** (np.asarray(psd_db, dtype=float) / 10.0)
    median_psd = np.median(psd_linear)
    if not np.isfinite(median_psd) or median_psd <= 0:
        return np.zeros_like(psd_db, dtype=float)
    # T*_A = T_sys × (P/P₀ - 1): line-free에서 0, HI 선에서 양수
    return t_sys * (psd_linear / median_psd - 1.0)


def brightness_temperature(
    t_ant_k: np.ndarray,
    eta: float = 0.5,
) -> np.ndarray:
    """안테나 온도 → 밝기 온도 변환.

    T_B = T*_A / η
    """
    return np.asarray(t_ant_k, dtype=float) / eta
