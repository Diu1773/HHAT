"""Step 9: HI 선 검출 (피크 후보 찾기)

혼 안테나 + RTL-SDR 환경에 맞춤:
  - DC spike (중심 주파수) 자동 제외
  - 노이즈 추정은 양 끝 line-free 영역에서 수행
  - HI 선 검색 영역 제한 옵션
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import find_peaks


@dataclass
class PeakCandidate:
    index: int
    position: float    # x축 값 (MHz 또는 km/s)
    amplitude: float   # 피크 높이 (baseline 위)
    width: float       # 추정 폭 (x축 단위)
    snr: float         # 신호 대 잡음비


def detect_peaks(
    x: np.ndarray,
    y: np.ndarray,
    snr_threshold: float = 3.0,
    min_width: int = 3,
    prominence: float = None,
    exclude_center_frac: float = 0.02,
    noise_edge_frac: float = 0.25,
) -> list[PeakCandidate]:
    """자동 피크 탐지.

    Args:
        x: 주파수(MHz) 또는 속도(km/s) 축
        y: 스펙트럼 값
        snr_threshold: 최소 SNR
        min_width: 최소 피크 폭 (채널 수)
        prominence: scipy prominence 파라미터 (None이면 자동)
        exclude_center_frac: 중심 주파수 근처 제외 비율 (DC spike 방지, 0이면 미제외)
        noise_edge_frac: 노이즈 추정에 사용할 양 끝 비율
    """
    if len(y) == 0:
        return []

    n = min(len(x), len(y))
    if n < 10:
        return []
    x = np.asarray(x[:n], dtype=float)
    y = np.asarray(y[:n], dtype=float)

    # NaN/Inf 제거
    finite_mask = np.isfinite(x) & np.isfinite(y)
    if np.count_nonzero(finite_mask) < 10:
        return []
    valid_indices = np.flatnonzero(finite_mask)
    x_valid = x[finite_mask]
    y_valid = y[finite_mask]

    n_valid = len(x_valid)

    # --- DC spike 제외 마스크 ---
    # RTL-SDR은 중심 주파수에 DC spike가 발생함
    dc_mask = np.ones(n_valid, dtype=bool)
    if exclude_center_frac > 0:
        center = n_valid // 2
        half_exclude = max(1, int(n_valid * exclude_center_frac / 2))
        dc_mask[max(0, center - half_exclude):min(n_valid, center + half_exclude + 1)] = False

    # --- 노이즈 추정 (양 끝 line-free 영역) ---
    edge = max(5, int(n_valid * noise_edge_frac))
    edge_mask = np.zeros(n_valid, dtype=bool)
    edge_mask[:edge] = True
    edge_mask[-edge:] = True
    # edge에서도 DC spike 제외
    noise_mask = edge_mask & dc_mask
    if np.count_nonzero(noise_mask) < 5:
        noise_mask = dc_mask  # fallback: DC 제외한 전체

    noise_data = y_valid[noise_mask]
    median_y = float(np.median(noise_data))
    mad = float(np.median(np.abs(noise_data - median_y)))
    noise = mad * 1.4826 if mad > 0 else float(np.std(noise_data))

    if not np.isfinite(noise) or noise <= 0:
        return []

    if prominence is None:
        prominence = snr_threshold * noise

    # --- find_peaks (DC spike 영역 제외) ---
    # DC spike 영역의 y값을 median으로 대체하여 검출에서 제외
    y_for_peaks = y_valid.copy()
    if exclude_center_frac > 0:
        y_for_peaks[~dc_mask] = median_y

    indices, properties = find_peaks(
        y_for_peaks,
        prominence=prominence,
        width=min_width,
        rel_height=0.5,
    )

    # DC spike 영역에 있는 피크 제거
    valid_peak_mask = dc_mask[indices] if len(indices) > 0 else np.array([], dtype=bool)
    indices = indices[valid_peak_mask]
    for key in properties:
        properties[key] = properties[key][valid_peak_mask]

    candidates = []
    dx = float(np.median(np.abs(np.diff(x_valid)))) if len(x_valid) > 1 else 1.0

    for i, idx in enumerate(indices):
        amp = float(y_valid[idx] - median_y)
        snr = amp / noise if noise > 0 else 0
        width_channels = properties["widths"][i] if "widths" in properties else float(min_width)
        original_idx = int(valid_indices[idx])
        width_x = float(width_channels) * dx

        candidates.append(PeakCandidate(
            index=original_idx,
            position=float(x[original_idx]),
            amplitude=amp,
            width=width_x,
            snr=float(snr),
        ))

    candidates.sort(key=lambda p: p.snr, reverse=True)
    return candidates
