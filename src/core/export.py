"""Step 12: 결과 저장/내보내기"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

from src.models.observation import Observation, FitResult


def _default_serializer(obj: Any) -> Any:
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


def export_csv(
    obs: Observation,
    output_path: Path,
    include_clean: bool = True,
    include_baseline_removed: bool = True,
    include_velocity: bool = True,
) -> Path:
    """결과를 CSV로 내보낸다."""
    rows = []
    if obs.freq_mhz is None or obs.psd_db is None:
        return output_path
    n = min(len(obs.freq_mhz), len(obs.psd_db))

    for i in range(n):
        row = {"freq_mhz": obs.freq_mhz[i], "psd_db_raw": obs.psd_db[i]}

        if include_clean and obs.psd_db_clean is not None:
            row["psd_db_clean"] = obs.psd_db_clean[i]

        if include_baseline_removed and obs.psd_db_baseline_removed is not None:
            row["psd_db_baseline_removed"] = obs.psd_db_baseline_removed[i]

        if include_velocity and obs.vel_kms is not None:
            row["vel_kms"] = obs.vel_kms[i]

        if obs.antenna_temp_k is not None and i < len(obs.antenna_temp_k):
            row["antenna_temp_k"] = obs.antenna_temp_k[i]

        rows.append(row)

    if not rows:
        return output_path

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    return output_path


def export_fit_json(
    fit_result: FitResult,
    processing_params: dict,
    output_path: Path,
) -> Path:
    """피팅 결과 + 처리 파라미터를 JSON으로 저장한다."""
    data = {
        "fit": {
            "success": fit_result.success,
            "message": fit_result.message,
            "residual_rms": fit_result.residual_rms,
            "model": fit_result.model,
            "x_unit": fit_result.x_unit,
            "baseline_offset": fit_result.baseline_offset,
            "baseline_slope": fit_result.baseline_slope,
            "baseline_x_ref": fit_result.baseline_x_ref,
            "components": [
                {
                    "amplitude": c.amplitude,
                    "center": c.center,
                    "sigma": c.sigma,
                    "fwhm": c.fwhm,
                    "model": c.model,
                    "shape": c.shape,
                }
                for c in fit_result.components
            ],
        },
        "processing": processing_params,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=_default_serializer)
    return output_path


def export_package(
    obs: Observation,
    output_dir: Path,
    processing_params: dict = None,
) -> dict[str, Path]:
    """전체 결과 패키지를 저장한다."""
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {}

    # CSV
    csv_path = output_dir / "result.csv"
    export_csv(obs, csv_path)
    files["csv"] = csv_path

    # fit.json
    if obs.fit_result and obs.fit_result.success:
        fit_path = output_dir / "fit.json"
        export_fit_json(obs.fit_result, processing_params or {}, fit_path)
        files["fit"] = fit_path

    # meta.json
    from src.core.metadata import merge_header_and_meta
    meta = merge_header_and_meta(obs)
    meta_path = output_dir / "meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False, default=_default_serializer)
    files["meta"] = meta_path

    return files


def export_autosave(
    obs: Observation,
    processing_params: dict | None = None,
) -> dict[str, Path]:
    """관측 폴더 내부 자동 내보내기.

    경로: <obs.path>/exports/latest
    """
    output_dir = obs.path / "exports" / "latest"
    files = export_package(obs, output_dir, processing_params or {})

    # 피크 목록은 별도 파일로 함께 저장
    if "peaks" in obs.metadata:
        peaks_path = output_dir / "peaks.json"
        with open(peaks_path, "w", encoding="utf-8") as f:
            json.dump({"peaks": obs.metadata["peaks"]}, f, indent=2, ensure_ascii=False, default=_default_serializer)
        files["peaks"] = peaks_path

    return files
