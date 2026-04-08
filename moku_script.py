"""
Crystal Expansion Frequency Sweep Logger
=========================================
For each run:
  1. Deploys Oscilloscope on the Moku Go to read the AD595 thermocouple voltage.
  2. Converts that voltage to temperature (°C) using the cubic calibration curve
     from thermocouple_calibration.ipynb (domain: 130 K – 300 K).
  3. Deploys FrequencyResponseAnalyzer to run a frequency sweep.
  4. Finds the resonant frequency as the frequency with maximum gain.
  5. Appends one row to the CSV: run, time, resonant_frequency_hz, temperature_C.

CSV schema
----------
run                  : integer, increments each loop iteration
time                 : ISO-8601 wall-clock timestamp
resonant_frequency_hz: frequency (Hz) at which gain is maximum
temperature_C        : temperature in °C from thermocouple calibration
"""

import csv
import datetime
import os
import numpy as np

from moku.instruments import FrequencyResponseAnalyzer, Oscilloscope

# ===========================================================================
# USER CONFIGURATION
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


# ===========================================================================
# CSV helpers
# ===========================================================================

CSV_FIELDS = ["run", "time", "capacitance_value", "thermo_volt", "temperature_C"]


def ensure_csv(path: str) -> None:
    if not os.path.exists(path):
        with open(path, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()


def append_row(path: str, row: dict) -> None:
    with open(path, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=CSV_FIELDS).writerow(row)


# ===========================================================================
# Moku helpers
# ===========================================================================

def read_thermocouple_voltage(serial: str, channel: int) -> float:
    """
    Briefly deploys the Oscilloscope, reads one data frame from the given
    channel, averages all samples (DC measurement), and returns the mean
    voltage in Volts.
    """
    osc = Oscilloscope(serial, force_connect=True)
    try:
        data = osc.get_data(wait_complete=True)
        samples = data[f"ch{channel}"]
        return float(np.mean(samples))
    finally:
        osc.relinquish_ownership()


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


# ===========================================================================
# MAIN
# ===========================================================================

def main() -> None:
    ensure_csv(OUTPUT_CSV)
    run = 1

    print(f"Logging to '{OUTPUT_CSV}'. Press Ctrl+C to stop.\n")

    try:
        while True:
            print(f"Run {run}")

            # ── Step 1: read thermocouple ──────────────────────────────────
            print("  Reading thermocouple voltage ...")
            voltage_V   = read_thermocouple_voltage(MOKU_SERIAL, THERMO_CHANNEL)
            temperature = voltage_to_temperature_C(voltage_V, CAL_COEFFS, CAL_T_MEAN, CAL_T_STD,
                                                   CAL_T_MIN_K, CAL_T_MAX_K)
            print(f"  → {voltage_V * 1000:.2f} mV  =  {temperature:.2f} °C")

            # ── Step 2: frequency sweep ────────────────────────────────────
            print(f"  Sweeping {SWEEP_START_HZ} Hz → {SWEEP_END_HZ} Hz ...")
            fra = FrequencyResponseAnalyzer(MOKU_SERIAL, force_connect=True)
            try:
                fra.set_sweep(
                    start_frequency=SWEEP_START_HZ,
                    stop_frequency=SWEEP_END_HZ,
                    num_points=SWEEP_POINTS,
                    strict=False,
                )
                fra.set_output(OUTPUT_CHANNEL, amplitude=SWEEP_AMPLITUDE)
                fra.start_sweep(single=True)
                sweep_data  = fra.get_data(wait_complete=True)
            finally:
                fra.relinquish_ownership()

            frequencies = sweep_data["ch1"]["frequency"]
            gains_db    = sweep_data["ch1"]["magnitude"]
            resonant_hz = find_resonant_frequency(frequencies, gains_db)
            timestamp   = datetime.datetime.now().isoformat(timespec="seconds")

            print(f"  → resonant frequency: {resonant_hz:.1f} Hz\n")

            append_row(OUTPUT_CSV, {
                "run":                   run,
                "time":                  timestamp,
                "resonant_frequency_hz": resonant_hz,
                "temperature_C":         round(temperature, 3),
            })

            run += 1

    except KeyboardInterrupt:
        print("\nStopped by user.")


if __name__ == "__main__":
    main()
