"""Step 1: FITS 파일 로딩 및 폴더 스캔"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import numpy as np
from astropy.io import fits

from src.models.observation import Observation, ObsType
from src.utils.constants import OBS_TYPE_KEYWORDS


def classify_obs_type(name: str) -> ObsType:
    """파일/폴더명에서 관측 타입을 추출한다."""
    for obs_type, keywords in OBS_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in name:
                return ObsType(obs_type)
    return ObsType.UNKNOWN


def _extract_obs_id(folder_name: str) -> str:
    """폴더명에서 관측 ID를 추출한다.
    예: HI_Obs_20260214_001122_SOU -> 20260214_001122
    """
    match = re.search(r"(\d{8}_\d{6})", folder_name)
    if match:
        return match.group(1)
    return folder_name


def load_fits(fits_path: Path) -> Optional[Observation]:
    """단일 FITS 파일을 읽어 Observation 객체를 생성한다.

    FITS data 구조: 2×NFFT 배열
      data[0] = freq_mhz
      data[1] = psd_db
    """
    if not fits_path.exists():
        return None

    try:
        with fits.open(str(fits_path)) as hdul:
            data = hdul[0].data
            hdr = dict(hdul[0].header)

            if data is None or data.ndim < 1:
                return None

            if data.ndim == 2 and data.shape[0] >= 2:
                freq_mhz = data[0].astype(np.float64)
                psd_db = data[1].astype(np.float64)
            elif data.ndim == 1:
                # 단일 배열인 경우 psd만 있다고 가정
                psd_db = data.astype(np.float64)
                freq_mhz = None
            else:
                return None

    except Exception:
        return None

    folder = fits_path.parent
    combined_name = f"{folder.name}/{fits_path.name}"
    obs_type = classify_obs_type(combined_name)
    obs_id = _extract_obs_id(folder.name)

    obs = Observation(
        obs_id=obs_id,
        path=folder,
        fits_path=fits_path,
        freq_mhz=freq_mhz,
        psd_db=psd_db,
        header=hdr,
        obs_type=obs_type,
        is_loaded=True,
    )
    return obs


def scan_folder(root: Path) -> list[Observation]:
    """루트 폴더를 스캔하여 모든 관측을 로드한다.

    구조 1: root/HI_Obs_YYYYMMDD_HHMMSS/raw_observation.fits
    구조 2: root/raw_observation.fits (단일 폴더)
    """
    observations: list[Observation] = []
    root = Path(root)

    if not root.is_dir():
        return observations

    # 하위 폴더 탐색
    for item in sorted(root.iterdir()):
        if item.is_dir():
            # 폴더 내 FITS 파일 탐색
            fits_files = list(item.glob("*.fits"))
            for ff in fits_files:
                obs = load_fits(ff)
                if obs is not None:
                    observations.append(obs)
        elif item.suffix.lower() == ".fits":
            # 루트에 바로 있는 FITS
            obs = load_fits(item)
            if obs is not None:
                observations.append(obs)

    return observations


def load_baseline_fits(fits_path: Path) -> Optional[np.ndarray]:
    """베이스라인 FITS를 로드하여 psd 배열만 반환한다."""
    try:
        with fits.open(str(fits_path)) as hdul:
            data = hdul[0].data
            if data.ndim == 2 and data.shape[0] >= 2:
                return data[1].astype(np.float64)
            elif data.ndim == 1:
                return data.astype(np.float64)
    except Exception:
        return None
    return None
