"""SDR 모듈 제어 — RTL-SDR 연결/관측 실행

향후 ASCOM 드라이버 연결 시 이 모듈에 마운트 컨트롤을 추가한다.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

from PySide6.QtCore import QObject, Signal, QThread


@dataclass
class ObsParams:
    """관측 파라미터"""
    sample_rate: float = 2.4e6
    center_freq: float = 1420.4e6
    gain: float = 40.0
    nfft: int = 2048
    iterations: int = 5000
    samples_per_scan: int = 512 * 1024

    # 옵션
    use_bias_tee: bool = False
    remove_dc: bool = True
    use_hanning: bool = True

    # 관측 타입
    obs_type: str = "SOU"       # SOU / AMB / SKY

    # 메타데이터
    site_name: str = ""
    lat: float = 37.5665
    lon: float = 126.9780
    height: float = 38.0
    timezone: str = "KST"
    alt_deg: Optional[float] = None
    az_deg: Optional[float] = None
    note: str = ""

    # 저장
    save_dir: str = ""
    project_name: str = ""


class SDRStatus:
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    OBSERVING = "observing"
    ERROR = "error"


class SDRController(QObject):
    """RTL-SDR 연결 및 관측 제어"""

    status_changed = Signal(str, str)    # (status, message)
    observation_finished = Signal(dict)  # 관측 결과 dict
    observation_error = Signal(str)      # 에러 메시지
    progress_updated = Signal(int, int)  # (current, total)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sdr = None
        self._status = SDRStatus.DISCONNECTED
        self._rtlsdr_available = False

        self._try_import_rtlsdr()

    def _try_import_rtlsdr(self):
        """rtlsdr 라이브러리 로드 시도"""
        try:
            # DLL 경로 설정 (Windows)
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(os.path.dirname(current_dir))
            dll_dir = os.path.join(project_root, "전파관측")

            if os.path.isdir(dll_dir):
                if dll_dir not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")
                if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
                    os.add_dll_directory(dll_dir)

            from rtlsdr import RtlSdr
            self._rtlsdr_available = True
        except (ImportError, OSError):
            self._rtlsdr_available = False

    @property
    def is_available(self) -> bool:
        return self._rtlsdr_available

    @property
    def status(self) -> str:
        return self._status

    def check_connection(self) -> bool:
        """SDR 연결 상태 확인"""
        if not self._rtlsdr_available:
            self._status = SDRStatus.DISCONNECTED
            self.status_changed.emit(self._status, "rtlsdr 라이브러리 없음")
            return False

        try:
            from rtlsdr import RtlSdr
            sdr = RtlSdr()
            sdr.close()
            self._status = SDRStatus.CONNECTED
            self.status_changed.emit(self._status, "SDR 연결됨")
            return True
        except Exception as e:
            self._status = SDRStatus.DISCONNECTED
            self.status_changed.emit(self._status, f"SDR 연결 실패: {e}")
            return False

    def run_observation(self, params: ObsParams) -> Optional[dict]:
        """관측을 실행한다. (동기 — Worker 스레드에서 호출할 것)

        Returns:
            {
                "freq_axis": ndarray,
                "raw_psd_db": ndarray,
                "fits_path": Path,
                "folder": Path,
                "header": dict,
            }
        """
        if not self._rtlsdr_available:
            self.observation_error.emit("rtlsdr 라이브러리가 없습니다")
            return None

        from rtlsdr import RtlSdr

        self._status = SDRStatus.OBSERVING
        self.status_changed.emit(self._status, "관측 중...")

        try:
            sdr = RtlSdr()
            sdr.sample_rate = params.sample_rate
            sdr.center_freq = params.center_freq
            sdr.gain = params.gain
            if params.use_bias_tee:
                sdr.set_bias_tee(True)

            sr = params.sample_rate
            cf = params.center_freq
            nfft = params.nfft

            freq_axis = np.fft.fftshift(
                np.fft.fftfreq(nfft, d=1.0 / sr)
            ) / 1e6 + (cf / 1e6)

            accumulated_psd = np.zeros(nfft)
            window = np.hanning(nfft) if params.use_hanning else np.ones(nfft)

            try:
                for i in range(params.iterations):
                    samples = sdr.read_samples(params.samples_per_scan)
                    if params.remove_dc:
                        samples = samples - np.mean(samples)
                    if len(samples) < nfft:
                        continue
                    segments = samples[: (len(samples) // nfft) * nfft].reshape((-1, nfft))
                    fft_res = np.fft.fft(segments * window, axis=1)
                    accumulated_psd += np.mean(
                        np.abs(np.fft.fftshift(fft_res, axes=1)) ** 2, axis=0
                    )
                    self.progress_updated.emit(i + 1, params.iterations)
            finally:
                sdr.close()

            raw_psd_db = 10 * np.log10(accumulated_psd / params.iterations + 1e-12)

            # 저장
            now = datetime.now()
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            type_suffix = f"_{params.obs_type}"
            folder_name = f"HI_Obs_{timestamp}{type_suffix}"

            save_root = Path(params.save_dir) if params.save_dir else Path.cwd()
            folder = save_root / folder_name
            folder.mkdir(parents=True, exist_ok=True)

            # FITS 저장
            from astropy.io import fits as pyfits
            combined = np.vstack((freq_axis, raw_psd_db))
            hdu = pyfits.PrimaryHDU(combined)
            hdr = hdu.header
            hdr["DATE-OBS"] = now.isoformat()
            hdr["FREQ-CEN"] = cf
            hdr["SAMPRATE"] = sr
            hdr["GAIN"] = params.gain
            hdr["NFFT"] = nfft
            hdr["OBS-TYPE"] = params.obs_type
            hdr["SITE"] = params.site_name
            hdr["SITELAT"] = params.lat
            hdr["SITELON"] = params.lon
            hdr["SITEHGT"] = params.height
            hdr["TIMEZONE"] = params.timezone
            if params.alt_deg is not None:
                hdr["ALT-DEG"] = params.alt_deg
            if params.az_deg is not None:
                hdr["AZ-DEG"] = params.az_deg
            if params.note:
                hdr["NOTE"] = params.note[:68]

            fits_path = folder / "raw_observation.fits"
            hdu.writeto(str(fits_path), overwrite=True)

            # raw plot 저장
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.plot(freq_axis, raw_psd_db, "k", lw=0.7)
            ax.set_title(f"Raw PSD — {timestamp} [{params.obs_type}]")
            ax.set_xlabel("Frequency (MHz)")
            ax.set_ylabel("Power (dB)")
            ax.grid(True)
            fig.savefig(str(folder / "raw_plot.png"), dpi=200, bbox_inches="tight")
            plt.close(fig)

            # meta.json 저장
            import json
            meta = {
                "obs_type": params.obs_type,
                "site_name": params.site_name,
                "lat": params.lat,
                "lon": params.lon,
                "height": params.height,
                "timezone": params.timezone,
                "alt_deg": params.alt_deg,
                "az_deg": params.az_deg,
                "note": params.note,
                "sample_rate": sr,
                "center_freq": cf,
                "gain": params.gain,
                "nfft": nfft,
                "iterations": params.iterations,
                "samples_per_scan": params.samples_per_scan,
                "use_bias_tee": params.use_bias_tee,
                "remove_dc": params.remove_dc,
                "use_hanning": params.use_hanning,
            }
            with open(folder / "meta.json", "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)

            self._status = SDRStatus.CONNECTED
            result = {
                "freq_axis": freq_axis,
                "raw_psd_db": raw_psd_db,
                "fits_path": fits_path,
                "folder": folder,
                "header": dict(hdr),
            }
            self.observation_finished.emit(result)
            self.status_changed.emit(self._status, f"관측 완료: {folder_name}")
            return result

        except Exception as e:
            self._status = SDRStatus.ERROR
            self.observation_error.emit(str(e))
            self.status_changed.emit(SDRStatus.ERROR, str(e))
            return None


class ObservationWorker(QThread):
    """관측을 별도 스레드에서 실행"""

    finished = Signal(dict)
    error = Signal(str)
    progress = Signal(int, int)

    def __init__(self, controller: SDRController, params: ObsParams, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.params = params

    def run(self):
        self.controller.progress_updated.connect(self.progress.emit)
        result = self.controller.run_observation(self.params)
        if result:
            self.finished.emit(result)
        else:
            self.error.emit("관측 실패")
