"""Y-factor 교정

SOU(천체)와 AMB(흡수체) 관측 쌍을 이용하여 수신기 이득 G(f)를 상쇄하고
안테나 온도(K)를 구한다.

물리:
    P_sou(f) = G(f) × (T_sou(f) + T_sys)
    P_amb(f) = G(f) × (T_amb + T_sys)

    R(f) = P_sou(f) / P_amb(f)   (비율 → G(f) 상쇄)

    line-free 대역에서 R_0 = median(R) — 이때 T_sou ≈ T_sky ≈ 0
    → T_sys = R_0 × T_amb / (1 - R_0)

    안테나 온도:
    T*_A(f) = T_amb × (R(f) - R_0) / (1 - R_0)

정상적인 혼 안테나 관측에서는 R_0 < 1 (하늘이 흡수체보다 차가움).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class YFactorResult:
    """Y-factor 교정 결과"""
    antenna_temp_k: np.ndarray   # 안테나 온도 스펙트럼 (K)
    t_sys_k: float               # 시스템 온도 (K)
    r_median: float              # R_0 (line-free P_sou/P_amb 비율)
    success: bool = True
    message: str = ""


def yfactor_calibrate(
    psd_sou_db: np.ndarray,
    psd_amb_db: np.ndarray,
    t_amb_k: float,
    line_free_frac: float = 0.25,
) -> YFactorResult:
    """Y-factor 교정을 수행한다.

    Args:
        psd_sou_db: SOU(천체) 관측 PSD (dB)
        psd_amb_db: AMB(흡수체) 관측 PSD (dB)
        t_amb_k: 흡수체 물리 온도 (K)
        line_free_frac: 양 끝에서 line-free로 간주할 비율 (기본 25%)

    Returns:
        YFactorResult
    """
    if t_amb_k <= 0:
        return YFactorResult(
            antenna_temp_k=np.array([]),
            t_sys_k=0.0, r_median=0.0,
            success=False,
            message=f"T_amb={t_amb_k:.1f} K: 0 이하는 불가능합니다.",
        )

    if len(psd_sou_db) != len(psd_amb_db):
        return YFactorResult(
            antenna_temp_k=np.array([]),
            t_sys_k=0.0, r_median=0.0,
            success=False,
            message=f"NFFT 불일치: SOU={len(psd_sou_db)}, AMB={len(psd_amb_db)}",
        )

    n = len(psd_sou_db)
    if n < 10:
        return YFactorResult(
            antenna_temp_k=np.array([]),
            t_sys_k=0.0, r_median=0.0,
            success=False,
            message="데이터 포인트가 너무 적습니다.",
        )

    # dB → linear power
    p_sou = 10.0 ** (np.asarray(psd_sou_db, dtype=float) / 10.0)
    p_amb = 10.0 ** (np.asarray(psd_amb_db, dtype=float) / 10.0)

    # 0 방지
    p_sou = np.maximum(p_sou, 1e-30)
    p_amb = np.maximum(p_amb, 1e-30)

    # 주파수별 비율 — G(f) 상쇄
    R = p_sou / p_amb

    # line-free 마스크 (양 끝)
    edge = max(1, int(n * line_free_frac))
    mask = np.zeros(n, dtype=bool)
    mask[:edge] = True
    mask[-edge:] = True

    R_0 = float(np.median(R[mask]))

    # 검증
    if R_0 <= 0 or R_0 >= 1.0 - 1e-6:
        # R_0 ≈ 1이면 AMB와 SOU가 거의 같음 → 교정 불가
        # R_0 > 1이면 SOU가 AMB보다 강함 → 비정상 (흡수체가 하늘보다 차가울 수 없음)
        if R_0 >= 1.0:
            return YFactorResult(
                antenna_temp_k=np.zeros(n),
                t_sys_k=0.0, r_median=R_0,
                success=False,
                message=(
                    f"R_0={R_0:.4f} ≥ 1: SOU 신호 ≥ AMB 신호.\n"
                    "흡수체가 하늘보다 차갑거나, SOU/AMB가 뒤바뀌었을 수 있습니다."
                ),
            )
        return YFactorResult(
            antenna_temp_k=np.zeros(n),
            t_sys_k=0.0, r_median=R_0,
            success=False,
            message=f"R_0={R_0:.4f}: 비율이 비정상입니다.",
        )

    # 시스템 온도: T_sys = R_0 × T_amb / (1 - R_0)
    t_sys = R_0 * t_amb_k / (1.0 - R_0)

    # 안테나 온도: T*_A(f) = T_amb × (R(f) - R_0) / (1 - R_0)
    t_ant = t_amb_k * (R - R_0) / (1.0 - R_0)

    # NaN/Inf 처리
    t_ant = np.where(np.isfinite(t_ant), t_ant, 0.0)

    return YFactorResult(
        antenna_temp_k=t_ant,
        t_sys_k=t_sys,
        r_median=R_0,
        success=True,
        message=f"R_0={R_0:.4f}, T_sys={t_sys:.0f} K",
    )
