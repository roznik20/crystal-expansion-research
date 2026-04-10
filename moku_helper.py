import csv
import os
import numpy as np

# ===========================================================================
# HARD CODED PART
# ===========================================================================

MOKU_SERIAL       = "MokuGo-008036.local"

# Thermocouple (AD595) channel on the Moku Go analog input
THERMO_CHANNEL    = 2

# FRA sweep settings
SWEEP_START_HZ    = 1_000        # start frequency (Hz)
SWEEP_END_HZ      = 1_000_000    # stop  frequency (Hz)
SWEEP_POINTS      = 512          # number of frequency points
SWEEP_AMPLITUDE   = 0.5          # stimulus amplitude (Vpp)
OUTPUT_CHANNEL    = 1            # Moku output channel for the stimulus

# Output file
OUTPUT_CSV        = "resonance_log.csv"

# ===========================================================================
# CALIBRATION  –  cubic fit coefficients from thermocouple_calibration.ipynb
# V_mV = a3*t^3 + a2*t^2 + a1*t + a0,  t = (T_K - T_MEAN) / T_STD
# Domain: 133.15 K (−140 °C) – 298.15 K (25 °C)
# ===========================================================================

CAL_COEFFS  = np.array([-5.371838e+01, 1.037465e+02,
                         1961.945128, 1227.4515])
CAL_T_MEAN  = 398.27    # K
CAL_T_STD   = 193.13    # K
CAL_T_MIN_K = 73.15     # K  (-200 °C)
CAL_T_MAX_K = 573.15    # K  (300 °C)

CSV_FIELDS = ["run", "time", "capacitance_value", "thermo_volt", "temperature_C"]

a,b = 1.08033962e-02, 3.70341310e-13

#=============================================================================
#DEFINING HELPER FUNCTIONS FOR mim_moku.py
#=============================================================================

def voltage_to_temperature_C(voltage_V: float,
                              coeffs, T_mean, T_std,
                              T_min_K, T_max_K) -> float:
    """
    Inverts the cubic calibration curve:
      V_mV = a3*t^3 + a2*t^2 + a1*t + a0   (t = T_norm)
    Solves for t, maps back to Kelvin, restricts to the calibration domain,
    and returns the result in °C.

    Raises ValueError if no real root falls within the calibration domain.
    """
    voltage_mV = voltage_V * 1000.0          # Moku reads Volts; calibration is in mV

    # Build the shifted polynomial: poly(t) - V_mV = 0
    shifted = coeffs.copy()
    shifted[-1] -= voltage_mV               # subtract V from the constant term

    roots = np.roots(shifted)

    # Keep only real roots inside the calibration domain
    real_roots = roots[np.abs(roots.imag) < 1e-6].real
    T_candidates = real_roots * T_std + T_mean    # un-normalise back to Kelvin

    in_domain = T_candidates[(T_candidates >= T_min_K) & (T_candidates <= T_max_K)]

    if len(in_domain) == 0:
        raise ValueError(
            f"Measured voltage {voltage_mV:.2f} mV is outside the calibration "
            f"domain ({T_min_K - 273.15:.1f} °C – {T_max_K - 273.15:.1f} °C)."
        )

    T_K = float(in_domain[0])
    return T_K - 273.15


def ensure_csv(path: str) -> None:
    if not os.path.exists(path):
        with open(path, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()


def append_row(path: str, row: dict) -> None:
    with open(path, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=CSV_FIELDS).writerow(row)


def find_resonant_frequency(frequencies: list, gains_db: list,
                            smooth_window: int = 15) -> float:
    freqs = np.asarray(frequencies, dtype=float)
    gains = np.asarray(gains_db, dtype=float)

    # ── Step 1: smooth with a moving-average to suppress noise ──
    # Pad edges with the boundary values so convolution doesn't create
    # fake peaks from zero-padding (gains are negative dB).
    pad = smooth_window // 2
    padded = np.pad(gains, pad, mode='edge')
    kernel = np.ones(smooth_window) / smooth_window
    smoothed = np.convolve(padded, kernel, mode='valid')

    # ── Step 2: find peak of smoothed curve ──
    peak_idx = int(np.nanargmax(smoothed))

    # ── Step 3: parabolic interpolation on the original data ──
    # Fit a parabola to the 3 points around the peak for sub-bin accuracy.
    # Uses log-frequency because the sweep is log-spaced.
    if 1 <= peak_idx <= len(freqs) - 2:
        log_f = np.log(freqs[peak_idx - 1 : peak_idx + 2])
        g     = gains[peak_idx - 1 : peak_idx + 2]
        # vertex of parabola through 3 points: offset = 0.5*(g[0]-g[2])/(g[0]-2*g[1]+g[2])
        denom = g[0] - 2 * g[1] + g[2]
        if denom != 0:
            offset = 0.5 * (g[0] - g[2]) / denom
            return float(np.exp(log_f[1] + offset * (log_f[2] - log_f[1])))

    return float(freqs[peak_idx])

def read_thermo_volt(osc_inst,channel):
    data = osc_inst.get_data(wait_complete=True)
    samples = data[f"ch{channel}"]
    return float(np.mean(samples))

def cap_calc(f):
    return ( 1 / (2*np.pi*f) ** 2 - b) / a