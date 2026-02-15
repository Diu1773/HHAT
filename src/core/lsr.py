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

    Returns:
        v_lsr_correction (km/s) 또는 실패 시 None
    """
    try:
        from astropy.coordinates import EarthLocation, SkyCoord
        from astropy.time import Time
        import astropy.units as u

        location = EarthLocation(
            lat=lat_deg * u.deg,
            lon=lon_deg * u.deg,
            height=height_m * u.m,
        )
        t = Time(obstime, scale="utc")
        coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")

        # 관측자의 barycentric 속도 → LSR 보정
        v_bary = coord.radial_velocity_correction(
            kind="barycentric", obstime=t, location=location
        )
        return v_bary.to(u.km / u.s).value
    except Exception:
        return None
