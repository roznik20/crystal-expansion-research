import numpy as np
import datetime
import json
import csv
from moku.instruments import MultiInstrument, Oscilloscope, FrequencyResponseAnalyzer
from moku_script import ensure_csv, append_row, voltage_to_temperature_C, find_resonant_frequency

#===============================

#HARD-CODED SECTION

#-------------------------------
print("the beginning")

MOKU_SERIAL       = "MokuGo-008036.local"
THERMO_CHANNEL    = 1            #oscilloscope slot
STREAM_DT         = 10           #datalogger
SAMPLE_RATE       = 5            #datalogger

SWEEP_START_HZ    = 30000        # start frequency (Hz)
SWEEP_END_HZ      = 300000    # stop  frequency (Hz)
SWEEP_POINTS      = 1024          # number of frequency points
SWEEP_AMPLITUDE   = 0.5          # stimulus amplitude (Vpp)
OUTPUT_CHANNEL    = 1            # Moku output channel for the stimulus

OUTPUT_CSV        = "final_data/test.csv"
CSV_FIELDS = ["run", "time", "capacitance_value", "thermo_volt", "temperature_C"]
RAW_SWEEP_CSV     = "final_data/test_raw.csv"

#thermo calibration constants

CAL_COEFFS  = np.array([-5.371838e+01, 1.037465e+02,
                         1961.945128, 1227.4515])
CAL_T_MEAN  = 398.27    # K
CAL_T_STD   = 193.13    # K
CAL_T_MIN_K = 73.15     # K  (-200 °C)
CAL_T_MAX_K = 573.15    # K  (300 °C)

a,b = 1.08033962e-02, 3.70341310e-13

#===============================

def read_thermo_volt(osc_inst,channel):
    data = osc_inst.get_data(wait_complete=True)
    samples = data[f"ch{channel}"]
    return float(np.mean(samples))

def cap_calc(f):
    return ( 1 / (2*np.pi*f) ** 2 - b) / a


mim = MultiInstrument(MOKU_SERIAL, platform_id=2, force_connect=True)

#Configure csv file
ensure_csv(OUTPUT_CSV)
run = 1
print(f"Logging to '{OUTPUT_CSV}'. Press Ctrl+C to stop.\n")

try:
    
    #Configure MultiInstrument mode
    osc = mim.set_instrument(1, Oscilloscope)
    fra = mim.set_instrument(2, FrequencyResponseAnalyzer)

    connections = [
        dict(source='Input2', destination='Slot1InA'),
        dict(source='Slot2OutA', destination='Output1'),
        dict(source='Input1', destination='Slot2InA')
    ]

    mim.set_connections(connections=connections)

    #power for AD595 thermocouple
    mim.set_power_supply(1, enable=True, voltage=-5, current=0.1)
    mim.set_power_supply(2, enable=True, voltage=10, current=0.1)

    #Configure oscilloscope
    osc.set_timebase(-0.05, 0.05)

    #Configure FRA
    fra.set_sweep(
        start_frequency=SWEEP_START_HZ,
        stop_frequency=SWEEP_END_HZ,
        num_points=SWEEP_POINTS,
        averaging_time=2e-3,
        strict=False,
    )
    sweep_cfg = fra.get_sweep()
    print("Sweep config applied by Moku:")
    for k, v in sweep_cfg.items():
        print(f"  {k}: {v}")
    print()
    
    fra.set_output(1, amplitude=SWEEP_AMPLITUDE)

    #Data processing
    while True:
        print(f"Run {run}")
        #recording with oscillsocope
        #print("  Reading thermocouple voltage ...")
        voltage_V   = read_thermo_volt(osc, THERMO_CHANNEL)
        try:
            temperature = voltage_to_temperature_C(voltage_V, CAL_COEFFS, CAL_T_MEAN, CAL_T_STD,
                                                    CAL_T_MIN_K, CAL_T_MAX_K)
        except ValueError as e:
            print(f"  Warning: {e}")
            temperature = float('nan')

        #print(f"  → {voltage_V * 1000:.2f} mV  =  {temperature:.2f} °C")
        
        #recording with FRA
        fra.start_sweep(single=True)
        sweep_data = fra.get_data(wait_complete=True)

        #logging the data in the csv file
        frequencies = sweep_data["ch1"]["frequency"]
        gains_db    = sweep_data["ch1"]["magnitude"]

        # DEBUG: print gain curve summary to diagnose stale/flat data
        g = np.asarray(gains_db, dtype=float)
        f = np.asarray(frequencies, dtype=float)
        valid = ~np.isnan(g)
        """print(f"  [DEBUG] {valid.sum()}/{len(g)} valid points, "
              f"gain range: {np.nanmin(g):.1f} to {np.nanmax(g):.1f} dB, "
              f"max at {f[np.nanargmax(g)]:.0f} Hz")"""

        resonant_hz = find_resonant_frequency(frequencies, gains_db)
        timestamp   = datetime.datetime.now().isoformat(timespec="seconds")

        #print(f"  → resonant frequency: {resonant_hz:.1f} Hz\n") 
        cap_val = cap_calc(resonant_hz)

        # Save raw sweep for live viewing in sweep_viewer.ipynb
        with open('latest_sweep.json', 'w') as jf:
            json.dump({
                'run': run,
                'frequency': f.tolist(),
                'gain_db': g.tolist(),
                'resonant_hz': resonant_hz,
                'temperature_C': round(temperature, 3),
                'capacitance_pF': cap_val * 1e12,
            }, jf)

        # Append raw sweep data to CSV (one row per frequency point)
        write_header = not __import__('os').path.exists(RAW_SWEEP_CSV)
        with open(RAW_SWEEP_CSV, 'a', newline='') as rf:
            writer = csv.writer(rf)
            if write_header:
                writer.writerow(['run', 'frequency_hz', 'gain_db'])
            for fi, gi in zip(f, g):
                writer.writerow([run, fi, gi])

        append_row(OUTPUT_CSV, {
            "run":                   run,
            "time":                  timestamp,
            "capacitance_value":     cap_val,
            "thermo_volt":           voltage_V,
            "temperature_C":         round(temperature, 3),
        })

        run += 1

except KeyboardInterrupt:
    # Catches the Ctrl+C and exits cleanly without a giant red error
    print("\nExperiment stopped by user. Saving and disconnecting...")

except Exception as e:
    print(f"\nAn error occurred: {e}")
    raise

finally:
    mim.set_power_supply(1, enable=False)
    mim.set_power_supply(2, enable=False)
    mim.relinquish_ownership()