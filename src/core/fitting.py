"""Step 10: 프로파일 피팅 (Gaussian / Skewed Gaussian / Voigt)."""

from __future__ import annotations

import numpy as np
from scipy.optimize import curve_fit
from scipy.special import erf, wofz

from src.models.observation import FitComponent, FitResult
from src.core.detection import PeakCandidate


SUPPORTED_FIT_MODELS = ("gaussian", "skewed_gaussian", "voigt")


def _estimate_default_sigma(x: np.ndarray) -> float:
    """x축 범위에서 기본 sigma 추정."""
    x_range = float(np.ptp(x))
    if x_range <= 0:
        return 1.0
    return max(0.01, x_range * 0.01)


def _gaussian_profile(x: np.ndarray, amplitude: float, center: float, sigma: float) -> np.ndarray:
    sigma = max(float(abs(sigma)), 1e-12)
    t = (x - center) / sigma
    return amplitude * np.exp(-0.5 * t * t)


def _skewed_gaussian_profile(
    x: np.ndarray,
    amplitude: float,
    center: float,
    sigma: float,
    alpha: float,
) -> np.ndarray:
    sigma = max(float(abs(sigma)), 1e-12)
    t = (x - center) / sigma
    return amplitude * np.exp(-0.5 * t * t) * (1.0 + erf(alpha * t / np.sqrt(2.0)))


def _voigt_profile(
    x: np.ndarray,
    amplitude: float,
    center: float,
    sigma: float,
    gamma: float,
) -> np.ndarray:
    sigma = max(float(abs(sigma)), 1e-12)
    gamma = max(float(abs(gamma)), 1e-12)
    z = ((x - center) + 1j * gamma) / (sigma * np.sqrt(2.0))
    profile = np.real(wofz(z)) / (sigma * np.sqrt(2.0 * np.pi))
    peak = float(np.nanmax(profile)) if profile.size else 1.0
    if not np.isfinite(peak) or peak <= 0:
        peak = 1.0
    return amplitude * (profile / peak)


def _component_profile(
    mode: str,
    x: np.ndarray,
    amplitude: float,
    center: float,
    sigma: float,
    shape: float = 0.0,
) -> np.ndarray:
    if mode == "skewed_gaussian":
        return _skewed_gaussian_profile(x, amplitude, center, sigma, shape)
    if mode == "voigt":
        return _voigt_profile(x, amplitude, center, sigma, shape)
    return _gaussian_profile(x, amplitude, center, sigma)


def _component_stride(mode: str) -> int:
    return 4 if mode in ("skewed_gaussian", "voigt") else 3


def _model_from_params(mode: str, x: np.ndarray, params: np.ndarray) -> np.ndarray:
    stride = _component_stride(mode)
    n_comp = len(params) // stride
    y = np.zeros_like(x, dtype=float)
    for i in range(n_comp):
        offset = i * stride
        a = float(params[offset])
        c = float(params[offset + 1])
        s = float(params[offset + 2])
        shape = float(params[offset + 3]) if stride == 4 else 0.0
        y += _component_profile(mode, x, a, c, s, shape)
    return y


def _multi_gaussian(x: np.ndarray, *params) -> np.ndarray:
    """기존 호출 호환용."""
    return _model_from_params("gaussian", x, np.asarray(params, dtype=float))


def evaluate_fit(
    x: np.ndarray,
    fit_result: FitResult,
) -> tuple[np.ndarray, list[np.ndarray]]:
    """FitResult로부터 total/성분 곡선 계산."""
    x = np.asarray(x, dtype=float)
    baseline = (
        float(getattr(fit_result, "baseline_offset", 0.0))
        + float(getattr(fit_result, "baseline_slope", 0.0))
        * (x - float(getattr(fit_result, "baseline_x_ref", 0.0)))
    )
    if not fit_result.components:
        return baseline, []

    mode = fit_result.model or "gaussian"
    comps: list[np.ndarray] = []
    total = baseline.copy()
    for c in fit_result.components:
        y = _component_profile(
            mode,
            x,
            float(c.amplitude),
            float(c.center),
            float(c.sigma),
            float(c.shape),
        )
        comps.append(y)
        total += y
    return total, comps


def _fwhm_from_mode(mode: str, sigma: float, shape: float) -> float:
    sigma = abs(float(sigma))
    if mode == "voigt":
        gamma = abs(float(shape))
        lorentz_fwhm = 2.0 * gamma
        gauss_fwhm = 2.355 * sigma
        return float(0.5346 * lorentz_fwhm + np.sqrt(0.2166 * lorentz_fwhm ** 2 + gauss_fwhm ** 2))
    return float(2.355 * sigma)


def _run_mcmc_refine(
    model_fn,
    x_fit: np.ndarray,
    y_fit: np.ndarray,
    start: np.ndarray,
    bounds_lo: np.ndarray,
    bounds_hi: np.ndarray,
    steps: int = 2000,
    burn_frac: float = 0.5,
    proposal_scale: float = 0.03,
    rng_seed: int | None = None,
) -> tuple[np.ndarray, float]:
    """간단한 Metropolis-Hastings로 파라미터를 정련한다.

    Returns:
        (best_params, acceptance_ratio)
    """
    rng = np.random.default_rng(rng_seed)
    span = np.maximum(bounds_hi - bounds_lo, 1e-12)
    burn = int(max(0, min(steps - 1, round(steps * burn_frac))))

    def in_bounds(p: np.ndarray) -> bool:
        return bool(np.all(p >= bounds_lo) and np.all(p <= bounds_hi))

    # 노이즈 추정: 초기 모델 잔차 MAD
    y0 = model_fn(x_fit, *start)
    r0 = y_fit - y0
    mad = float(np.median(np.abs(r0 - np.median(r0))))
    noise = mad * 1.4826
    if not np.isfinite(noise) or noise <= 1e-12:
        noise = float(np.std(r0))
    if not np.isfinite(noise) or noise <= 1e-12:
        noise = 1.0

    def log_post(p: np.ndarray) -> float:
        yhat = model_fn(x_fit, *p)
        res = y_fit - yhat
        return float(-0.5 * np.sum((res / noise) ** 2))

    base = np.asarray(start, dtype=float).copy()
    if not in_bounds(base):
        base = np.clip(base, bounds_lo, bounds_hi)

    best_params = base.copy()
    best_accept = 0.0

    for scale_factor in (1.0, 0.3, 0.1, 0.03):
        step_sigma = np.maximum(span * proposal_scale * scale_factor, 1e-9)
        current = base.copy()
        cur_lp = log_post(current)
        accepted = 0
        samples: list[np.ndarray] = []

        for i in range(max(steps, 1)):
            prop = current + rng.normal(0.0, step_sigma, size=current.shape)
            prop = np.clip(prop, bounds_lo, bounds_hi)
            prop_lp = log_post(prop)
            if np.log(rng.random()) < (prop_lp - cur_lp):
                current = prop
                cur_lp = prop_lp
                accepted += 1

            if i >= burn:
                samples.append(current.copy())

        accept_ratio = accepted / max(steps, 1)
        if samples:
            chain = np.asarray(samples, dtype=float)
            candidate = np.median(chain, axis=0)
            candidate = np.clip(candidate, bounds_lo, bounds_hi)
        else:
            candidate = current

        best_params = candidate
        best_accept = accept_ratio
        if accept_ratio >= 0.02:
            break

    return best_params, best_accept


def fit_gaussians(
    x: np.ndarray,
    y: np.ndarray,
    peaks: list[PeakCandidate],
    default_sigma: float = None,
    fit_window_factor: float = 3.0,
    model: str = "gaussian",
    x_unit: str = "",
    solver: str = "curve_fit",
    mcmc_steps: int = 2500,
    mcmc_seed: int | None = None,
    mcmc_proposal_scale: float = 0.03,
) -> FitResult:
    """피크 후보를 초기값으로 프로파일 피팅.

    model: gaussian | skewed_gaussian | voigt
    """
    if model not in SUPPORTED_FIT_MODELS:
        return FitResult(success=False, message=f"지원하지 않는 모델: {model}", model=model, x_unit=x_unit)
    if not peaks:
        return FitResult(success=False, message="피크 후보 없음", model=model, x_unit=x_unit)

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    finite = np.isfinite(x) & np.isfinite(y)
    if np.count_nonzero(finite) < 10:
        return FitResult(success=False, message="유효 데이터가 부족합니다.", model=model, x_unit=x_unit)
    x = x[finite]
    y = y[finite]

    if default_sigma is None:
        default_sigma = _estimate_default_sigma(x)

    x_range = float(np.ptp(x)) if len(x) > 1 else 1.0
    dx = float(np.median(np.abs(np.diff(np.sort(x))))) if len(x) > 1 else 1.0
    sigma_min = max(1e-6, dx * 0.5, x_range * 0.001)
    sigma_max = max(sigma_min * 2.0, x_range / 2.0)
    stride = _component_stride(model)
    x_ref = float(np.median(x))

    peaks_sorted = sorted(peaks, key=lambda p: abs(p.snr), reverse=True)

    def _full_model(xx: np.ndarray, *params) -> np.ndarray:
        p = np.asarray(params, dtype=float)
        if len(p) < 2:
            return np.zeros_like(xx, dtype=float)
        comp = p[:-2]
        b0 = float(p[-2])
        b1 = float(p[-1])
        return _model_from_params(model, xx, comp) + (b0 + b1 * (xx - x_ref))

    def _build_line_mask(sel_peaks: list[PeakCandidate]) -> np.ndarray:
        mask = np.zeros(len(x), dtype=bool)
        for pk in sel_peaks:
            width_guess = pk.width if pk.width > 0 else (2.355 * default_sigma)
            half_window = max(width_guess * fit_window_factor, dx * 10.0)
            mask |= np.abs(x - pk.position) <= half_window
        if np.count_nonzero(mask) < max(20, len(sel_peaks) * 10):
            mask[:] = True
        return mask

    def _build_seed(sel_peaks: list[PeakCandidate]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        p0: list[float] = []
        lo: list[float] = []
        hi: list[float] = []

        for pk in sel_peaks:
            if pk.width > 0:
                sigma_init = pk.width / 2.355
            else:
                sigma_init = default_sigma
            sigma_init = max(sigma_min, min(sigma_init, sigma_max))

            width_guess = pk.width if pk.width > 0 else (2.355 * sigma_init)
            center_window = max(width_guess * 1.2, dx * 6.0, x_range * 0.005)
            center_window = min(center_window, x_range * 0.35 if x_range > 0 else center_window)
            center_lo = max(float(x.min()), pk.position - center_window)
            center_hi = min(float(x.max()), pk.position + center_window)
            if center_hi <= center_lo:
                center_lo = float(x.min())
                center_hi = float(x.max())

            sigma_lo = max(sigma_min, sigma_init * 0.3)
            sigma_hi = min(sigma_max, max(sigma_lo * 1.2, sigma_init * 3.5))

            if pk.amplitude < 0:
                amp_lo = min(pk.amplitude * 6.0, pk.amplitude - abs(pk.amplitude) * 0.5)
                amp_hi = 0.0
            else:
                amp_lo = 0.0
                amp_hi = max(pk.amplitude * 6.0, pk.amplitude + float(np.std(y)) * 3.0, 1.0)

            p0.extend([pk.amplitude, pk.position, sigma_init])
            lo.extend([amp_lo, center_lo, sigma_lo])
            hi.extend([amp_hi, center_hi, sigma_hi])

            if model == "skewed_gaussian":
                p0.append(0.0)
                lo.append(-8.0)
                hi.append(8.0)
            elif model == "voigt":
                gamma_init = max(sigma_lo, min(sigma_hi, sigma_init))
                p0.append(gamma_init)
                lo.append(max(1e-6, sigma_lo * 0.3))
                hi.append(max(gamma_init * 1.2, sigma_hi * 2.0))

        line_mask = _build_line_mask(sel_peaks)
        edge_n = max(10, int(0.15 * len(x)))
        edge_mask = np.zeros(len(x), dtype=bool)
        edge_mask[:edge_n] = True
        edge_mask[-edge_n:] = True
        fit_mask = line_mask | edge_mask

        base_mask = (~line_mask) & np.isfinite(y)
        if np.count_nonzero(base_mask) < 10:
            base_mask = edge_mask & np.isfinite(y)

        if np.count_nonzero(base_mask) >= 10:
            try:
                slope, intercept = np.polyfit(x[base_mask], y[base_mask], deg=1)
            except Exception:
                slope, intercept = 0.0, float(np.median(y))
            b1 = float(slope)
            b0 = float(intercept + slope * x_ref)
            baseline_est = b0 + b1 * (x[base_mask] - x_ref)
            resid_base = y[base_mask] - baseline_est
            mad_base = float(np.median(np.abs(resid_base - np.median(resid_base))))
            noise_base = mad_base * 1.4826 if mad_base > 0 else float(np.std(resid_base))
            if not np.isfinite(noise_base) or noise_base <= 1e-12:
                noise_base = float(np.std(y)) * 0.3
        else:
            b0 = float(np.median(y))
            b1 = 0.0
            noise_base = float(np.std(y)) * 0.3

        y_span = max(float(np.ptp(y)), float(np.std(y)) * 6.0, 1.0)
        slope_scale = y_span / max(x_range, 1e-6)
        b0_margin = max(4.0 * noise_base, 0.08 * y_span)
        b1_margin = max(
            6.0 * noise_base / max(x_range, 1e-6),
            abs(b1) * 1.5,
            0.02 * slope_scale,
        )
        p0.extend([b0, b1])
        lo.extend([b0 - b0_margin, b1 - b1_margin])
        hi.extend([b0 + b0_margin, b1 + b1_margin])
        return (
            np.asarray(p0, dtype=float),
            np.asarray(lo, dtype=float),
            np.asarray(hi, dtype=float),
            fit_mask,
        )

    best = None
    best_bic = np.inf
    max_n = min(len(peaks_sorted), 8)
    for n_comp_try in range(1, max_n + 1):
        sel = peaks_sorted[:n_comp_try]
        p0_arr, lo_arr, hi_arr, fit_mask = _build_seed(sel)
        x_fit = x[fit_mask]
        y_fit = y[fit_mask]
        if len(x_fit) < max(20, n_comp_try * 10):
            x_fit = x
            y_fit = y
        try:
            popt_try, _ = curve_fit(
                _full_model, x_fit, y_fit, p0=p0_arr,
                bounds=(lo_arr, hi_arr),
                maxfev=30000,
            )
        except (RuntimeError, ValueError):
            continue

        res = y_fit - _full_model(x_fit, *popt_try)
        rss = float(np.sum(res * res))
        n_data = max(len(y_fit), 2)
        k = len(popt_try)
        bic = n_data * np.log(max(rss / n_data, 1e-12)) + k * np.log(n_data)
        if bic < best_bic:
            best_bic = bic
            best = (
                popt_try,
                lo_arr,
                hi_arr,
                x_fit,
                y_fit,
                n_comp_try,
            )

    if best is None:
        return FitResult(success=False, message="피팅 실패: 유효한 해를 찾지 못했습니다.", model=model, x_unit=x_unit)

    popt, lo_arr, hi_arr, x_fit, y_fit, n_comp = best
    mcmc_accept = None
    if solver == "mcmc":
        try:
            popt, mcmc_accept = _run_mcmc_refine(
                _full_model,
                x_fit,
                y_fit,
                np.asarray(popt, dtype=float),
                lo_arr,
                hi_arr,
                steps=max(200, int(mcmc_steps)),
                burn_frac=0.5,
                proposal_scale=float(max(1e-4, mcmc_proposal_scale)),
                rng_seed=mcmc_seed,
            )
        except Exception as e:
            return FitResult(
                success=False,
                message=f"MCMC 정련 실패: {e}",
                model=model,
                x_unit=x_unit,
            )

    components: list[FitComponent] = []
    comp_params = np.asarray(popt[:-2], dtype=float)
    n_comp = len(comp_params) // stride
    for i in range(n_comp):
        offset = i * stride
        amp = float(comp_params[offset])
        center = float(comp_params[offset + 1])
        sigma = float(abs(comp_params[offset + 2]))
        shape = float(comp_params[offset + 3]) if stride == 4 else 0.0
        components.append(FitComponent(
            amplitude=amp,
            center=center,
            sigma=sigma,
            fwhm=_fwhm_from_mode(model, sigma, shape),
            model=model,
            shape=shape,
        ))
    components.sort(key=lambda c: c.center)

    b0 = float(popt[-2]) if len(popt) >= 2 else 0.0
    b1 = float(popt[-1]) if len(popt) >= 1 else 0.0
    fitted = _full_model(x, *np.asarray(popt, dtype=float))
    residual_rms = float(np.sqrt(np.mean((y - fitted) ** 2)))

    return FitResult(
        components=components,
        residual_rms=residual_rms,
        success=True,
        message=(
            f"{n_comp}성분 {model} 피팅 완료"
            if mcmc_accept is None
            else f"{n_comp}성분 {model} MCMC 피팅 완료 (accept={mcmc_accept:.2f}, BIC선택)"
        ),
        model=model,
        x_unit=x_unit,
        baseline_offset=b0,
        baseline_slope=b1,
        baseline_x_ref=x_ref,
    )
