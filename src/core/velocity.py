"""Step 7: 주파수축 → 속도축 변환 (21cm 기준)"""

from __future__ import annotations

import numpy as np

from src.utils.constants import HI_REST_FREQ_MHZ, C_KMS


def freq_to_velocity_radio(
    freq_mhz: np.ndarray,
    rest_freq_mhz: float = HI_REST_FREQ_MHZ,
) -> np.ndarray:
    """Radio convention: V = c * (f0 - f) / f0

    양수 = 멀어짐 (적색편이)
    """
    return C_KMS * (rest_freq_mhz - freq_mhz) / rest_freq_mhz


def freq_to_velocity_optical(
    freq_mhz: np.ndarray,
    rest_freq_mhz: float = HI_REST_FREQ_MHZ,
) -> np.ndarray:
    """Optical convention: V = c * (f0 - f) / f"""
    freq_mhz = np.asarray(freq_mhz, dtype=float)
    safe_freq = np.where(freq_mhz == 0, np.nan, freq_mhz)
    return C_KMS * (rest_freq_mhz - safe_freq) / safe_freq


def freq_to_velocity_relativistic(
    freq_mhz: np.ndarray,
    rest_freq_mhz: float = HI_REST_FREQ_MHZ,
) -> np.ndarray:
    """Relativistic: V = c * (f0^2 - f^2) / (f0^2 + f^2)"""
    f0_sq = rest_freq_mhz ** 2
    f_sq = freq_mhz ** 2
    return C_KMS * (f0_sq - f_sq) / (f0_sq + f_sq)


def convert_velocity(
    freq_mhz: np.ndarray,
    convention: str = "radio",
    rest_freq_mhz: float = HI_REST_FREQ_MHZ,
) -> np.ndarray:
    """통합 변환 함수.

    convention: "radio" | "optical" | "relativistic"
    """
    if rest_freq_mhz <= 0:
        raise ValueError(f"rest_freq_mhz must be > 0, got {rest_freq_mhz}")
    if convention == "optical":
        return freq_to_velocity_optical(freq_mhz, rest_freq_mhz)
    elif convention == "relativistic":
        return freq_to_velocity_relativistic(freq_mhz, rest_freq_mhz)
    else:
        return freq_to_velocity_radio(freq_mhz, rest_freq_mhz)
