"""처리 결과 캐시 — 중간 처리 결과를 npz/json으로 저장/복원

각 관측 폴더에 processing_cache.npz + processing_state.json을 저장하여
앱 재시작 후에도 처리 결과를 유지한다.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np

from src.models.observation import Observation, ObsType, QCResult, QCStatus, FitResult, FitComponent

logger = logging.getLogger(__name__)


def _cache_npz_path(obs: Observation) -> Path:
    return obs.path / "processing_cache.npz"


def _cache_json_path(obs: Observation) -> Path:
    return obs.path / "processing_state.json"


def save_cache(obs: Observation) -> None:
    """관측의 처리 결과를 디스크에 저장한다."""
    if not obs.path.is_dir():
        return

    # numpy 배열들
    arrays = {}
    if obs.psd_db_clean is not None:
        arrays["psd_db_clean"] = obs.psd_db_clean
    if obs.mask_rfi is not None:
        arrays["mask_rfi"] = obs.mask_rfi
    if obs.psd_db_baseline_removed is not None:
        arrays["psd_db_baseline_removed"] = obs.psd_db_baseline_removed
    if obs.vel_kms is not None:
        arrays["vel_kms"] = obs.vel_kms
    if obs.antenna_temp_k is not None:
        arrays["antenna_temp_k"] = obs.antenna_temp_k

    if arrays:
        np.savez_compressed(str(_cache_npz_path(obs)), **arrays)

    # 스칼라/구조체 상태
    state: dict = {
        "obs_type": obs.obs_type.value,
        "is_preprocessed": obs.is_preprocessed,
        "is_baseline_removed": obs.is_baseline_removed,
        "is_velocity_converted": obs.is_velocity_converted,
        "is_calibrated": obs.is_calibrated,
    }

    # QC
    if obs.qc.status != QCStatus.UNCHECKED:
        state["qc"] = {
            "status": obs.qc.status.value,
            "rms_total": obs.qc.rms_total,
            "rms_center": obs.qc.rms_center,
            "spike_count": obs.qc.spike_count,
            "nan_count": obs.qc.nan_count,
            "inf_count": obs.qc.inf_count,
            "mean_level_db": obs.qc.mean_level_db,
            "messages": obs.qc.messages,
        }

    # 피팅 결과
    if obs.fit_result is not None and obs.fit_result.success:
        state["fit_result"] = {
            "success": True,
            "message": obs.fit_result.message,
            "residual_rms": obs.fit_result.residual_rms,
            "model": obs.fit_result.model,
            "x_unit": obs.fit_result.x_unit,
            "baseline_offset": obs.fit_result.baseline_offset,
            "baseline_slope": obs.fit_result.baseline_slope,
            "baseline_x_ref": obs.fit_result.baseline_x_ref,
            "components": [
                {
                    "amplitude": c.amplitude,
                    "center": c.center,
                    "sigma": c.sigma,
                    "fwhm": c.fwhm,
                    "model": c.model,
                    "shape": c.shape,
                }
                for c in obs.fit_result.components
            ],
        }

    # 피크 데이터 (metadata에 저장된 것)
    if "peaks" in obs.metadata:
        state["peaks"] = obs.metadata["peaks"]

    with open(_cache_json_path(obs), "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    # 단계별 자동 내보내기: 관측 폴더 내 exports/latest 갱신
    try:
        from src.core.export import export_autosave
        export_autosave(obs)
    except Exception:
        logger.exception("자동 내보내기 실패: %s", obs.display_name)


def load_cache(obs: Observation) -> bool:
    """디스크에서 처리 결과를 복원한다. 캐시가 있으면 True."""
    json_path = _cache_json_path(obs)
    npz_path = _cache_npz_path(obs)

    loaded_any = False

    # JSON 상태 복원
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                state = json.load(f)

            # obs_type
            try:
                obs.obs_type = ObsType(state.get("obs_type", "UNKNOWN"))
            except ValueError:
                pass

            obs.is_preprocessed = state.get("is_preprocessed", False)
            obs.is_baseline_removed = state.get("is_baseline_removed", False)
            obs.is_velocity_converted = state.get("is_velocity_converted", False)
            obs.is_calibrated = state.get("is_calibrated", False)

            # QC
            if "qc" in state:
                qc = state["qc"]
                obs.qc = QCResult(
                    status=QCStatus(qc.get("status", "UNCHECKED")),
                    rms_total=qc.get("rms_total", 0),
                    rms_center=qc.get("rms_center", 0),
                    spike_count=qc.get("spike_count", 0),
                    nan_count=qc.get("nan_count", 0),
                    inf_count=qc.get("inf_count", 0),
                    mean_level_db=qc.get("mean_level_db", 0),
                    messages=qc.get("messages", []),
                )

            # 피팅
            if "fit_result" in state:
                fr = state["fit_result"]
                try:
                    obs.fit_result = FitResult(
                        success=fr.get("success", False),
                        message=fr.get("message", ""),
                        residual_rms=fr.get("residual_rms", 0),
                        model=fr.get("model", "gaussian"),
                        x_unit=fr.get("x_unit", ""),
                        baseline_offset=fr.get("baseline_offset", 0.0),
                        baseline_slope=fr.get("baseline_slope", 0.0),
                        baseline_x_ref=fr.get("baseline_x_ref", 0.0),
                        components=[
                            FitComponent(
                                amplitude=c.get("amplitude", 0),
                                center=c.get("center", 0),
                                sigma=c.get("sigma", 0),
                                fwhm=c.get("fwhm", 0),
                                model=c.get("model", fr.get("model", "gaussian")),
                                shape=c.get("shape", 0),
                            )
                            for c in fr.get("components", [])
                        ],
                    )
                except (TypeError, AttributeError):
                    pass

            # 피크
            if "peaks" in state:
                obs.metadata["peaks"] = state["peaks"]

            loaded_any = True

        except (json.JSONDecodeError, IOError, KeyError):
            pass

    # NPZ 배열 복원
    if npz_path.exists():
        try:
            with np.load(str(npz_path)) as data:
                if "psd_db_clean" in data:
                    obs.psd_db_clean = data["psd_db_clean"]
                if "mask_rfi" in data:
                    obs.mask_rfi = data["mask_rfi"]
                if "psd_db_baseline_removed" in data:
                    obs.psd_db_baseline_removed = data["psd_db_baseline_removed"]
                if "vel_kms" in data:
                    obs.vel_kms = data["vel_kms"]
                if "antenna_temp_k" in data:
                    obs.antenna_temp_k = data["antenna_temp_k"]
            loaded_any = True
        except Exception:
            pass

    return loaded_any


def clear_cache(obs: Observation) -> None:
    """캐시를 삭제한다."""
    for p in [_cache_npz_path(obs), _cache_json_path(obs)]:
        if p.exists():
            p.unlink()
