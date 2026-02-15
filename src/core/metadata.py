"""Step 3: 메타데이터 관리 (로드/저장/편집)"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.models.observation import Observation


DEFAULT_METADATA = {
    "site_name": "",
    "lat": 0.0,
    "lon": 0.0,
    "height": 0.0,
    "timezone": "KST",
    "alt_deg": None,
    "az_deg": None,
    "note": "",
}


def load_meta_json(obs: Observation) -> dict:
    """관측 폴더의 meta.json을 읽는다. 없으면 빈 dict."""
    meta_path = obs.path / "meta.json"
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_meta_json(obs: Observation, meta: dict) -> Path:
    """meta.json으로 저장한다. 원본 FITS는 건드리지 않는다."""
    meta_path = obs.path / "meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False, default=_json_default)
    return meta_path


def _json_default(obj: Any) -> Any:
    """numpy 타입 등 JSON 직렬화 헬퍼"""
    import numpy as np
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return str(obj)


def merge_header_and_meta(obs: Observation) -> dict:
    """FITS 헤더와 meta.json을 병합한다. meta.json이 우선."""
    merged = dict(DEFAULT_METADATA)
    # FITS 헤더에서 가져올 수 있는 값
    if "DATE-OBS" in obs.header:
        merged["date_obs"] = obs.header["DATE-OBS"]
    if "FREQ-CEN" in obs.header:
        merged["freq_cen"] = obs.header["FREQ-CEN"]
    if "SAMPRATE" in obs.header:
        merged["sample_rate"] = obs.header["SAMPRATE"]
    if "GAIN" in obs.header:
        merged["gain"] = obs.header["GAIN"]
    if "NFFT" in obs.header:
        merged["nfft"] = obs.header["NFFT"]
    # meta.json으로 덮어쓰기
    merged.update(obs.metadata)
    return merged
