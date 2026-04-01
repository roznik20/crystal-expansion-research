"""
Crystal Expansion Frequency Sweep Logger
=========================================
Runs repeated Moku:Go FrequencyResponseAnalyzer sweeps, prompts for the
temperature at each sweep, finds the resonant frequency (peak gain), and
appends one row per run to a CSV.

CSV schema
----------
run                  : integer, increments each loop iteration
time                 : ISO-8601 wall-clock timestamp
resonant_frequency_hz: frequency (Hz) at which gain is maximum
temperature_C        : temperature in °C entered by the user
"""

import csv
import datetime
import os
import sys

from moku.instruments import FrequencyResponseAnalyzer

# ===========================================================================
# USER CONFIGURATION
# ===========================================================================

MOKU_SERIAL     = "MokuGo-008036.local"

SWEEP_START_HZ  = 1_000        # start frequency (Hz)
SWEEP_END_HZ    = 1_000_000    # stop  frequency (Hz)
SWEEP_POINTS    = 512          # number of frequency points
SWEEP_AMPLITUDE = 0.5          # stimulus amplitude (Vpp)
OUTPUT_CHANNEL  = 1            # Moku output channel for the stimulus

OUTPUT_CSV      = "resonance_log.csv"
LOOP_DELAY_S    = 0.0          # seconds to wait between runs (0 = none)

# ===========================================================================
# HELPERS
# ===========================================================================

CSV_FIELDS = ["run", "time", "resonant_frequency_hz", "temperature_C"]


def ensure_csv(path: str) -> None:
    if not os.path.exists(path):
        with open(path, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()


def append_row(path: str, row: dict) -> None:
    with open(path, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=CSV_FIELDS).writerow(row)


def find_resonant_frequency(frequencies: list, gains_db: list) -> float:
    peak_idx = gains_db.index(max(gains_db))
    return frequencies[peak_idx]


def get_temperature() -> float:
    while True:
        raw = input("Enter temperature (°C): ").strip()
        try:
            return float(raw)
        except ValueError:
            print("  Invalid input — please enter a number.")


# ===========================================================================
# MAIN
# ===========================================================================

def main() -> None:
    ensure_csv(OUTPUT_CSV)
    run = 1

    print(f"Connecting to Moku at {MOKU_SERIAL} ...")
    fra = FrequencyResponseAnalyzer(MOKU_SERIAL, force_connect=True)

    try:
        fra.set_sweep(
            start_frequency=SWEEP_START_HZ,
            stop_frequency=SWEEP_END_HZ,
            num_points=SWEEP_POINTS,
            strict=False,
        )
        fra.set_output(OUTPUT_CHANNEL, amplitude=SWEEP_AMPLITUDE)

        print(f"Logging to '{OUTPUT_CSV}'. Press Ctrl+C to stop.\n")

        while True:
            temperature = get_temperature()

            print(f"  Run {run}: sweeping {SWEEP_START_HZ} Hz → {SWEEP_END_HZ} Hz ...")
            fra.start_sweep(single=True)
            data = fra.get_data(wait_complete=True)

            frequencies = data["ch1"]["frequency"]
            gains_db    = data["ch1"]["magnitude"]

            resonant_hz = find_resonant_frequency(frequencies, gains_db)
            timestamp   = datetime.datetime.now().isoformat(timespec="seconds")

            row = {
                "run":                   run,
                "time":                  timestamp,
                "resonant_frequency_hz": resonant_hz,
                "temperature_C":         temperature,
            }
            append_row(OUTPUT_CSV, row)

            print(f"  → resonant frequency: {resonant_hz:.1f} Hz  |  temp: {temperature} °C\n")
            run += 1

            if LOOP_DELAY_S > 0:
                import time as _time
                _time.sleep(LOOP_DELAY_S)

    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        fra.relinquish_ownership()


if __name__ == "__main__":
    main()
