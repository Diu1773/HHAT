"""Step 8: LSR 보정 및 좌표 변환 (선택)"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import numpy as np


def altaz_to_radec(
    alt_deg: float,
    az_deg: float,
    lat_deg: float,
    lon_deg: float,
    height_m: float,
    obstime: datetime,
) -> Optional[tuple[float, float]]:
    """Alt/Az → RA/Dec 변환 (astropy 사용)"""
    try:
        from astropy.coordinates import EarthLocation, AltAz, SkyCoord
        from astropy.time import Time
        import astropy.units as u

        location = EarthLocation(
            lat=lat_deg * u.deg,
            lon=lon_deg * u.deg,
            height=height_m * u.m,
        )
        t = Time(obstime, scale="utc")
        altaz_frame = AltAz(obstime=t, location=location)
        coord = SkyCoord(alt=alt_deg * u.deg, az=az_deg * u.deg, frame=altaz_frame)
        icrs = coord.icrs
        return (icrs.ra.deg, icrs.dec.deg)
    except Exception:
        return None


def radec_to_galactic(
    ra_deg: float, dec_deg: float,
) -> Optional[tuple[float, float]]:
    """RA/Dec → Galactic (l, b)"""
    try:
        from astropy.coordinates import SkyCoord
        import astropy.units as u

        coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")
        gal = coord.galactic
        return (gal.l.deg, gal.b.deg)
    except Exception:
        return None


def compute_lsr_correction(
    ra_deg: float,
    dec_deg: float,
    obstime: datetime,
    lat_deg: float,
    lon_deg: float,
    height_m: float,
) -> Optional[float]:
    """LSR 보정 속도 (km/s)를 계산한다.

    V_LSR = V_observed + v_correction
    보정값 = (지구자전 + 공전) + 태양 고유운동 투영

    Returns:
        v_lsr_correction (km/s) 또는 실패 시 None
    """
    try:
        from astropy.coordinates import EarthLocation, SkyCoord, Galactocentric
        from astropy.time import Time
        import astropy.units as u

        location = EarthLocation(
            lat=lat_deg * u.deg,
            lon=lon_deg * u.deg,
            height=height_m * u.m,
        )
        t = Time(obstime, scale="utc")
        coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")

        # 1) 관측자 → 태양중심 (지구 자전 + 공전)
        v_bary = coord.radial_velocity_correction(
            kind="barycentric", obstime=t, location=location
        ).to(u.km / u.s).value

        # 2) 태양 → LSR (태양 고유운동)
        # Standard Solar Motion: 20.0 km/s toward (RA=18h, Dec=+30°) [1900 epoch]
        # astropy의 LSR 프레임 변환 사용
        try:
            from astropy.coordinates import LSR
            # ICRS에서 LSR로 변환 시 필요한 radial velocity=0 설정
            coord_with_rv = SkyCoord(
                ra=ra_deg * u.deg, dec=dec_deg * u.deg,
                frame="icrs",
                radial_velocity=0 * u.km / u.s,
                distance=1 * u.kpc,  # 형식적 거리 (방향만 중요)
            )
            coord_lsr = coord_with_rv.transform_to(LSR())
            # LSR 프레임에서의 radial velocity = -(태양→LSR 투영 속도)
            v_solar_lsr = -coord_lsr.radial_velocity.to(u.km / u.s).value
        except Exception:
            # fallback: Standard Solar Motion 직접 계산
            # V_sun = 20.0 km/s toward (RA=18h=270°, Dec=+30°)
            ra_apex = np.deg2rad(270.0)  # 18h
            dec_apex = np.deg2rad(30.0)
            ra_src = np.deg2rad(ra_deg)
            dec_src = np.deg2rad(dec_deg)
            # 두 방향 사이 각도의 cos → 시선 방향 투영
            cos_angle = (
                np.sin(dec_src) * np.sin(dec_apex)
                + np.cos(dec_src) * np.cos(dec_apex) * np.cos(ra_src - ra_apex)
            )
            v_solar_lsr = 20.0 * cos_angle

        return float(v_bary + v_solar_lsr)
    except Exception:
        return None
